from datetime import datetime, timezone
from typing import Any, ClassVar, Final
from urllib.parse import urlparse

from mypycli import Commandable, Installable, Updatable, utils
from mypycli.types import Color, Command

from mytonprovider import constants
from mytonprovider.locales import _


class UpdaterModule(Installable, Commandable):
    mandatory: ClassVar[bool] = False
    name: ClassVar[str] = "updater"
    label: ClassVar[str] = "Updater"

    SERVICE_NAME: Final[str] = f"{constants.APP_NAME}-updater"
    CHECK_UPDATES_INTERVAL_SEC: Final[int] = 86400
    REMOTE_AGE_THRESHOLD_DAYS: Final[int] = 7

    service: ClassVar[utils.SystemdService] = utils.SystemdService(SERVICE_NAME)

    @property
    def is_enabled(self) -> bool:
        return bool(self.app.db.modules.updater.enabled)

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "updater",
                description=_("modules.updater.cmd.group"),
                always_visible=True,
                children=[
                    Command(
                        "enable",
                        self._cmd_enable,
                        _("modules.updater.cmd.enable"),
                    ),
                    Command(
                        "disable",
                        self._cmd_disable,
                        _("modules.updater.cmd.disable"),
                    ),
                    Command(
                        "update",
                        self._cmd_update,
                        _("modules.updater.cmd.update"),
                        "<module> [<url>|<branch>] [<author>] [<repo>]",
                    ),
                ],
            ),
        ]

    def on_install(self) -> None:
        self.app.db.modules.updater.enabled = True
        self.service.create(
            exec_start=f"{constants.VENV_DIR}/bin/{constants.APP_NAME} updater-daemon",
            user="root",
            environment={"PYTHONUNBUFFERED": "1"},
            description=f"{constants.APP_NAME} updater loop",
        )
        self.service.enable()
        self.service.start()

    def on_uninstall(self) -> None:
        self.app.db.modules.updater.enabled = False
        self.service.disable()
        self.service.remove()

    def update_modules(self) -> None:
        if not self.app.db.modules.updater.enabled:
            return
        for module in self.app.modules.all():
            if not isinstance(module, Updatable):
                continue
            try:
                if not self._is_remote_old_enough(module):
                    self.logger.debug(f"{module.name}: remote commit too recent, skipping")
                    continue
                self.logger.info(f"{module.name}: updating")
                module.on_update()
            except Exception:
                self.logger.exception(f"{module.name}: update failed")

    def _cmd_enable(self, app: Any, _args: list[str]) -> None:
        self.app.db.modules.updater.enabled = True
        app.console.print(_("modules.updater.msg.enabled"), Color.GREEN)

    def _cmd_disable(self, app: Any, _args: list[str]) -> None:
        self.app.db.modules.updater.enabled = False
        app.console.print(_("modules.updater.msg.disabled"), Color.YELLOW)

    def _cmd_update(self, app: Any, args: list[str]) -> None:
        if not args or len(args) > 4:
            app.console.print(
                f"{_('common.usage_prefix')} updater update <module> [<url>|<branch>] [<author>] [<repo>]",
                Color.YELLOW,
            )
            return

        name = args[0]
        target = self.app.modules.get(name)
        if target is None or not isinstance(target, Updatable):
            app.console.print(_("modules.updater.msg.not_updatable", name=name), Color.RED)
            return

        git_repo = getattr(target, "repo", None)
        if not isinstance(git_repo, utils.LocalGitRepo):
            app.console.print(_("modules.updater.msg.no_git_repo", name=name), Color.RED)
            return

        branch: str | None = args[1] if len(args) > 1 else None
        author: str | None = args[2] if len(args) > 2 else None
        repo: str | None = args[3] if len(args) > 3 else None

        if branch and ("github.com" in branch or "://" in branch):
            if author is not None or repo is not None:
                app.console.print(_("modules.updater.msg.url_form_extra"), Color.RED)
                return
            try:
                author, repo, branch = self._parse_github_url(branch)
            except ValueError as exc:
                app.console.print(str(exc), Color.RED)
                return

        if author or repo:
            try:
                cur_author, cur_repo, _cur_branch = self._parse_github_url(git_repo.remote.url)
            except ValueError as exc:
                app.console.print(str(exc), Color.RED)
                return
            new_url = f"https://github.com/{author or cur_author}/{repo or cur_repo}"
            if new_url != git_repo.remote.url:
                git_repo.set_origin(new_url)
                app.console.print(
                    _("modules.updater.msg.origin_set", name=name, url=new_url),
                    Color.GRAY,
                )

        git_repo.update(ref=branch)

        build = getattr(target, "build", None)
        if not callable(build):
            self.logger.error(f"{name}: no build() method")
            return
        build()

        app.console.print(_("modules.updater.msg.updated", name=name), Color.GREEN)
        if name == constants.APP_NAME:
            app.console.print(_("modules.updater.msg.restart_console_hint"), Color.YELLOW)

    def _is_remote_old_enough(self, module: Updatable) -> bool:
        repo = getattr(module, "repo", None)
        if not isinstance(repo, utils.LocalGitRepo):
            return True
        try:
            repo.fetch()
            info = repo.info
            target = repo.remote.info.latest_version if info.tag else f"origin/{info.branch or 'master'}"
            if target is None:
                return False
            target_dt = repo.commit_date(target)
        except Exception:
            self.logger.exception(f"{module.name}: failed to query upgrade target")
            return False
        age_days = (datetime.now(timezone.utc) - target_dt).days
        return age_days >= self.REMOTE_AGE_THRESHOLD_DAYS

    @staticmethod
    def _parse_github_url(url: str) -> tuple[str, str, str | None]:
        url = url.strip()
        if "://" not in url and "/" in url:
            url = f"https://github.com/{url}"
        if not url.startswith(("http://", "https://")):
            raise ValueError(_("modules.updater.msg.bad_url", url=url))
        parts = [p for p in urlparse(url).path.split("/") if p]
        if len(parts) < 2:
            raise ValueError(_("modules.updater.msg.bad_url", url=url))
        author = parts[0]
        repo = parts[1].removesuffix(".git")
        branch = parts[3] if len(parts) >= 4 and parts[2] == "tree" else None
        return author, repo, branch

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Final

from mypycli import Commandable, Installable, Updatable, utils
from mypycli.types import Color, Command

from mytonprovider import constants
from mytonprovider.locales import _
from mytonprovider.utils import chown_owner


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
                        "<module> [<ref>] [<author>] [<repo>]",
                    ),
                ],
            ),
        ]

    def on_install(self) -> None:
        self.app.db.modules.updater.enabled = True
        self.service.create(
            exec_start=f"{constants.VENV_DIR}/bin/{constants.APP_NAME} auto-update",
            user="root",
            environment={"PYTHONUNBUFFERED": "1"},
            description=f"{constants.APP_NAME} updater loop",
        )
        self.service.enable()
        self.service.restart()

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

        for module in self.app.modules.all():
            src_path = getattr(module, "src_path", None)
            if isinstance(src_path, Path) and src_path.is_dir():
                chown_owner(src_path, self.app.work_dir)

    def _cmd_enable(self, app: Any, _args: list[str]) -> None:
        self.on_install()
        app.console.print(_("modules.updater.msg.enabled"), Color.GREEN)

    def _cmd_disable(self, app: Any, _args: list[str]) -> None:
        self.on_uninstall()
        app.console.print(_("modules.updater.msg.disabled"), Color.YELLOW)

    def _cmd_update(self, app: Any, args: list[str]) -> None:
        if not args or len(args) > 4:
            app.console.print(_("modules.updater.msg.usage_update"), Color.YELLOW)
            return

        name = args[0]
        try:
            target = self.app.modules.get(name)
        except KeyError:
            target = None
        if target is None or not isinstance(target, Updatable):
            app.console.print(_("modules.updater.msg.not_updatable", name=name), Color.RED)
            return

        git_repo = getattr(target, "repo", None)
        if not isinstance(git_repo, utils.LocalGitRepo):
            app.console.print(_("modules.updater.msg.no_git_repo", name=name), Color.RED)
            return

        ref: str | None = args[1] if len(args) > 1 else None
        author: str | None = args[2] if len(args) > 2 else None
        repo: str | None = args[3] if len(args) > 3 else None

        if author or repo:
            new_url = f"https://github.com/{author or git_repo.author}/{repo or git_repo.repo_name}"
            if new_url != git_repo.url:
                git_repo.set_origin(new_url)
                app.console.print(
                    _("modules.updater.msg.origin_set", name=name, url=new_url),
                    Color.GRAY,
                )

        git_repo.update(ref=ref)

        build = getattr(target, "build", None)
        if not callable(build):
            self.logger.error(f"{name}: no build() method")
            return
        build()

        refresh = getattr(target, "task_check_update", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                self.logger.exception(f"{name}: post-update refresh failed")

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
            target = repo.remote.info.latest_version if info.is_tag_pinned else f"origin/{info.branch or 'master'}"
            if target is None:
                return False
            target_dt = repo.commit_date(target)
        except Exception:
            self.logger.exception(f"{module.name}: failed to query upgrade target")
            return False
        age_days = (datetime.now(timezone.utc) - target_dt).days
        self.logger.debug(f"{module.name}: remote age={age_days}d, threshold={self.REMOTE_AGE_THRESHOLD_DAYS}d")
        return age_days >= self.REMOTE_AGE_THRESHOLD_DAYS

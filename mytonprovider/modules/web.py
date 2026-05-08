from typing import Any, ClassVar, Final

from mypycli import Commandable, Installable, utils
from mypycli.types import Color, Command

from mytonprovider import constants
from mytonprovider.locales import _


class WebModule(Installable, Commandable):
    mandatory: ClassVar[bool] = False
    name: ClassVar[str] = "web"
    label: ClassVar[str] = "Web Dashboard"

    SERVICE_NAME: Final[str] = f"{constants.APP_NAME}-web"

    service: ClassVar[utils.SystemdService] = utils.SystemdService(SERVICE_NAME)

    @property
    def is_enabled(self) -> bool:
        return bool(self.app.db.modules.web.enabled)

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "web",
                description=_("modules.web.cmd.group"),
                always_visible=True,
                children=[
                    Command(
                        "password",
                        self._cmd_password,
                        _("modules.web.cmd.password"),
                    ),
                ],
            ),
        ]

    def on_install(self) -> None:
        from mytonprovider.web import auth

        state = self.app.db.modules.web
        state.enabled = True
        if not state.session_secret:
            state.session_secret = auth.generate_secret()
        self._prompt_password()

        self.service.create(
            exec_start=f"{constants.VENV_DIR}/bin/{constants.APP_NAME} web-daemon",
            user=self.app.work_dir.owner(),
            work_dir=str(self.app.work_dir),
            environment={"PYTHONUNBUFFERED": "1"},
            description=f"{constants.APP_NAME} web dashboard",
        )
        self.service.enable()
        self.service.start()

    def on_uninstall(self) -> None:
        state = self.app.db.modules.web
        state.enabled = False
        state.password_hash = None
        state.password_salt = None
        state.session_secret = None
        state.failed_attempts = 0
        state.lockout_until = 0
        self.service.disable()
        self.service.remove()

    def _cmd_password(self, app: Any, _args: list[str]) -> None:
        from mytonprovider.web import auth

        password = app.console.secret(_("modules.web.msg.password_prompt"))
        if not password:
            app.console.print(_("modules.web.msg.password_empty"), Color.RED)
            return
        confirmation = app.console.secret(_("modules.web.msg.password_confirm"))
        if password != confirmation:
            app.console.print(_("modules.web.msg.password_mismatch"), Color.RED)
            return
        auth.set_password(self.app.db.modules.web, password)
        app.console.print(_("modules.web.msg.password_set"), Color.GREEN)

    def _prompt_password(self) -> None:
        from mytonprovider.web import auth

        try:
            password = self.app.console.secret(_("modules.web.msg.password_prompt"))
            if not password:
                self.logger.warning("web install: empty password, set later via 'web password' in REPL")
                return
            confirmation = self.app.console.secret(_("modules.web.msg.password_confirm"))
            if password != confirmation:
                self.app.console.print(_("modules.web.msg.password_mismatch"), Color.RED)
                self.logger.warning("web install: password mismatch, set later via 'web password' in REPL")
                return
            auth.set_password(self.app.db.modules.web, password)
            self.app.console.print(_("modules.web.msg.password_set"), Color.GREEN)
        except Exception:
            self.logger.warning("web install: non-interactive prompt; set password via 'web password' in REPL")

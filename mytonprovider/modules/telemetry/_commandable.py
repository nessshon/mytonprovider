from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mypycli import Commandable
from mypycli.types import Color, Command

from mytonprovider.utils import hash_telemetry_password

if TYPE_CHECKING:
    from mypycli import Application


class CommandableMixin(Commandable):
    __abstract__ = True

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "telemetry",
                description="Telemetry controls",
                children=[
                    Command("enable", self._cmd_enable, "Enable telemetry"),
                    Command("disable", self._cmd_disable, "Disable telemetry"),
                    Command("password", self._cmd_password, "Set access password"),
                ],
            ),
        ]

    def _cmd_enable(self, app: Application[Any], _args: list[str]) -> None:
        self.db.enabled = True
        app.console.print("Telemetry enabled.", color=Color.GREEN)
        if not self.db.password_hash:
            app.console.print(
                "No password set; data is sent anonymously. Use `telemetry password` to link an account.",
                color=Color.YELLOW,
            )

    def _cmd_disable(self, app: Application[Any], _args: list[str]) -> None:
        self.db.enabled = False
        app.console.print("Telemetry disabled.", color=Color.YELLOW)

    def _cmd_password(self, app: Application[Any], _args: list[str]) -> None:
        pw = app.console.secret("Telemetry password")
        repeat = app.console.secret("Repeat password")
        if pw != repeat:
            app.console.print("Passwords do not match.", color=Color.RED)
            return
        self.db.password_hash = hash_telemetry_password(pw)
        app.console.print("Telemetry password updated.", color=Color.GREEN)

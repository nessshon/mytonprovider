from __future__ import annotations

from typing import TYPE_CHECKING

from mypycli import Installable

if TYPE_CHECKING:
    from mypycli import InstallContext
    from pydantic import BaseModel


class InstallableMixin(Installable):
    __abstract__ = True

    def on_install(self, params: BaseModel | None = None, context: InstallContext | None = None) -> None:
        del params, context
        # Selecting telemetry during install implies consent to send data.
        # The password is optional and can be set later via `telemetry password`.
        self.db.enabled = True

    def on_uninstall(self) -> None:
        self.db.enabled = False

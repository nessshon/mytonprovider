from __future__ import annotations

from typing import TYPE_CHECKING

from mypycli import Installable
from mypycli.utils.service import SystemdService
from mypycli.utils.system import run_as_root

from mytonprovider import constants

if TYPE_CHECKING:
    from mypycli import InstallContext
    from pydantic import BaseModel

SERVICE_NAME = "mytonprovider-update"


class InstallableMixin(Installable):
    __abstract__ = True

    def on_install(self, params: BaseModel | None = None, context: InstallContext | None = None) -> None:
        del params, context
        svc = SystemdService(SERVICE_NAME)
        svc.create(
            service_type="oneshot",
            exec_start=f"{constants.VENV_DIR}/bin/{constants.APP_NAME} update",
            user="root",
            description=f"{constants.APP_LABEL} auto-update runner",
        )
        svc.create_timer(
            on_calendar="daily",
            persistent=True,
            description=f"Trigger {constants.APP_LABEL} auto-update daily",
        )
        # Enable + start the timer unit; the oneshot service runs only when the timer fires.
        run_as_root(["systemctl", "enable", f"{SERVICE_NAME}.timer"])
        run_as_root(["systemctl", "start", f"{SERVICE_NAME}.timer"])

    def on_uninstall(self) -> None:
        SystemdService(SERVICE_NAME).remove()

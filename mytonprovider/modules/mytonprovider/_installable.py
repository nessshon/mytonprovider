from __future__ import annotations

from typing import TYPE_CHECKING

from mypycli import Installable
from mypycli.utils.service import SystemdService

from mytonprovider import constants

if TYPE_CHECKING:
    from mypycli import InstallContext
    from pydantic import BaseModel

SERVICE_NAME = "mytonproviderd"


class InstallableMixin(Installable):
    __abstract__ = True

    def on_install(self, params: BaseModel | None = None, context: InstallContext | None = None) -> None:
        del params, context
        svc = SystemdService(SERVICE_NAME)
        svc.create(
            exec_start=f"{constants.VENV_DIR}/bin/{constants.APP_NAME} daemon",
            user=constants.INSTALL_USER,
            work_dir=str(constants.WORK_DIR),
            description=f"{constants.APP_LABEL} daemon",
            after="network.target",
            restart="on-failure",
            restart_sec=10,
        )
        svc.enable()
        svc.start()

    def on_uninstall(self) -> None:
        SystemdService(SERVICE_NAME).remove()

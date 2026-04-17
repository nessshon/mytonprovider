from __future__ import annotations

from typing import ClassVar

from mytonprovider import constants

from ._installable import InstallableMixin
from ._startable import StartableMixin
from ._statusable import StatusableMixin
from ._updatable import UpdatableMixin


class MytonproviderModule(InstallableMixin, UpdatableMixin, StatusableMixin, StartableMixin):
    name: ClassVar[str] = constants.APP_NAME
    label: ClassVar[str] = constants.APP_LABEL
    mandatory: ClassVar[bool] = True

    install_params: ClassVar[None] = None
    db_schema: ClassVar[None] = None

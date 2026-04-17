from __future__ import annotations

from typing import ClassVar

from ._commandable import CommandableMixin
from ._daemonic import DaemonicMixin
from ._installable import InstallableMixin
from ._startable import StartableMixin
from ._statusable import StatusableMixin
from ._updatable import UpdatableMixin
from .schemas import TonStorageDBSchema, TonStorageInstallParams


class TonStorageModule(
    InstallableMixin,
    UpdatableMixin,
    DaemonicMixin,
    StatusableMixin,
    CommandableMixin,
    StartableMixin,
):
    name: ClassVar[str] = "ton-storage"
    label: ClassVar[str] = "Ton Storage"
    mandatory: ClassVar[bool] = True

    install_params: ClassVar[type[TonStorageInstallParams]] = TonStorageInstallParams
    db_schema: ClassVar[type[TonStorageDBSchema]] = TonStorageDBSchema

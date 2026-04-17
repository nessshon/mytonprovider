from __future__ import annotations

from typing import ClassVar

from ._commandable import CommandableMixin
from ._daemonic import DaemonicMixin
from ._installable import InstallableMixin
from ._startable import StartableMixin
from ._statusable import StatusableMixin
from ._updatable import UpdatableMixin
from .schemas import TonStorageProviderDBSchema, TonStorageProviderInstallParams


class TonStorageProviderModule(
    InstallableMixin,
    UpdatableMixin,
    StartableMixin,
    DaemonicMixin,
    StatusableMixin,
    CommandableMixin,
):
    name: ClassVar[str] = "ton-storage-provider"
    label: ClassVar[str] = "Ton Storage Provider"
    mandatory: ClassVar[bool] = True

    install_params: ClassVar[type[TonStorageProviderInstallParams]] = TonStorageProviderInstallParams
    db_schema: ClassVar[type[TonStorageProviderDBSchema]] = TonStorageProviderDBSchema

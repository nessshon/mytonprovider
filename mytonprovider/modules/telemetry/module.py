from __future__ import annotations

from typing import ClassVar

from ._commandable import CommandableMixin
from ._daemonic import DaemonicMixin
from ._installable import InstallableMixin
from .schemas import TelemetryDBSchema


class TelemetryModule(InstallableMixin, DaemonicMixin, CommandableMixin):
    name: ClassVar[str] = "telemetry"
    label: ClassVar[str] = "Telemetry"
    mandatory: ClassVar[bool] = False

    install_params: ClassVar[None] = None
    db_schema: ClassVar[type[TelemetryDBSchema]] = TelemetryDBSchema

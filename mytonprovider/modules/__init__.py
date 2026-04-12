from .benchmark import BenchmarkModule
from .core import (
    BaseModule,
    Commandable,
    Daemonic,
    Installable,
    ModuleRegistry,
    Startable,
    Statusable,
    Updatable,
    build_registry,
)
from .mytonprovider import MytonproviderModule
from .statistics import StatisticsModule
from .telemetry import TelemetryModule
from .ton_storage import TonStorageModule
from .ton_storage_provider import TonStorageProviderModule

# Order matters: cmd_init iterates this list to call install() on each
# module. Dependencies are implicit:
#   - TonStorageProviderModule.install needs TonStorageModule already
#     installed (reads ``mconfig.ton_storage.api``).
#   - TelemetryModule needs TonStorageModule for pubkey.
#   - MytonproviderModule goes first to create the global config.
MODULE_CLASSES: list[type[BaseModule]] = [
    MytonproviderModule,
    StatisticsModule,
    BenchmarkModule,
    TonStorageModule,
    TonStorageProviderModule,
    TelemetryModule,
]

__all__ = [
    "MODULE_CLASSES",
    "BaseModule",
    "BenchmarkModule",
    "Commandable",
    "Daemonic",
    "Installable",
    "ModuleRegistry",
    "MytonproviderModule",
    "Startable",
    "StatisticsModule",
    "Statusable",
    "TelemetryModule",
    "TonStorageModule",
    "TonStorageProviderModule",
    "Updatable",
    "build_registry",
]

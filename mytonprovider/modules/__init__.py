from mytonprovider.modules.auto_update import AutoUpdateModule
from mytonprovider.modules.benchmark import BenchmarkModule
from mytonprovider.modules.mytonprovider import MytonproviderModule
from mytonprovider.modules.statistics import StatisticsModule
from mytonprovider.modules.telemetry import TelemetryModule
from mytonprovider.modules.ton_storage import TonStorageModule
from mytonprovider.modules.ton_storage_provider import TonStorageProviderModule

__all__ = [
    "MODULES",
    "AutoUpdateModule",
    "BenchmarkModule",
    "MytonproviderModule",
    "StatisticsModule",
    "TelemetryModule",
    "TonStorageModule",
    "TonStorageProviderModule",
]

# Registration order drives install/on_start sequence; teardown runs reversed.
# Mandatory Installables first (with dep-graph — tsp reads ts.db at install),
# then non-Installable mandatories (samplers), then optional Installables.
MODULES = [
    MytonproviderModule,
    TonStorageModule,
    TonStorageProviderModule,
    StatisticsModule,
    BenchmarkModule,
    TelemetryModule,
    AutoUpdateModule,
]

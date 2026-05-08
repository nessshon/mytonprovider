from .benchmark import BenchmarkModule
from .mytonprovider import MytonproviderModule
from .sys_metrics import SysMetricsModule
from .telemetry import TelemetryModule
from .ton_storage import TonStorageModule
from .ton_storage_provider import TonStorageProviderModule
from .ton_wallet import TonWalletModule
from .updater import UpdaterModule
from .web import WebModule

MODULES = [
    MytonproviderModule,
    TonStorageModule,
    TonStorageProviderModule,
    TonWalletModule,
    BenchmarkModule,
    SysMetricsModule,
    TelemetryModule,
    UpdaterModule,
    WebModule,
]

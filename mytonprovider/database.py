from mypycli import DatabaseSchema
from pydantic import BaseModel, ConfigDict, Field

from mytonprovider import constants


class NetAverages(BaseModel):
    recv: tuple[float, float, float] = (0.0, 0.0, 0.0)
    sent: tuple[float, float, float] = (0.0, 0.0, 0.0)
    load: tuple[float, float, float] = (0.0, 0.0, 0.0)
    pps: tuple[float, float, float] = (0.0, 0.0, 0.0)


class DiskAverages(BaseModel):
    load: tuple[float, float, float] = (0.0, 0.0, 0.0)
    iops: tuple[float, float, float] = (0.0, 0.0, 0.0)
    load_percent: tuple[float, float, float] = (0.0, 0.0, 0.0)


class MemorySample(BaseModel):
    total: int = 0
    used: int = 0
    percent: float = 0.0


class CpuSample(BaseModel):
    name: str | None = None
    count_logical: int = 0
    load: tuple[float, float, float] = (0.0, 0.0, 0.0)


class OsSample(BaseModel):
    sysname: str = ""
    release: str = ""
    version: str = ""
    machine: str = ""


class HardwareSample(BaseModel):
    product_name: str | None = None
    is_virtual: bool | None = None


class MetricsSnapshot(BaseModel):
    timestamp: int = 0
    bytes_recv: int = 0
    bytes_sent: int = 0
    net: NetAverages | None = None
    disks: dict[str, DiskAverages] = Field(default_factory=dict)
    ram: MemorySample = Field(default_factory=MemorySample)
    swap: MemorySample = Field(default_factory=MemorySample)
    cpu: CpuSample = Field(default_factory=CpuSample)
    os: OsSample = Field(default_factory=OsSample)
    hardware: HardwareSample = Field(default_factory=HardwareSample)


class DailyTraffic(BaseModel):
    timestamp: int
    bytes_recv: int
    bytes_sent: int


class FioResult(BaseModel):
    name: str
    read: str
    read_iops: str
    write: str
    write_iops: str


class BenchmarkDisk(BaseModel):
    qd64: FioResult
    qd1: FioResult


class BenchmarkNetwork(BaseModel):
    model_config = ConfigDict(extra="allow")

    download: float = 0.0
    upload: float = 0.0
    ping: float = 0.0


class BenchmarkSnapshot(BaseModel):
    timestamp: int
    disk: BenchmarkDisk
    network: BenchmarkNetwork


class TonStorageDBSchema(DatabaseSchema):
    enabled: bool = False
    storage_path: str = ""
    api_port: int = 0
    udp_port: int = 0


class SysMetricsDBSchema(DatabaseSchema):
    snapshot: MetricsSnapshot | None = None
    daily_traffic: dict[str, DailyTraffic] = Field(default_factory=dict)


class BenchmarkDBSchema(DatabaseSchema):
    snapshot: BenchmarkSnapshot | None = None


class TelemetryDBSchema(DatabaseSchema):
    enabled: bool = False
    password_hash: str | None = None
    last_benchmark_sent_at: int = 0
    last_cycle_at: int = 0


class UpdaterDBSchema(DatabaseSchema):
    enabled: bool = False


class WebDBSchema(DatabaseSchema):
    enabled: bool = False
    password_hash: str | None = None
    password_salt: str | None = None
    session_secret: str | None = None
    failed_attempts: int = 0
    lockout_until: int = 0


class TonWalletDBSchema(DatabaseSchema):
    registered: bool = False


class ModulesGroup(DatabaseSchema):
    ton_storage: TonStorageDBSchema = Field(default_factory=TonStorageDBSchema)
    ton_wallet: TonWalletDBSchema = Field(default_factory=TonWalletDBSchema)
    benchmark: BenchmarkDBSchema = Field(default_factory=BenchmarkDBSchema)
    sys_metrics: SysMetricsDBSchema = Field(default_factory=SysMetricsDBSchema)
    telemetry: TelemetryDBSchema = Field(default_factory=TelemetryDBSchema)
    updater: UpdaterDBSchema = Field(default_factory=UpdaterDBSchema)
    web: WebDBSchema = Field(default_factory=WebDBSchema)


class InstallArgs(DatabaseSchema):
    ton_storage_path: str | None = None
    ton_storage_provider_storage_cost: float | None = None
    ton_storage_provider_space_gb: int | None = None
    ton_storage_provider_max_bag_size_gb: int | None = None


class LiteBalancerSettings(DatabaseSchema):
    config: str = str(constants.TON_CONFIG_PATH)
    rps_limit: int = 10
    connect_timeout: float = 1.5
    client_connect_timeout: float = 1.25
    request_timeout: float = 30.0
    client_request_timeout: float = 5
    retry_total_timeout: float = 10
    retry_rule_rate_limit: int = 3
    retry_rule_backend_timeout: int = 5
    retry_rule_cannot_load_block: int = 10


class StorageApiSettings(DatabaseSchema):
    request_timeout: float = 5.0
    verify_timeout: float = 60.0


class TelemetryApiSettings(DatabaseSchema):
    request_timeout: float = 5.0


class AdnlCheckerApiSettings(DatabaseSchema):
    request_timeout: float = 2.5


class WebSettings(DatabaseSchema):
    host: str = "127.0.0.1"
    port: int = 8080
    refresh_sec: float = 5.0
    session_max_age_sec: int = 60 * 60 * 24 * 30


class Settings(DatabaseSchema):
    lite_balancer: LiteBalancerSettings = Field(default_factory=LiteBalancerSettings)
    storage_api: StorageApiSettings = Field(default_factory=StorageApiSettings)
    telemetry_api: TelemetryApiSettings = Field(default_factory=TelemetryApiSettings)
    adnl_checker_api: AdnlCheckerApiSettings = Field(default_factory=AdnlCheckerApiSettings)
    web: WebSettings = Field(default_factory=WebSettings)


class AppDatabaseSchema(DatabaseSchema):
    install_args: InstallArgs = Field(default_factory=InstallArgs)
    modules: ModulesGroup = Field(default_factory=ModulesGroup)
    settings: Settings = Field(default_factory=Settings)

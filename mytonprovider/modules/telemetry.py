import base64
import hashlib
import time
from typing import Any, ClassVar, Final, cast

from mypycli import Commandable, Daemonic, Installable, Updatable, utils
from mypycli.types import ByteUnit, ByteUnitDec, Color, Command

from mytonprovider import constants
from mytonprovider.clients.telemetry import (
    BenchmarkPayload,
    CpuTelemetry,
    DiskBenchmarks,
    MemoryTelemetry,
    TelemetryApi,
    TelemetryPayload,
    TelemetryProvider,
    TelemetryStorage,
    UnameTelemetry,
)
from mytonprovider.database import MemorySample, MetricsSnapshot, NetAverages
from mytonprovider.locales import _
from mytonprovider.modules.benchmark import BenchmarkModule
from mytonprovider.modules.sys_metrics import SysMetricsModule
from mytonprovider.modules.ton_storage import TonStorageModule
from mytonprovider.modules.ton_storage_provider import TonStorageProviderModule


class TelemetryModule(
    Installable,
    Daemonic,
    Commandable,
):
    mandatory: ClassVar[bool] = False
    name: ClassVar[str] = "telemetry"
    label: ClassVar[str] = "Telemetry"

    TELEMETRY_INTERVAL_SEC: Final[int] = 60
    BENCHMARK_INTERVAL_SEC: Final[int] = 86400

    @property
    def is_enabled(self) -> bool:
        return bool(self.app.db.modules.telemetry.enabled)

    @property
    def api(self) -> TelemetryApi:
        cfg = self.app.db.settings.telemetry_api
        return TelemetryApi(
            telemetry_url=constants.TELEMETRY_URL,
            benchmark_url=constants.BENCHMARK_URL,
            timeout=cfg.request_timeout,
        )

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "telemetry",
                description=_("modules.telemetry.cmd.group"),
                always_visible=True,
                children=[
                    Command(
                        "enable",
                        self._cmd_enable,
                        _("modules.telemetry.cmd.enable"),
                    ),
                    Command(
                        "disable",
                        self._cmd_disable,
                        _("modules.telemetry.cmd.disable"),
                    ),
                    Command(
                        "password",
                        self._cmd_password,
                        _("modules.telemetry.cmd.password"),
                    ),
                ],
            ),
        ]

    def on_install(self) -> None:
        self.app.db.modules.telemetry.enabled = True

    def on_uninstall(self) -> None:
        self.app.db.modules.telemetry.enabled = False

    def on_daemon(self) -> None:
        self.run_cycle(self.cycle_send, seconds=self.TELEMETRY_INTERVAL_SEC)

    def cycle_send(self) -> None:
        state = self.app.db.modules.telemetry
        state.last_cycle_at = int(time.time())
        if not state.enabled:
            return
        try:
            self.api.send_telemetry(self._build_telemetry())
        except Exception:
            self.logger.exception("telemetry send failed")
            return

        now = int(time.time())
        if now - state.last_benchmark_sent_at < self.BENCHMARK_INTERVAL_SEC:
            return
        bench_payload = self._build_benchmark()
        if bench_payload is None:
            return
        try:
            self.api.send_benchmark(bench_payload)
            state.last_benchmark_sent_at = now
        except Exception:
            self.logger.exception("benchmark send failed")

    def _cmd_enable(self, app: Any, _args: list[str]) -> None:
        state = self.app.db.modules.telemetry
        state.enabled = True
        app.console.print(_("modules.telemetry.msg.enabled"), Color.GREEN)
        cycle_alive = (int(time.time()) - state.last_cycle_at) < self.TELEMETRY_INTERVAL_SEC * 2
        if not cycle_alive:
            utils.SystemdService(constants.APP_NAME).restart()
            app.console.print(_("modules.telemetry.msg.daemon_restarted"), Color.YELLOW)

    def _cmd_disable(self, app: Any, _args: list[str]) -> None:
        self.app.db.modules.telemetry.enabled = False
        app.console.print(_("modules.telemetry.msg.disabled"), Color.YELLOW)

    def _cmd_password(self, app: Any, _args: list[str]) -> None:
        password = app.console.secret(_("modules.telemetry.msg.password_prompt"))
        confirmation = app.console.secret(_("modules.telemetry.msg.password_confirm"))
        if password != confirmation:
            app.console.print(_("modules.telemetry.msg.password_mismatch"), Color.RED)
            return
        self.app.db.modules.telemetry.password_hash = self._hash_password(password)
        app.console.print(_("modules.telemetry.msg.password_set"), Color.GREEN)

    @staticmethod
    def _hash_password(password: str) -> str:
        data = (constants.TELEMETRY_URL + password).encode("utf-8")
        return base64.b64encode(hashlib.sha256(data).digest()).decode("utf-8")

    def _build_telemetry(self) -> TelemetryPayload:
        ts = cast("TonStorageModule", self.app.modules.get("ton-storage"))
        sm = cast("SysMetricsModule", self.app.modules.get("sys-metrics"))
        metrics = sm.snapshot or MetricsSnapshot()
        net = metrics.net or NetAverages()
        return TelemetryPayload(
            storage=self._build_storage(ts),
            git_hashes=self._build_versions(),
            net_recv=list(net.recv),
            net_sent=list(net.sent),
            net_load=list(net.load),
            bytes_recv=metrics.bytes_recv,
            bytes_sent=metrics.bytes_sent,
            disks_load={k: list(v.load) for k, v in metrics.disks.items()},
            disks_load_percent={k: list(v.load_percent) for k, v in metrics.disks.items()},
            iops={k: list(v.iops) for k, v in metrics.disks.items()},
            pps=list(net.pps),
            ram=self._build_memory(metrics.ram),
            swap=self._build_memory(metrics.swap),
            uname=UnameTelemetry.model_validate(metrics.os.model_dump()),
            cpu_info=CpuTelemetry(
                cpu_count=metrics.cpu.count_logical,
                cpu_load=list(metrics.cpu.load),
                cpu_name=metrics.cpu.name,
                product_name=metrics.hardware.product_name,
                is_virtual=metrics.hardware.is_virtual,
            ),
            pings=self._build_pings(),
            timestamp=int(time.time()),
            telemetry_pass=self.app.db.modules.telemetry.password_hash,
        )

    def _build_storage(self, ts: TonStorageModule) -> TelemetryStorage:
        config = ts.get_storage_config()
        disk = utils.sysinfo.get_disk_usage(str(ts.storage_path))
        return TelemetryStorage(
            pubkey=config.pubkey,
            disk_name=disk.device,
            total_disk_space=round(utils.bytes_to(disk.total, ByteUnit.GB), 2),
            used_disk_space=round(utils.bytes_to(disk.used, ByteUnit.GB), 2),
            free_disk_space=round(utils.bytes_to(disk.free, ByteUnit.GB), 2),
            service_uptime=ts.service.uptime,
            provider=self._build_provider(),
        )

    def _build_provider(self) -> TelemetryProvider | None:
        tsp = cast("TonStorageProviderModule | None", self.app.modules.get("ton-storage-provider"))
        if tsp is None:
            return None
        config = tsp.get_provider_config()
        return TelemetryProvider(
            pubkey=config.provider_pubkey,
            used_provider_space=round(tsp.get_used_space_gb(), 2),
            total_provider_space=float(config.space_gb),
            max_bag_size_bytes=config.max_bag_size_bytes,
            service_uptime=tsp.service.uptime,
        )

    @staticmethod
    def _build_memory(sample: MemorySample) -> MemoryTelemetry:
        return MemoryTelemetry(
            total=round(utils.bytes_to(sample.total, ByteUnitDec.GB), 2),
            usage=round(utils.bytes_to(sample.used, ByteUnitDec.GB), 2),
            usage_percent=round(sample.percent, 2),
        )

    def _build_benchmark(self) -> BenchmarkPayload | None:
        bench = cast("BenchmarkModule | None", self.app.modules.get("benchmark"))
        tsp = cast("TonStorageProviderModule | None", self.app.modules.get("ton-storage-provider"))
        if bench is None or tsp is None or bench.snapshot is None:
            return None
        snap = bench.snapshot
        return BenchmarkPayload(
            pubkey=tsp.get_provider_config().provider_pubkey,
            timestamp=snap.timestamp,
            disk=DiskBenchmarks.model_validate(snap.disk.model_dump()),
            network=snap.network.model_dump(),
        )

    @staticmethod
    def _build_pings() -> dict[str, float] | None:
        ping_hosts: tuple[str, ...] = (
            "45.129.96.53",
            "5.154.181.153",
            "2.56.126.137",
            "91.194.11.68",
            "45.12.134.214",
            "138.124.184.27",
            "103.106.3.171",
        )
        result: dict[str, float] = {}
        for host in ping_hosts:
            latency = utils.ping_latency(host)
            if latency is not None:
                result[host] = latency
        return result or None

    def _build_versions(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for module in self.app.modules.all():
            if not isinstance(module, Updatable):
                continue
            try:
                result[module.name] = module.version
            except Exception:
                self.logger.exception(f"failed to read version of {module.name}")
        return result

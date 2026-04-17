from __future__ import annotations

import os
import time
from dataclasses import dataclass

from mypycli import Daemonic, Updatable
from mypycli.utils.network import ping_latency
from mypycli.utils.service import SystemdService
from mypycli.utils.sysinfo import sysinfo

from mytonprovider import constants
from mytonprovider.modules.ton_storage.config import StorageConfig
from mytonprovider.modules.ton_storage_provider.config import ProviderConfig
from mytonprovider.utils import read_config

from .api.client import TelemetryApi
from .api.models import (
    BenchmarkPayload,
    CpuTelemetry,
    DiskBenchmark,
    DiskBenchmarks,
    MemoryTelemetry,
    TelemetryPayload,
    TelemetryProvider,
    TelemetryStorage,
    UnameTelemetry,
)

_SENDER_INTERVAL_SEC = 60
_BENCHMARK_INTERVAL_SEC = 24 * 3600
_BYTES_PER_GB = 10**9  # Decimal GB to match legacy mytonprovider wire protocol.


class DaemonicMixin(Daemonic):
    __abstract__ = True

    def on_daemon(self) -> None:
        self.run_cycle(self.sender, seconds=_SENDER_INTERVAL_SEC)

    def sender(self) -> None:
        if not self.db.enabled:
            return
        try:
            payload = self._collect_telemetry()
        except Exception:
            self.logger.exception("telemetry: collect failed")
            return
        try:
            self._api().send_telemetry(payload)
        except Exception:
            self.logger.warning("telemetry: send failed", exc_info=True)
            return
        self.db.last_sent_at = int(time.time())
        self._maybe_send_benchmark()

    def _maybe_send_benchmark(self) -> None:
        now = int(time.time())
        if now - self.db.last_benchmark_sent_at < _BENCHMARK_INTERVAL_SEC:
            return
        payload = self._collect_benchmark()
        if payload is None:
            return
        try:
            self._api().send_benchmark(payload)
        except Exception:
            self.logger.warning("telemetry: benchmark send failed", exc_info=True)
            return
        self.db.last_benchmark_sent_at = now

    def _api(self) -> TelemetryApi:
        return TelemetryApi(
            telemetry_url=self.db.telemetry_url or constants.TELEMETRY_URL,
            benchmark_url=self.db.benchmark_url or constants.BENCHMARK_URL,
        )

    def _collect_telemetry(self) -> TelemetryPayload:
        ts = self.app.modules.get("ton-storage")
        tsp = self.app.modules.get("ton-storage-provider")
        stats = self.app.modules.get("statistics")

        storage = self._storage_section(ts, tsp)
        snapshot = stats.db.snapshot
        net = snapshot.net if snapshot is not None else None

        return TelemetryPayload(
            storage=storage,
            git_hashes=self._collect_git_hashes(),
            net_recv=list(net.recv) if net else [0.0, 0.0, 0.0],
            net_sent=list(net.sent) if net else [0.0, 0.0, 0.0],
            net_load=list(net.load) if net else [0.0, 0.0, 0.0],
            bytes_recv=snapshot.bytes_recv if snapshot else 0,
            bytes_sent=snapshot.bytes_sent if snapshot else 0,
            disks_load={name: list(d.load) for name, d in (snapshot.disks.items() if snapshot else {})},
            disks_load_percent={name: list(d.load_percent) for name, d in (snapshot.disks.items() if snapshot else {})},
            iops={name: list(d.iops) for name, d in (snapshot.disks.items() if snapshot else {})},
            pps=list(net.pps) if net else [0.0, 0.0, 0.0],
            ram=_memory(sysinfo.ram.total, sysinfo.ram.used, sysinfo.ram.percent),
            swap=_memory(sysinfo.swap.total, sysinfo.swap.used, sysinfo.swap.percent),
            uname=_uname(),
            cpu_info=_cpu_info(),
            pings=self._collect_pings(),
            timestamp=int(time.time()),
            telemetry_pass=self.db.password_hash or None,
        )

    def _collect_benchmark(self) -> BenchmarkPayload | None:
        bench = self.app.modules.get("benchmark")
        tsp = self.app.modules.get("ton-storage-provider")
        last = bench.db.last
        if last is None:
            return None
        try:
            cfg = read_config(tsp.db.config_path, ProviderConfig)
            pubkey = cfg.provider_key.public_key.as_hex.upper()
        except Exception:
            self.logger.warning("telemetry: cannot read provider config for benchmark payload", exc_info=True)
            return None
        return BenchmarkPayload(
            pubkey=pubkey,
            timestamp=last.timestamp,
            disk=DiskBenchmarks(
                qd64=DiskBenchmark(
                    name=last.disk.qd64.name,
                    read=last.disk.qd64.read,
                    write=last.disk.qd64.write,
                    read_iops=last.disk.qd64.read_iops,
                    write_iops=last.disk.qd64.write_iops,
                ),
                qd1=DiskBenchmark(
                    name=last.disk.qd1.name,
                    read=last.disk.qd1.read,
                    write=last.disk.qd1.write,
                    read_iops=last.disk.qd1.read_iops,
                    write_iops=last.disk.qd1.write_iops,
                ),
            ),
            network=last.network.model_dump(),
        )

    def _storage_section(self, ts: object, tsp: object) -> TelemetryStorage:
        ts_db = ts.db  # type: ignore[attr-defined]
        tsp_db = tsp.db  # type: ignore[attr-defined]
        # Both configs are mandatory for a complete wire payload; if either is
        # missing we raise so the sender skips this cycle rather than submitting
        # a half-populated record with null ``provider`` or empty ``pubkey``.
        ts_cfg = read_config(ts_db.config_path, StorageConfig)
        tsp_cfg = read_config(tsp_db.config_path, ProviderConfig)

        disk = _disk_info(ts_db.storage_path)
        return TelemetryStorage(
            pubkey=ts_cfg.pubkey_hex,
            disk_name=disk.name,
            total_disk_space=disk.total,
            used_disk_space=disk.used,
            free_disk_space=disk.free,
            service_uptime=SystemdService("ton-storage").uptime,
            provider=TelemetryProvider(
                pubkey=tsp_cfg.provider_key.public_key.as_hex.upper(),
                used_provider_space=_used_provider_space(ts_db.api_host, ts_db.api_port),
                total_provider_space=_total_provider_space(tsp_cfg),
                max_bag_size_bytes=tsp_cfg.max_bag_size_bytes,
                service_uptime=SystemdService("ton-storage-provider").uptime,
            ),
        )

    def _collect_git_hashes(self) -> dict[str, str]:
        updatables: list[Updatable] = self.app.modules.by_interface(Updatable)  # type: ignore[type-abstract]
        return {mod.name: self._safe_version(mod) for mod in updatables}

    def _safe_version(self, mod: Updatable) -> str:
        try:
            return mod.version
        except Exception:
            self.logger.debug("telemetry: version read failed for %s", mod.name, exc_info=True)
            return "unknown"

    def _collect_pings(self) -> dict[str, float] | None:
        result: dict[str, float] = {}
        for host in constants.CHECKER_HOSTS:
            latency = ping_latency(host)
            if latency is None:
                # Match legacy behaviour: drop the whole section if any probe fails.
                return None
            result[host] = latency
        return result


def _memory(total: int, used: int, percent: float) -> MemoryTelemetry:
    return MemoryTelemetry(
        total=round(total / _BYTES_PER_GB, 2),
        usage=round(used / _BYTES_PER_GB, 2),
        usage_percent=round(percent, 2),
    )


def _uname() -> UnameTelemetry:
    u = os.uname()
    # Legacy strips nodename: hostname leaks nothing useful and varies by deployment.
    return UnameTelemetry(sysname=u.sysname, release=u.release, version=u.version, machine=u.machine)


def _cpu_info() -> CpuTelemetry:
    cpu = sysinfo.cpu
    hw = sysinfo.hardware
    return CpuTelemetry(
        cpu_count=cpu.count_logical,
        cpu_load=[cpu.load_1m, cpu.load_5m, cpu.load_15m],
        cpu_name=cpu.name,
        product_name=hw.product_name,
        is_virtual=hw.is_virtualized,
    )


@dataclass(frozen=True)
class _DiskInfo:
    name: str | None
    total: float
    used: float
    free: float


def _disk_info(storage_path: str) -> _DiskInfo:
    if not storage_path:
        return _DiskInfo(name=None, total=0.0, used=0.0, free=0.0)
    try:
        usage = sysinfo.get_disk_usage(storage_path)
    except Exception:
        return _DiskInfo(name=None, total=0.0, used=0.0, free=0.0)
    return _DiskInfo(
        name=usage.device,
        total=round(usage.total / _BYTES_PER_GB, 2),
        used=round(usage.used / _BYTES_PER_GB, 2),
        free=round(usage.free / _BYTES_PER_GB, 2),
    )


def _used_provider_space(api_host: str, api_port: int) -> float:
    if not api_host or not api_port:
        return 0.0
    try:
        from mytonprovider.modules.ton_storage.api.client import StorageApi

        bags = StorageApi(api_host, api_port).list_bags().bags
    except Exception:
        return 0.0
    return round(sum(b.size for b in bags) / _BYTES_PER_GB, 2)


def _total_provider_space(cfg: ProviderConfig) -> float:
    if not cfg.storages:
        return 0.0
    mb = cfg.storages[0].space_to_provide_megabytes
    return round(mb * 1024**2 / _BYTES_PER_GB, 2)

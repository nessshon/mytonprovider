import os
import re
import time
from collections import deque
from typing import ClassVar, Final, cast

from mypycli import Daemonic, utils
from mypycli.types import DiskIO, NetworkIO

from mytonprovider.database import (
    CpuSample,
    DailyTraffic,
    DiskAverages,
    HardwareSample,
    MemorySample,
    MetricsSnapshot,
    NetAverages,
    OsSample,
)


class SysMetricsModule(Daemonic):
    mandatory: ClassVar[bool] = True
    name: ClassVar[str] = "sys-metrics"
    label: ClassVar[str] = "System Metrics"

    REFRESH_SNAPSHOT_INTERVAL_SEC: Final[int] = 10
    SNAPSHOT_TTL_SEC: Final[int] = 12 * REFRESH_SNAPSHOT_INTERVAL_SEC
    TRAFFIC_HISTORY_DAYS: ClassVar[int] = 365
    METRICS_HISTORY_SAMPLES: ClassVar[int] = 15 * 60 // REFRESH_SNAPSHOT_INTERVAL_SEC

    _prev_at: int
    _prev_net: NetworkIO | None
    _prev_disk: dict[str, DiskIO]

    _net_pps: deque[float]
    _net_recv: deque[float]
    _net_sent: deque[float]
    _net_load: deque[float]

    _disk_iops: dict[str, deque[float]]
    _disk_load: dict[str, deque[float]]
    _disk_load_percent: dict[str, deque[float]]

    @property
    def snapshot(self) -> MetricsSnapshot | None:
        snap = self.app.db.modules.sys_metrics.snapshot
        if snap is None or (int(time.time()) - snap.timestamp) > self.SNAPSHOT_TTL_SEC:
            return None
        return cast(MetricsSnapshot, snap)

    def on_daemon(self) -> None:
        self._prev_at = 0
        self._prev_net = None
        self._prev_disk = {}

        self._net_pps = deque(maxlen=self.METRICS_HISTORY_SAMPLES)
        self._net_recv = deque(maxlen=self.METRICS_HISTORY_SAMPLES)
        self._net_sent = deque(maxlen=self.METRICS_HISTORY_SAMPLES)
        self._net_load = deque(maxlen=self.METRICS_HISTORY_SAMPLES)

        self._disk_iops = {}
        self._disk_load = {}
        self._disk_load_percent = {}

        self.run_cycle(self.cycle_refresh_snapshot, seconds=self.REFRESH_SNAPSHOT_INTERVAL_SEC)

    def cycle_refresh_snapshot(self) -> None:
        now = int(time.time())
        iface = utils.get_network_interface()
        net = utils.sysinfo.get_network_io(iface) if iface else None
        if net is None:
            self.logger.warning("no network interface; skipping cycle")
            return

        dt = now - self._prev_at
        self._update_network(net, dt)
        self._update_disks(dt)
        self._prev_at = now

        snapshot = self._build_snapshot(now, net)
        self.app.db.modules.sys_metrics.snapshot = snapshot
        self._record_daily(snapshot)

    def _update_network(self, net: NetworkIO, dt: int) -> None:
        if self._prev_net is not None and dt > 0:
            recv = (net.bytes_recv - self._prev_net.bytes_recv) * 8 / dt / 1000**2
            sent = (net.bytes_sent - self._prev_net.bytes_sent) * 8 / dt / 1000**2
            pps = (net.packets_recv - self._prev_net.packets_recv + net.packets_sent - self._prev_net.packets_sent) / dt
            self._net_recv.append(recv)
            self._net_sent.append(sent)
            self._net_load.append(recv + sent)
            self._net_pps.append(pps)
        self._prev_net = net

    def _update_disks(self, dt: int) -> None:
        try:
            block_devices = os.listdir("/sys/block")
        except FileNotFoundError:
            block_devices = []

        disk_blacklist_re: Final[re.Pattern[str]] = re.compile(r"^(loop|ram|zram|md|dm-|fd|sr)")
        known = {
            name for name in block_devices if not disk_blacklist_re.match(name) and name in utils.sysinfo.all_disk_io
        }
        for stale in self._disk_load.keys() - known:
            self._prev_disk.pop(stale, None)
            self._disk_load.pop(stale, None)
            self._disk_load_percent.pop(stale, None)
            self._disk_iops.pop(stale, None)

        for disk in known:
            cur = utils.sysinfo.get_disk_io(disk)
            if cur is None:
                continue
            prev = self._prev_disk.get(disk)
            if prev is not None and dt > 0:
                iops = (cur.read_count - prev.read_count + cur.write_count - prev.write_count) / dt
                load = (cur.read_bytes - prev.read_bytes + cur.write_bytes - prev.write_bytes) / dt / 1024**2
                pct = (cur.busy_time_ms - prev.busy_time_ms) / 1000 / dt * 100
                self._disk_iops.setdefault(disk, deque(maxlen=self.METRICS_HISTORY_SAMPLES)).append(iops)
                self._disk_load.setdefault(disk, deque(maxlen=self.METRICS_HISTORY_SAMPLES)).append(load)
                self._disk_load_percent.setdefault(disk, deque(maxlen=self.METRICS_HISTORY_SAMPLES)).append(pct)
            self._prev_disk[disk] = cur

    def _build_snapshot(self, now: int, net: NetworkIO) -> MetricsSnapshot:
        sysinfo = utils.sysinfo
        return MetricsSnapshot(
            timestamp=now,
            net=NetAverages(
                recv=self._load_averages(self._net_recv),
                sent=self._load_averages(self._net_sent),
                load=self._load_averages(self._net_load),
                pps=self._load_averages(self._net_pps),
            ),
            disks={
                disk: DiskAverages(
                    load=self._load_averages(self._disk_load[disk]),
                    load_percent=self._load_averages(self._disk_load_percent[disk]),
                    iops=self._load_averages(self._disk_iops[disk]),
                )
                for disk in self._disk_load
                if disk in self._prev_disk and self._prev_disk[disk].busy_time_ms > 0
            },
            bytes_recv=net.bytes_recv,
            bytes_sent=net.bytes_sent,
            ram=MemorySample(total=sysinfo.ram.total, used=sysinfo.ram.used, percent=sysinfo.ram.percent),
            swap=MemorySample(total=sysinfo.swap.total, used=sysinfo.swap.used, percent=sysinfo.swap.percent),
            cpu=CpuSample(
                name=sysinfo.cpu.name,
                count_logical=sysinfo.cpu.count_logical,
                load=(sysinfo.cpu.load_1m, sysinfo.cpu.load_5m, sysinfo.cpu.load_15m),
            ),
            os=OsSample(
                sysname=sysinfo.os.name,
                release=sysinfo.os.release,
                version=sysinfo.os.version,
                machine=sysinfo.os.arch,
            ),
            hardware=HardwareSample(
                product_name=sysinfo.hardware.product_name,
                is_virtual=sysinfo.hardware.is_virtualized,
            ),
        )

    def _record_daily(self, snapshot: MetricsSnapshot) -> None:
        day = str(snapshot.timestamp // 86400)
        daily = dict(self.app.db.modules.sys_metrics.daily_traffic)
        daily[day] = DailyTraffic(
            timestamp=snapshot.timestamp,
            bytes_recv=snapshot.bytes_recv,
            bytes_sent=snapshot.bytes_sent,
        )
        if len(daily) > self.TRAFFIC_HISTORY_DAYS:
            keep = sorted(daily, key=int, reverse=True)[: self.TRAFFIC_HISTORY_DAYS]
            daily = {k: daily[k] for k in keep}
        self.app.db.modules.sys_metrics.daily_traffic = daily

    def _load_averages(self, rates: deque[float]) -> tuple[float, float, float]:
        r = list(rates)
        per_min = 60 // self.REFRESH_SNAPSHOT_INTERVAL_SEC

        def avg(n: int) -> float:
            return round(sum(r[-n:]) / min(n, len(r)), 2) if r else 0.0

        return avg(per_min), avg(5 * per_min), avg(self.METRICS_HISTORY_SAMPLES)

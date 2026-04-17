from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mypycli import Daemonic
from mypycli.utils.network import get_network_interface
from mypycli.utils.sysinfo import sysinfo

from .schemas import DailyTraffic, DiskAverages, NetAverages, StatsSnapshot

if TYPE_CHECKING:
    from mypycli.types import DiskIO, NetworkIO

_SAMPLE_INTERVAL_SEC = 10
_SAMPLES_PER_MINUTE = 6
_WINDOW_MINUTES = 15
_BUFFER_SIZE = _SAMPLES_PER_MINUTE * _WINDOW_MINUTES  # 90
_IDX_1M = _SAMPLES_PER_MINUTE * 1 - 1  # 5
_IDX_5M = _SAMPLES_PER_MINUTE * 5 - 1  # 29
_IDX_15M = _SAMPLES_PER_MINUTE * 15 - 1  # 89
_DAILY_HISTORY_DAYS = 365
_SECONDS_PER_DAY = 86400


@dataclass(frozen=True)
class _NetSample:
    at: int
    io: NetworkIO


@dataclass(frozen=True)
class _DiskSample:
    at: int
    io: DiskIO


class DaemonicMixin(Daemonic):
    __abstract__ = True

    _net_ring: list[_NetSample | None]
    _disk_ring: dict[str, list[_DiskSample | None]]

    def on_daemon(self) -> None:
        self._net_ring = [None] * _BUFFER_SIZE
        self._disk_ring = {}
        self.run_cycle(self.sampler, seconds=_SAMPLE_INTERVAL_SEC)

    def sampler(self) -> None:
        now = int(time.time())
        iface = get_network_interface()
        net_io = sysinfo.get_network_io(iface) if iface else None
        if net_io is None:
            return

        self._net_ring.pop(0)
        self._net_ring.append(_NetSample(at=now, io=net_io))

        known_disks = set(_list_disks())
        # Drop rings for disks that disappeared (unmounted / hot-swapped out).
        for stale in self._disk_ring.keys() - known_disks:
            del self._disk_ring[stale]
        for disk in known_disks:
            disk_io = sysinfo.get_disk_io(disk)
            if disk_io is None:
                continue
            ring = self._disk_ring.setdefault(disk, [None] * _BUFFER_SIZE)
            ring.pop(0)
            ring.append(_DiskSample(at=now, io=disk_io))

        self.db.snapshot = StatsSnapshot(
            timestamp=now,
            net=self._net_averages(),
            disks={name: self._disk_averages(ring) for name, ring in self._disk_ring.items()},
            bytes_recv=net_io.bytes_recv,
            bytes_sent=net_io.bytes_sent,
        )
        self._record_daily(now, net_io)

    def _net_averages(self) -> NetAverages | None:
        reversed_buf = list(reversed(self._net_ring))
        zero = reversed_buf[0]
        if zero is None:
            return None
        b1 = reversed_buf[_IDX_1M]
        b5 = reversed_buf[_IDX_5M] or b1
        b15 = reversed_buf[_IDX_15M] or b5
        r1, s1, l1, p1 = _net_window(zero, b1)
        r5, s5, l5, p5 = _net_window(zero, b5)
        r15, s15, l15, p15 = _net_window(zero, b15)
        return NetAverages(
            recv=(r1, r5, r15),
            sent=(s1, s5, s15),
            load=(l1, l5, l15),
            pps=(p1, p5, p15),
        )

    @staticmethod
    def _disk_averages(ring: list[_DiskSample | None]) -> DiskAverages:
        reversed_buf = list(reversed(ring))
        zero = reversed_buf[0]
        if zero is None:
            return DiskAverages()
        b1 = reversed_buf[_IDX_1M]
        b5 = reversed_buf[_IDX_5M] or b1
        b15 = reversed_buf[_IDX_15M] or b5
        l1, p1, i1 = _disk_window(zero, b1)
        l5, p5, i5 = _disk_window(zero, b5)
        l15, p15, i15 = _disk_window(zero, b15)
        return DiskAverages(
            load=(l1, l5, l15),
            load_percent=(p1, p5, p15),
            iops=(i1, i5, i15),
        )

    def _record_daily(self, now: int, net_io: NetworkIO) -> None:
        day_key = str(now // _SECONDS_PER_DAY)
        daily = dict(self.db.daily_traffic)
        daily[day_key] = DailyTraffic(
            timestamp=now,
            bytes_recv=net_io.bytes_recv,
            bytes_sent=net_io.bytes_sent,
        )
        if len(daily) > _DAILY_HISTORY_DAYS:
            keep = sorted(daily.keys(), key=int, reverse=True)[:_DAILY_HISTORY_DAYS]
            daily = {k: daily[k] for k in keep}
        self.db.daily_traffic = daily


def _list_disks() -> list[str]:
    return sorted(name for name in sysinfo.all_disk_io if "loop" not in name)


def _net_window(zero: _NetSample, past: _NetSample | None) -> tuple[float, float, float, float]:
    if past is None:
        return 0.0, 0.0, 0.0, 0.0
    dt = zero.at - past.at
    if dt <= 0:
        return 0.0, 0.0, 0.0, 0.0
    recv_mbit = (zero.io.bytes_recv - past.io.bytes_recv) * 8 / dt / 1024**2
    sent_mbit = (zero.io.bytes_sent - past.io.bytes_sent) * 8 / dt / 1024**2
    pps = (zero.io.packets_recv - past.io.packets_recv + zero.io.packets_sent - past.io.packets_sent) / dt
    return (
        round(recv_mbit, 2),
        round(sent_mbit, 2),
        round(recv_mbit + sent_mbit, 2),
        round(pps, 2),
    )


def _disk_window(zero: _DiskSample, past: _DiskSample | None) -> tuple[float, float, float]:
    if past is None:
        return 0.0, 0.0, 0.0
    dt = zero.at - past.at
    if dt <= 0:
        return 0.0, 0.0, 0.0
    load_mb = (zero.io.read_bytes - past.io.read_bytes + zero.io.write_bytes - past.io.write_bytes) / dt / 1024**2
    load_pct = (zero.io.busy_time_ms - past.io.busy_time_ms) / 1000 / dt * 100
    iops = (zero.io.read_count - past.io.read_count + zero.io.write_count - past.io.write_count) / dt
    return round(load_mb, 2), round(load_pct, 2), round(iops, 2)

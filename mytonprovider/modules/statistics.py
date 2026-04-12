from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Final, cast

import psutil
from mypylib import (
    ByteUnit,
    Dict,
    convert_bytes,
    get_internet_interface_name,
    get_timestamp,
    print_table,
)

from mytonprovider.modules.core import Commandable, Daemonic
from mytonprovider.types import Command

if TYPE_CHECKING:
    from mypylib import MyPyClass


# Daemon timing
DAEMON_INTERVAL_SEC: Final[int] = 10
SAMPLES_PER_MIN: Final[int] = 60 // DAEMON_INTERVAL_SEC  # 6

# Buffer sizes (15 min window)
BUFFER_MINUTES: Final[int] = 15
BUFFER_SIZE: Final[int] = SAMPLES_PER_MIN * BUFFER_MINUTES  # 90

# Window slice indices for 1m / 5m / 15m averages (on reversed buffer)
WINDOW_1MIN_INDEX: Final[int] = SAMPLES_PER_MIN - 1  # 5
WINDOW_5MIN_INDEX: Final[int] = SAMPLES_PER_MIN * 5 - 1  # 29
WINDOW_15MIN_INDEX: Final[int] = SAMPLES_PER_MIN * 15 - 1  # 89

# Stats freshness
STATS_LIFETIME_SEC: Final[int] = 120

# Daily statistics retention
DAILY_STATS_MAX_DAYS: Final[int] = 365

# Seconds per day (for `days since epoch`)
SECONDS_PER_DAY: Final[int] = 86400

# Disk discovery
BLOCK_DEVICES_DIR: Final[str] = "/sys/block"


class StatisticsModule(Daemonic, Commandable):
    """Collects network and disk I/O metrics every ``DAEMON_INTERVAL_SEC``."""

    name = "statistics"
    mandatory = True
    daemon_interval = DAEMON_INTERVAL_SEC

    def __init__(self, app: MyPyClass) -> None:
        super().__init__(app)
        self._network_buffer: list[Dict | None] = [None] * BUFFER_SIZE
        self._diskio_buffer: list[dict[str, Dict] | None] = [None] * BUFFER_SIZE

    def daemon(self) -> None:
        """Read current counters and persist aggregated statistics to DB."""
        self._read_network_data()
        self._save_network_statistics()
        self._read_disk_data()
        self._save_disk_statistics()

    def get_commands(self) -> list[Command]:
        return [
            Command(
                name="network_status",
                func=self._print_network_status,
                description=self.app.translate("network_status_cmd"),
            ),
        ]

    def get_net_recv_avg(self) -> list[float]:
        """Return [1m, 5m, 15m] download averages in Mbit/s."""
        return cast("list[float]", self._get_stats("net_recv_avg"))

    def get_net_sent_avg(self) -> list[float]:
        """Return [1m, 5m, 15m] upload averages in Mbit/s."""
        return cast("list[float]", self._get_stats("net_sent_avg"))

    def get_net_load_avg(self) -> list[float]:
        """Return [1m, 5m, 15m] total network load averages in Mbit/s."""
        return cast("list[float]", self._get_stats("net_load_avg"))

    def get_pps_avg(self) -> list[float]:
        """Return [1m, 5m, 15m] packets-per-second averages."""
        return cast("list[float]", self._get_stats("pps_avg"))

    def get_bytes_recv(self) -> int:
        """Return total received bytes counter."""
        return cast("int", self._get_stats("bytes_recv"))

    def get_bytes_sent(self) -> int:
        """Return total sent bytes counter."""
        return cast("int", self._get_stats("bytes_sent"))

    def get_disks_load_avg(self) -> dict[str, list[float]]:
        """Return disk load averages ``{disk: [1m, 5m, 15m]}`` in MB/s."""
        return cast("dict[str, list[float]]", self._get_stats("disks_load_avg"))

    def get_disks_load_percent_avg(self) -> dict[str, list[float]]:
        """Return disk busy percent ``{disk: [1m, 5m, 15m]}``."""
        return cast("dict[str, list[float]]", self._get_stats("disks_load_percent_avg"))

    def get_iops_avg(self) -> dict[str, list[float]]:
        """Return disk IOPS averages ``{disk: [1m, 5m, 15m]}``."""
        return cast("dict[str, list[float]]", self._get_stats("iops_avg"))

    def _get_stats(self, name: str) -> Any:
        """Return a statistics value; raise if data is missing or stale."""
        stats = self.app.db.statistics
        if stats is None:
            raise RuntimeError(f"{self.name}: statistics data is not available")
        if stats.timestamp + STATS_LIFETIME_SEC < get_timestamp():
            raise RuntimeError(f"{self.name}: statistics data is stale")
        return stats.get(name)

    @staticmethod
    def _get_days_since_epoch() -> int:
        return get_timestamp() // SECONDS_PER_DAY

    def _get_daily_statistics_data(self, comparing_days: int) -> Dict:
        """Compare today's bytes counters with those from ``comparing_days`` ago."""
        if self.app.db.daily_statistics is None:
            raise RuntimeError(f"{self.name}: daily_statistics data is not available")

        data = Dict()
        data.recv = None
        data.sent = None
        data.total = None

        days = self._get_days_since_epoch()
        zero_day = self.app.db.daily_statistics.get(str(days))
        comparing_day = self.app.db.daily_statistics.get(str(days - comparing_days))

        if zero_day is None:
            raise RuntimeError(f"{self.name}: no data for the current day")
        if comparing_day is None:
            return data

        data.recv = convert_bytes(zero_day.bytes_recv - comparing_day.bytes_recv, ByteUnit.GB)
        data.sent = convert_bytes(zero_day.bytes_sent - comparing_day.bytes_sent, ByteUnit.GB)
        data.total = round(data.recv + data.sent, 2)
        return data

    def _read_network_data(self) -> None:
        """Append a fresh network counter snapshot to the buffer."""
        interface = get_internet_interface_name()
        counters = psutil.net_io_counters(pernic=True)[interface]
        sample = Dict()
        sample.timestamp = get_timestamp()
        sample.bytes_recv = counters.bytes_recv
        sample.bytes_sent = counters.bytes_sent
        sample.packets_recv = counters.packets_recv
        sample.packets_sent = counters.packets_sent
        self._network_buffer.pop(0)
        self._network_buffer.append(sample)

    def _save_network_statistics(self) -> None:
        """Compute 1m/5m/15m network averages and persist them to DB."""
        buffer = self._network_buffer[::-1]
        zero = buffer[0]
        if zero is None:
            return

        buff_1m = buffer[WINDOW_1MIN_INDEX]
        buff_5m = buffer[WINDOW_5MIN_INDEX] or buff_1m
        buff_15m = buffer[WINDOW_15MIN_INDEX] or buff_5m

        recv_1, sent_1, load_1, pps_1 = self._calculate_network_statistics(zero, buff_1m)
        recv_5, sent_5, load_5, pps_5 = self._calculate_network_statistics(zero, buff_5m)
        recv_15, sent_15, load_15, pps_15 = self._calculate_network_statistics(zero, buff_15m)

        stats = self.app.db.get("statistics", Dict())
        stats.timestamp = get_timestamp()
        stats.net_recv_avg = [recv_1, recv_5, recv_15]
        stats.net_sent_avg = [sent_1, sent_5, sent_15]
        stats.net_load_avg = [load_1, load_5, load_15]
        stats.pps_avg = [pps_1, pps_5, pps_15]
        stats.bytes_recv = zero.bytes_recv
        stats.bytes_sent = zero.bytes_sent
        self.app.db.statistics = stats

        daily_stats = self.app.db.get("daily_statistics", Dict())
        snapshot = Dict()
        snapshot.timestamp = get_timestamp()
        snapshot.bytes_recv = zero.bytes_recv
        snapshot.bytes_sent = zero.bytes_sent
        daily_stats[str(self._get_days_since_epoch())] = snapshot
        self.app.db.daily_statistics = daily_stats

        self._trim_daily_statistics()

    @staticmethod
    def _calculate_network_statistics(
        zero: Dict,
        prev: Dict | None,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        """Return ``(recv_mbit, sent_mbit, load_mbit, pps)`` between two samples."""
        if prev is None:
            return None, None, None, None
        time_diff = zero.timestamp - prev.timestamp
        if time_diff == 0:
            return None, None, None, None

        bits_recv = (zero.bytes_recv - prev.bytes_recv) / time_diff * 8
        bits_sent = (zero.bytes_sent - prev.bytes_sent) / time_diff * 8
        packets_recv = (zero.packets_recv - prev.packets_recv) / time_diff
        packets_sent = (zero.packets_sent - prev.packets_sent) / time_diff

        return (
            convert_bytes(bits_recv, ByteUnit.MB),
            convert_bytes(bits_sent, ByteUnit.MB),
            convert_bytes(bits_recv + bits_sent, ByteUnit.MB),
            round(packets_recv + packets_sent, 2),
        )

    def _trim_daily_statistics(self) -> None:
        """Keep only the most recent ``DAILY_STATS_MAX_DAYS`` entries."""
        daily_stats = self.app.db.daily_statistics
        if daily_stats is None or len(daily_stats) <= DAILY_STATS_MAX_DAYS:
            return
        sorted_keys = sorted(daily_stats.keys(), key=int, reverse=True)
        for stale_key in sorted_keys[DAILY_STATS_MAX_DAYS:]:
            del daily_stats[stale_key]

    def _read_disk_data(self) -> None:
        """Append a fresh disk I/O counter snapshot to the buffer."""
        timestamp = get_timestamp()
        counters = psutil.disk_io_counters(perdisk=True)
        snapshot: dict[str, Dict] = {}
        for name in self._get_disks_list():
            counter = counters[name]
            disk = Dict()
            disk.timestamp = timestamp
            disk.busy_time = counter.busy_time  # type: ignore[attr-defined]
            disk.read_bytes = counter.read_bytes
            disk.write_bytes = counter.write_bytes
            disk.read_count = counter.read_count
            disk.write_count = counter.write_count
            snapshot[name] = disk
        self._diskio_buffer.pop(0)
        self._diskio_buffer.append(snapshot)

    def _save_disk_statistics(self) -> None:
        """Compute 1m/5m/15m disk averages and persist them to DB."""
        buffer = self._diskio_buffer[::-1]
        zero = buffer[0]
        if zero is None:
            return

        buff_1m = buffer[WINDOW_1MIN_INDEX]
        buff_5m = buffer[WINDOW_5MIN_INDEX] or buff_1m
        buff_15m = buffer[WINDOW_15MIN_INDEX] or buff_5m

        disks_load_avg: dict[str, list[float | None]] = {}
        disks_load_percent_avg: dict[str, list[float | None]] = {}
        iops_avg: dict[str, list[float | None]] = {}

        for name in self._get_disks_list():
            if zero[name].busy_time == 0:
                continue
            load_1, percent_1, iops_1 = self._calculate_disk_statistics(zero, buff_1m, name)
            load_5, percent_5, iops_5 = self._calculate_disk_statistics(zero, buff_5m, name)
            load_15, percent_15, iops_15 = self._calculate_disk_statistics(zero, buff_15m, name)
            disks_load_avg[name] = [load_1, load_5, load_15]
            disks_load_percent_avg[name] = [percent_1, percent_5, percent_15]
            iops_avg[name] = [iops_1, iops_5, iops_15]

        stats = self.app.db.get("statistics", Dict())
        stats.timestamp = get_timestamp()
        stats.disks_load_avg = disks_load_avg
        stats.disks_load_percent_avg = disks_load_percent_avg
        stats.iops_avg = iops_avg
        self.app.db.statistics = stats

    @staticmethod
    def _calculate_disk_statistics(
        zero: dict[str, Dict],
        prev: dict[str, Dict] | None,
        name: str,
    ) -> tuple[float | None, float | None, float | None]:
        """Return ``(load_mb, busy_percent, iops)`` for one disk between two samples."""
        if prev is None:
            return None, None, None
        zero_disk = zero[name]
        prev_disk = prev[name]
        time_diff = zero_disk.timestamp - prev_disk.timestamp
        if time_diff == 0:
            return None, None, None

        busy_diff = zero_disk.busy_time - prev_disk.busy_time
        read_diff = zero_disk.read_bytes - prev_disk.read_bytes
        write_diff = zero_disk.write_bytes - prev_disk.write_bytes
        read_count_diff = zero_disk.read_count - prev_disk.read_count
        write_count_diff = zero_disk.write_count - prev_disk.write_count

        load_percent = round(busy_diff / 1000 / time_diff * 100, 2)
        load = convert_bytes((read_diff + write_diff) / time_diff, ByteUnit.MB)
        iops = round((read_count_diff + write_count_diff) / time_diff, 2)
        return load, load_percent, iops

    @staticmethod
    def _get_disks_list() -> list[str]:
        """Return sorted list of non-loop block devices."""
        return sorted(entry for entry in os.listdir(BLOCK_DEVICES_DIR) if "loop" not in entry)

    def _print_network_status(self, args: list[str]) -> None:
        """Print current network speed and daily traffic tables."""
        net_recv_avg = self.get_net_recv_avg()
        net_sent_avg = self.get_net_sent_avg()
        net_load_avg = self.get_net_load_avg()

        speed_table: list[list[Any]] = [
            ["Network speed", "Download", "Upload", "Total"],
            [
                "1 minute",
                f"{net_recv_avg[0]} Mbit/s",
                f"{net_sent_avg[0]} Mbit/s",
                f"{net_load_avg[0]} Mbit/s",
            ],
            [
                "5 minutes",
                f"{net_recv_avg[1]} Mbit/s",
                f"{net_sent_avg[1]} Mbit/s",
                f"{net_load_avg[1]} Mbit/s",
            ],
            [
                "15 minutes",
                f"{net_recv_avg[2]} Mbit/s",
                f"{net_sent_avg[2]} Mbit/s",
                f"{net_load_avg[2]} Mbit/s",
            ],
        ]
        print_table(speed_table)
        print()

        data1 = self._get_daily_statistics_data(comparing_days=1)
        data7 = self._get_daily_statistics_data(comparing_days=7)
        data30 = self._get_daily_statistics_data(comparing_days=30)
        traffic_table: list[list[Any]] = [
            ["Network traffic", "Download", "Upload", "Total"],
            ["1 day", f"{data1.recv} GB", f"{data1.sent} GB", f"{data1.total} GB"],
            ["7 days", f"{data7.recv} GB", f"{data7.sent} GB", f"{data7.total} GB"],
            ["30 days", f"{data30.recv} GB", f"{data30.sent} GB", f"{data30.total} GB"],
        ]
        print_table(traffic_table)

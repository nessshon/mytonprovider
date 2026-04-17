from __future__ import annotations

from mypycli import DatabaseSchema
from pydantic import BaseModel, Field


class NetAverages(BaseModel):
    """Rolling network averages over 1-, 5-, and 15-minute windows."""

    recv: tuple[float, float, float] = (0.0, 0.0, 0.0)  # Mbit/s
    sent: tuple[float, float, float] = (0.0, 0.0, 0.0)  # Mbit/s
    load: tuple[float, float, float] = (0.0, 0.0, 0.0)  # Mbit/s (recv + sent)
    pps: tuple[float, float, float] = (0.0, 0.0, 0.0)  # packets/sec


class DiskAverages(BaseModel):
    """Rolling disk I/O averages over 1-, 5-, and 15-minute windows."""

    load: tuple[float, float, float] = (0.0, 0.0, 0.0)  # MB/s (read + write)
    load_percent: tuple[float, float, float] = (0.0, 0.0, 0.0)  # %
    iops: tuple[float, float, float] = (0.0, 0.0, 0.0)


class StatsSnapshot(BaseModel):
    """Most recent computed averages plus cumulative counters; refreshed every sampler tick."""

    timestamp: int = 0
    net: NetAverages | None = None
    disks: dict[str, DiskAverages] = Field(default_factory=dict)
    bytes_recv: int = 0
    bytes_sent: int = 0


class DailyTraffic(BaseModel):
    """End-of-day snapshot of cumulative network counters used for 1d/7d/30d traffic deltas."""

    timestamp: int
    bytes_recv: int
    bytes_sent: int


class StatisticsDBSchema(DatabaseSchema):
    """Persistent state: latest snapshot for REPL/status IPC + 365-day traffic history."""

    snapshot: StatsSnapshot | None = None
    daily_traffic: dict[str, DailyTraffic] = Field(default_factory=dict)

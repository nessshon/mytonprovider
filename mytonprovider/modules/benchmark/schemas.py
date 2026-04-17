from __future__ import annotations

from mypycli import DatabaseSchema
from pydantic import BaseModel, ConfigDict


class FioResult(BaseModel):
    """Bandwidth + IOPS from one fio run; values are raw strings from fio output."""

    name: str
    read: str
    read_iops: str
    write: str
    write_iops: str


class BenchmarkDisk(BaseModel):
    qd64: FioResult
    qd1: FioResult


class BenchmarkNetwork(BaseModel):
    """Subset of speedtest-cli results; extra fields preserved for byte-for-byte upload."""

    model_config = ConfigDict(extra="allow")

    download: float = 0.0
    upload: float = 0.0
    ping: float = 0.0


class BenchmarkResult(BaseModel):
    timestamp: int
    disk: BenchmarkDisk
    network: BenchmarkNetwork


class BenchmarkDBSchema(DatabaseSchema):
    """Persistent cache of the last benchmark run (≤ 7 days before auto-refresh)."""

    last: BenchmarkResult | None = None

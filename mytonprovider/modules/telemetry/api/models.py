from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class TelemetryProvider(_BaseModel):
    pubkey: str
    used_provider_space: float
    total_provider_space: float
    max_bag_size_bytes: int
    service_uptime: int | None = None


class TelemetryStorage(_BaseModel):
    pubkey: str
    disk_name: str | None = None
    total_disk_space: float
    used_disk_space: float
    free_disk_space: float
    service_uptime: int | None = None
    provider: TelemetryProvider | None = None


class CpuTelemetry(_BaseModel):
    cpu_count: int
    cpu_load: list[float]
    cpu_name: str | None = None
    product_name: str | None = None
    is_virtual: bool | None = None


class MemoryTelemetry(_BaseModel):
    total: float
    usage: float
    usage_percent: float


class UnameTelemetry(_BaseModel):
    sysname: str
    release: str
    version: str
    machine: str


class TelemetryPayload(_BaseModel):
    storage: TelemetryStorage
    git_hashes: dict[str, str] = Field(default_factory=dict)
    net_recv: list[float]
    net_sent: list[float]
    net_load: list[float]
    bytes_recv: int
    bytes_sent: int
    disks_load: dict[str, list[float]] = Field(default_factory=dict)
    disks_load_percent: dict[str, list[float]] = Field(default_factory=dict)
    iops: dict[str, list[float]] = Field(default_factory=dict)
    pps: list[float]
    ram: MemoryTelemetry
    swap: MemoryTelemetry
    uname: UnameTelemetry
    cpu_info: CpuTelemetry
    pings: dict[str, float] | None = None
    timestamp: int
    telemetry_pass: str | None = None


class DiskBenchmark(_BaseModel):
    name: str
    read: str
    write: str
    read_iops: str
    write_iops: str


class DiskBenchmarks(_BaseModel):
    qd64: DiskBenchmark
    qd1: DiskBenchmark


class BenchmarkPayload(_BaseModel):
    pubkey: str
    timestamp: int
    disk: DiskBenchmarks
    network: dict[str, Any] = Field(default_factory=dict)

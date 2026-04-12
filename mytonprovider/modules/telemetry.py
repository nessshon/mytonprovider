from __future__ import annotations

import base64
import gzip
import hashlib
import json
from contextlib import contextmanager
from getpass import getpass
from typing import TYPE_CHECKING, Any, Final

import psutil
import requests
from mypylib import (
    DEBUG,
    ERROR,
    ByteUnit,
    color_print,
    get_cpu_count,
    get_cpu_name,
    get_disk_device,
    get_disk_space,
    get_hardware_name,
    get_load_avg,
    get_pings,
    get_service_uptime,
    get_timestamp,
    get_uname,
    is_hardware_virtualized,
)

from mytonprovider import constants
from mytonprovider.modules.core import (
    Commandable,
    Daemonic,
    Updatable,
)
from mytonprovider.modules.statistics import StatisticsModule
from mytonprovider.modules.ton_storage import TonStorageModule
from mytonprovider.modules.ton_storage_provider import TonStorageProviderModule
from mytonprovider.types import Command

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mypylib import MyPyClass


# Daemon interval and send thresholds
DAEMON_INTERVAL_SEC: Final[int] = 60
BENCHMARK_SEND_INTERVAL_SEC: Final[int] = 86400  # 24 hours
TELEMETRY_TIMEOUT_SEC: Final[float] = 3.0

# Old payload reports RAM/swap in decimal GB (bytes / 10**9), not binary.
# Kept 1:1 with the old server contract.
BYTES_PER_GB_DECIMAL: Final[int] = 10**9


class TelemetryModule(Daemonic, Commandable):
    """Periodically send node telemetry and benchmark data to mytonprovider.org."""

    name = "telemetry"
    mandatory = False
    daemon_interval = DAEMON_INTERVAL_SEC

    def __init__(self, app: MyPyClass) -> None:
        super().__init__(app)
        self._last_benchmark_send: int = 0

    @property
    def is_enabled(self) -> bool:
        return bool(self.app.db.get("telemetry_enabled"))

    def daemon(self) -> None:
        try:
            telemetry_data = self._collect_telemetry_data()
            self._send_data(constants.TELEMETRY_URL, telemetry_data)
        except Exception as exc:
            self.app.add_log(f"telemetry send failed: {exc}", ERROR)

        now = get_timestamp()
        if self._last_benchmark_send + BENCHMARK_SEND_INTERVAL_SEC < now:
            try:
                benchmark_data = self._collect_benchmark_data()
                if benchmark_data is not None:
                    self._send_data(constants.BENCHMARK_URL, benchmark_data)
                    self._last_benchmark_send = now
            except Exception as exc:
                self.app.add_log(f"benchmark send failed: {exc}", ERROR)

    def get_commands(self) -> list[Command]:
        return [
            Command(
                name="set_telemetry_password",
                func=self._cmd_set_telemetry_password,
                description=self.app.translate("set_telemetry_password_cmd"),
            ),
        ]

    def _cmd_set_telemetry_password(self, args: list[str]) -> None:
        passwd = getpass("Set a new password for the telemetry data: ")
        repasswd = getpass("Repeat password: ")
        if passwd != repasswd:
            color_print("{red}Error: password mismatch{endc}")
            return
        self.app.db.telemetry_password_hash = self._hash_password(passwd)
        self.app.save()
        color_print("telemetry password {green}OK{endc}")

    @staticmethod
    def _hash_password(passwd: str) -> str:
        """Return ``sha256(telemetry_url + passwd)`` base64-encoded."""
        data = (constants.TELEMETRY_URL + passwd).encode("utf-8")
        digest = hashlib.sha256(data).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _send_data(self, url: str, data: dict[str, Any]) -> None:
        """POST gzip-compressed JSON payload to the telemetry API."""
        payload = gzip.compress(json.dumps(data).encode("utf-8"))
        headers = {
            "Content-Encoding": "gzip",
            "Content-Type": "application/json",
        }
        requests.post(url, data=payload, headers=headers, timeout=TELEMETRY_TIMEOUT_SEC)

    @contextmanager
    def _log_on_error(self, label: str) -> Iterator[None]:
        """Swallow and log exceptions so one bad field doesn't drop the whole payload."""
        try:
            yield
        except Exception as exc:
            self.app.add_log(f"telemetry: {label} failed: {exc}", DEBUG)

    def _collect_telemetry_data(self) -> dict[str, Any]:
        """Build the telemetry payload matching the old server contract 1:1."""
        statistics = self.registry.get_by_class(StatisticsModule)
        return {
            "storage": self._collect_storage_section(),
            "git_hashes": self._collect_versions(),
            **self._collect_statistics(statistics),
            "ram": self._collect_ram(),
            "swap": self._collect_swap(),
            "uname": self._collect_uname(),
            "cpu_info": self._collect_cpu_info(),
            "pings": self._collect_pings(),
            "timestamp": get_timestamp(),
            # Old payload key ``telemetry_pass`` — new internal name is
            # ``telemetry_password_hash``.
            "telemetry_pass": self.app.db.get("telemetry_password_hash"),
        }

    def _collect_storage_section(self) -> dict[str, Any]:
        """Build the ``storage`` section (includes nested ``provider``)."""
        ton_storage = self.registry.get_by_class(TonStorageModule)
        storage_path = (
            self.app.db.ton_storage.storage_path if self.app.db.ton_storage else None
        )

        section: dict[str, Any] = {
            "pubkey": None,
            "disk_name": None,
            "total_disk_space": None,
            "used_disk_space": None,
            "free_disk_space": None,
            "service_uptime": None,
        }

        with self._log_on_error("storage pubkey"):
            section["pubkey"] = ton_storage.get_storage_pubkey()

        if storage_path:
            with self._log_on_error("storage disk_name"):
                section["disk_name"] = get_disk_device(storage_path)
            with self._log_on_error("storage disk_space"):
                disk = get_disk_space(storage_path, unit=ByteUnit.GB, ndigits=2)
                section["total_disk_space"] = disk.total
                section["used_disk_space"] = disk.used
                section["free_disk_space"] = disk.free

        with self._log_on_error("storage service_uptime"):
            section["service_uptime"] = get_service_uptime(ton_storage.service_name)

        section["provider"] = self._collect_provider_section()
        return section

    def _collect_provider_section(self) -> dict[str, Any]:
        """Build the ``storage.provider`` sub-section."""
        ton_storage = self.registry.get_by_class(TonStorageModule)
        provider = self.registry.get_by_class(TonStorageProviderModule)

        section: dict[str, Any] = {
            "pubkey": None,
            "used_provider_space": None,
            "total_provider_space": None,
            "max_bag_size_bytes": None,
            "service_uptime": None,
        }

        with self._log_on_error("provider pubkey"):
            section["pubkey"] = provider.get_provider_pubkey()
        with self._log_on_error("provider used_space"):
            section["used_provider_space"] = ton_storage.get_used_space_gb()
        with self._log_on_error("provider total_space"):
            section["total_provider_space"] = provider.get_total_space_gb()
        with self._log_on_error("provider max_bag_size"):
            max_bag_gb = provider.get_max_bag_size_gb()
            if max_bag_gb is not None:
                section["max_bag_size_bytes"] = int(max_bag_gb * 1024**3)
        with self._log_on_error("provider service_uptime"):
            section["service_uptime"] = get_service_uptime(provider.service_name)

        return section

    def _collect_statistics(self, statistics: StatisticsModule) -> dict[str, Any]:
        """Build the top-level statistics fields (net/disk/iops/pps)."""
        section: dict[str, Any] = {
            "net_recv": None,
            "net_sent": None,
            "net_load": None,
            "bytes_recv": None,
            "bytes_sent": None,
            "disks_load": None,
            "disks_load_percent": None,
            "iops": None,
            "pps": None,
        }
        with self._log_on_error("stats net_recv"):
            section["net_recv"] = statistics.get_net_recv_avg()
        with self._log_on_error("stats net_sent"):
            section["net_sent"] = statistics.get_net_sent_avg()
        with self._log_on_error("stats net_load"):
            section["net_load"] = statistics.get_net_load_avg()
        with self._log_on_error("stats bytes_recv"):
            section["bytes_recv"] = statistics.get_bytes_recv()
        with self._log_on_error("stats bytes_sent"):
            section["bytes_sent"] = statistics.get_bytes_sent()
        with self._log_on_error("stats disks_load"):
            section["disks_load"] = statistics.get_disks_load_avg()
        with self._log_on_error("stats disks_load_percent"):
            section["disks_load_percent"] = statistics.get_disks_load_percent_avg()
        with self._log_on_error("stats iops"):
            section["iops"] = statistics.get_iops_avg()
        with self._log_on_error("stats pps"):
            section["pps"] = statistics.get_pps_avg()
        return section

    def _collect_ram(self) -> dict[str, Any]:
        """RAM info in decimal GB, matching old payload keys."""
        vm = psutil.virtual_memory()
        return {
            "total": round(vm.total / BYTES_PER_GB_DECIMAL, 2),
            "usage": round(vm.used / BYTES_PER_GB_DECIMAL, 2),
            "usage_percent": vm.percent,
        }

    def _collect_swap(self) -> dict[str, Any]:
        """Swap info in decimal GB, matching old payload keys."""
        sm = psutil.swap_memory()
        return {
            "total": round(sm.total / BYTES_PER_GB_DECIMAL, 2),
            "usage": round(sm.used / BYTES_PER_GB_DECIMAL, 2),
            "usage_percent": sm.percent,
        }

    def _collect_uname(self) -> dict[str, Any] | None:
        """Return ``os.uname()._asdict()`` or ``None`` on failure."""
        try:
            return get_uname()._asdict()
        except Exception as exc:
            self.app.add_log(f"telemetry: uname failed: {exc}", DEBUG)
            return None

    def _collect_cpu_info(self) -> dict[str, Any]:
        """Build the ``cpu_info`` section (old keys: product_name, is_virtual)."""
        info: dict[str, Any] = {
            "cpu_count": None,
            "cpu_load": None,
            "cpu_name": None,
            "product_name": None,
            "is_virtual": None,
        }
        with self._log_on_error("cpu_count"):
            info["cpu_count"] = get_cpu_count()
        with self._log_on_error("cpu_load"):
            info["cpu_load"] = get_load_avg()
        with self._log_on_error("cpu_name"):
            info["cpu_name"] = get_cpu_name()
        with self._log_on_error("product_name"):
            info["product_name"] = get_hardware_name()
        with self._log_on_error("is_virtual"):
            info["is_virtual"] = is_hardware_virtualized()
        return info

    def _collect_versions(self) -> dict[str, str]:
        """Collect ``format_version()`` output for every Updatable module.

        Replaces the old ``git_hashes`` payload (previously short git
        commits per module). Key name kept for server compatibility;
        values are now version strings like ``v1.0.0 (a1b2c3d)``.
        """
        versions: dict[str, str] = {}
        for module in self.registry.all(enabled_only=False):
            if not isinstance(module, Updatable):
                continue
            try:
                versions[module.name] = module.format_version()
            except Exception as exc:
                self.app.add_log(
                    f"telemetry: {module.name} version failed: {exc}", DEBUG,
                )
        return versions

    def _collect_pings(self) -> dict[str, float] | None:
        """Return per-host ping latencies, or ``None`` on any failure.

        All-or-nothing semantics match the old ``get_pings_values`` path
        which raised on the first failing host and was wrapped in
        ``try_function`` yielding ``None`` for the whole payload.
        """
        try:
            result = get_pings(constants.ADNL_CHECKER_HOSTS)
        except Exception as exc:
            self.app.add_log(f"telemetry: pings failed: {exc}", DEBUG)
            return None
        if any(value is None for value in result.values()):
            return None
        return {host: value for host, value in result.items() if value is not None}

    def _collect_benchmark_data(self) -> dict[str, Any] | None:
        """Build benchmark payload, or ``None`` if no benchmark has run yet."""
        benchmark = self.app.db.benchmark
        if benchmark is None:
            return None
        provider = self.registry.get_by_class(TonStorageProviderModule)
        return {
            "pubkey": provider.get_provider_pubkey(),
            "timestamp": get_timestamp(),
            **benchmark,
        }

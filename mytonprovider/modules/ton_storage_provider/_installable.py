from __future__ import annotations

import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mypycli import Installable
from mypycli.types import Color, ColorText
from mypycli.utils.network import get_public_ip
from mypycli.utils.service import SystemdService
from mypycli.utils.sysinfo import sysinfo
from mypycli.utils.system import run_as_root

from mytonprovider import constants
from mytonprovider.utils import (
    calculate_max_span,
    calculate_min_rate_per_mb_day,
    calculate_space_to_provide_megabytes,
    read_config,
    run_root_script,
    write_config,
)

from .config import ProviderConfig, StorageBackend

if TYPE_CHECKING:
    from mypycli import InstallContext

    from .schemas import TonStorageProviderInstallParams

SERVICE_NAME = "ton-storage-provider"

_PROVIDER_MIN_SPAN_SEC = 7 * 24 * 3600
_CONFIG_WAIT_SECONDS = 15


class InstallableMixin(Installable):
    __abstract__ = True

    def prefill_install_params(self, context: InstallContext) -> dict[str, Any]:
        ts_params = context.collected.get("ton-storage")
        if ts_params is None:
            return {}
        storage_path = getattr(ts_params, "storage_path", None)
        if not storage_path:
            return {}
        probe = Path(storage_path)
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        try:
            usage = sysinfo.get_disk_usage(str(probe))
        except (OSError, FileNotFoundError):
            return {}
        # Offer 80% of free space rounded to GB.
        suggested_gb = max(1, int(usage.free * 0.8 / 1024**3))
        return {"space_to_provide_gigabytes": ColorText(str(suggested_gb), Color.YELLOW)}

    def on_install(
        self,
        params: TonStorageProviderInstallParams | None = None,
        context: InstallContext | None = None,
    ) -> None:
        del context
        assert params is not None, "ton-storage-provider install params are mandatory"

        ts = self.app.modules.get("ton-storage")
        storage_path = Path(ts.db.storage_path)
        provider_dir = storage_path / "provider"
        db_dir = provider_dir / "db"
        config_path = db_dir / "config.json"
        udp_port = random.randint(1024, 65000)

        provider_dir.mkdir(parents=True, exist_ok=True)
        run_as_root(
            [
                "chown",
                "-R",
                f"{constants.INSTALL_USER}:{constants.INSTALL_USER}",
                str(provider_dir),
            ]
        )

        self._build_binary()
        self._create_service(provider_dir, db_dir, config_path)

        svc = SystemdService(SERVICE_NAME)
        svc.enable()
        svc.start()
        self._wait_for_config(config_path)
        svc.stop()

        config = read_config(str(config_path), ProviderConfig)
        config.listen_addr = f"0.0.0.0:{udp_port}"
        config.external_ip = get_public_ip() or "0.0.0.0"
        config.min_span = _PROVIDER_MIN_SPAN_SEC
        config.max_span = calculate_max_span(params.storage_cost)
        config.min_rate_per_mb_day = calculate_min_rate_per_mb_day(params.storage_cost)
        config.max_bag_size_bytes = params.max_bag_size_gigabytes * 1024**3
        config.storages = [
            StorageBackend.model_validate(
                {
                    "BaseURL": f"http://{ts.db.api_host}:{ts.db.api_port}",
                    "SpaceToProvideMegabytes": calculate_space_to_provide_megabytes(params.space_to_provide_gigabytes),
                }
            )
        ]
        # Mutate ``enabled`` in place instead of replacing the whole CronConfig:
        # the Go daemon writes additional fields (e.g. ``min``) that we must
        # preserve via ``extra="allow"`` round-trip, otherwise startup fails with
        # ``failed to parse cron min amount``.
        config.cron.enabled = True
        write_config(str(config_path), config)

        self.db.config_path = str(config_path)

        svc.start()

    def on_uninstall(self) -> None:
        SystemdService(SERVICE_NAME).remove()

    @staticmethod
    def _build_binary() -> None:
        helper = constants.SCRIPTS_DIR / "install_go_package.sh"
        run_root_script(
            [
                str(helper),
                "-a",
                constants.TONUTILS_STORAGE_PROVIDER_AUTHOR,
                "-r",
                constants.TONUTILS_STORAGE_PROVIDER_REPO,
                "-b",
                constants.TONUTILS_STORAGE_PROVIDER_REF,
                "-e",
                constants.TONUTILS_STORAGE_PROVIDER_ENTRY,
            ]
        )

    @staticmethod
    def _create_service(provider_dir: Path, db_dir: Path, config_path: Path) -> None:
        binary = constants.BIN_DIR / constants.TONUTILS_STORAGE_PROVIDER_REPO
        exec_start = f"{binary} --db {db_dir} --config {config_path} -network-config {constants.GLOBAL_CONFIG_PATH}"
        SystemdService(SERVICE_NAME).create(
            exec_start=exec_start,
            user=constants.INSTALL_USER,
            work_dir=str(provider_dir),
            description="TON Storage Provider daemon",
            after="network.target",
            restart="on-failure",
            restart_sec=10,
        )

    @staticmethod
    def _wait_for_config(config_path: Path) -> None:
        deadline = time.monotonic() + _CONFIG_WAIT_SECONDS
        while time.monotonic() < deadline:
            if config_path.exists():
                return
            time.sleep(0.5)
        raise RuntimeError(f"ton-storage-provider did not generate {config_path} within {_CONFIG_WAIT_SECONDS}s")

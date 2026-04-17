from __future__ import annotations

import random
import time
from pathlib import Path
from typing import TYPE_CHECKING

from mypycli import Installable
from mypycli.utils.network import get_public_ip
from mypycli.utils.service import SystemdService
from mypycli.utils.system import run_as_root

from mytonprovider import constants
from mytonprovider.utils import read_config, run_root_script, write_config

from .config import StorageConfig

if TYPE_CHECKING:
    from mypycli import InstallContext

    from .schemas import TonStorageInstallParams

SERVICE_NAME = "ton-storage"
_CONFIG_WAIT_SECONDS = 15


class InstallableMixin(Installable):
    __abstract__ = True

    def on_install(
        self,
        params: TonStorageInstallParams | None = None,
        context: InstallContext | None = None,
    ) -> None:
        del context
        assert params is not None, "ton-storage install params are mandatory"

        storage_path = Path(params.storage_path)
        db_dir = storage_path / "db"
        config_path = db_dir / "config.json"
        api_port = random.randint(1024, 65000)
        udp_port = random.randint(1024, 65000)

        storage_path.mkdir(parents=True, exist_ok=True)
        run_as_root(["chown", "-R", f"{constants.INSTALL_USER}:{constants.INSTALL_USER}", str(storage_path)])

        self._build_binary()
        self._create_service(storage_path, db_dir, api_port)

        svc = SystemdService(SERVICE_NAME)
        svc.enable()
        svc.start()
        self._wait_for_config(config_path)
        svc.stop()

        config = read_config(str(config_path), StorageConfig)
        config.listen_addr = f"0.0.0.0:{udp_port}"
        config.external_ip = get_public_ip() or "0.0.0.0"
        write_config(str(config_path), config)

        self.db.storage_path = str(storage_path)
        self.db.config_path = str(config_path)
        self.db.api_host = "localhost"
        self.db.api_port = api_port

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
                constants.TONUTILS_STORAGE_AUTHOR,
                "-r",
                constants.TONUTILS_STORAGE_REPO,
                "-b",
                constants.TONUTILS_STORAGE_REF,
                "-e",
                constants.TONUTILS_STORAGE_ENTRY,
            ]
        )

    @staticmethod
    def _create_service(storage_path: Path, db_dir: Path, api_port: int) -> None:
        binary = constants.BIN_DIR / constants.TONUTILS_STORAGE_REPO
        exec_start = (
            f"{binary} --daemon "
            f"--db {db_dir} "
            f"--api localhost:{api_port} "
            f"-network-config {constants.GLOBAL_CONFIG_PATH} "
            f"--no-verify"
        )
        SystemdService(SERVICE_NAME).create(
            exec_start=exec_start,
            user=constants.INSTALL_USER,
            work_dir=str(storage_path),
            description="TON Storage daemon",
            after="network.target",
            restart="on-failure",
            restart_sec=10,
        )

    @staticmethod
    def _wait_for_config(config_path: Path) -> None:
        # First start writes config.json once the daemon initializes its keys.
        # Poll instead of a fixed sleep to tolerate slow hosts.
        deadline = time.monotonic() + _CONFIG_WAIT_SECONDS
        while time.monotonic() < deadline:
            if config_path.exists():
                return
            time.sleep(0.5)
        raise RuntimeError(f"ton-storage did not generate {config_path} within {_CONFIG_WAIT_SECONDS}s")

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
from pathlib import Path
from random import randint
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast

import requests
from mypylib import (
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    ByteUnit,
    Dict,
    add2systemd,
    bcolors,
    color_print,
    convert_bytes,
    get_disk_space,
    get_own_ip,
    get_service_status,
    get_service_uptime,
    get_timestamp,
    print_table,
    read_config_from_file,
    time2human,
    timeago,
    write_config_to_file,
)
from ton_core import PrivateKey

from mytonprovider import constants
from mytonprovider.modules.core import (
    Commandable,
    Daemonic,
    Installable,
    Startable,
    Statusable,
    Updatable,
)
from mytonprovider.types import Command, InstallContext
from mytonprovider.utils import (
    check_adnl_connection,
    get_config_path,
    get_service_status_color,
    read_git_clone_version,
    shorten_bag_id,
)

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from mytonprovider.types import Channel, InstalledVersion


# Service behavior
DAEMON_INTERVAL_SEC: Final[int] = 86400
SERVICE_START_SLEEP_SEC: Final[int] = 10
INSTALL_BUILD_TIMEOUT_SEC: Final[int] = 300

# HTTP API (local tonutils-storage daemon)
API_HOST: Final[str] = "localhost"
API_TIMEOUT_LIST_SEC: Final[float] = 0.3
API_TIMEOUT_VERIFY_SEC: Final[float] = 60.0
API_TIMEOUT_LOGGER_SEC: Final[float] = 3.0

# Bag identifier
BAG_ID_LENGTH: Final[int] = 64

# storage_log verbosity bounds accepted by /api/v1/logger
STORAGE_LOG_VERBOSITY_MIN: Final[int] = 0
STORAGE_LOG_VERBOSITY_MAX: Final[int] = 13

# Layout under storage_path
BAGS_SUBDIR: Final[str] = "provider"
DB_SUBDIR: Final[str] = "db"
STORAGE_CONFIG_NAME: Final[str] = "config.json"

# Source clone & binary location (set by install_go_package.sh)
GIT_CLONE_DIR: Final[Path] = Path("/usr/src") / constants.TON_STORAGE_REPO
BIN_PATH: Final[Path] = Path("/usr/local/bin") / constants.TON_STORAGE_REPO


class TonStorageModule(
    Startable,
    Statusable,
    Daemonic,
    Installable,
    Updatable,
    Commandable,
):
    """Wraps the ``ton-storage`` Go daemon (xssnick/tonutils-storage)."""

    name = "ton-storage"
    service_name = "ton-storage"
    mandatory = False

    github_author = constants.TON_STORAGE_AUTHOR
    github_repo = constants.TON_STORAGE_REPO
    default_version = constants.TON_STORAGE_VERSION
    entry_point: ClassVar[str] = constants.TON_STORAGE_ENTRY
    daemon_interval = DAEMON_INTERVAL_SEC

    def __init__(self, app: MyPyClass) -> None:
        super().__init__(app)
        self._port_check_ok: bool | None = None
        self._port_check_error: str | None = None

    @property
    def is_enabled(self) -> bool:
        return "ton_storage" in self.app.db

    def pre_up(self) -> None:
        self.app.start_thread(self._check_update_background)
        self.app.start_thread(self._check_port_background)

    def get_installed_version(self) -> InstalledVersion:
        return read_git_clone_version(GIT_CLONE_DIR)

    def build_update_args(self, target: Channel) -> list[str]:
        flag = "-t" if target.ref_kind == "tag" else "-b"
        script_path = constants.SCRIPTS_DIR / "install_go_package.sh"
        args = [
            "bash",
            str(script_path),
            "-a",
            target.author,
            "-r",
            target.repo,
            flag,
            target.ref,
            "-e",
            self.entry_point,
            "-s",
            self.service_name,
        ]
        if os.geteuid() != 0:
            args = ["sudo", *args]
        return args

    def show_status(self) -> None:
        color_print("{cyan}===[ Local storage status ]==={endc}")
        self._print_module_name()
        self._print_bags_num()
        self._print_disk_space()
        self._print_port_status()
        self._print_service_status()
        self._print_version()

    def get_used_space_gb(self) -> float:
        """Return total size of tracked BAGs in GB.

        Cross-module entry point used by ``TonStorageProviderModule``.

        :raises RuntimeError: if the storage API is unreachable.
        """
        return self._get_bags_size_gb(self._get_api_data())

    def daemon(self) -> None:
        """Remove orphan BAG directories that the provider no longer tracks."""
        storage_path = Path(self.app.db.ton_storage.storage_path)
        bags_dir = storage_path / BAGS_SUBDIR
        try:
            api_data = self._get_api_data()
        except RuntimeError as exc:
            self.app.add_log(f"{self.name}: daemon skipped (API unreachable): {exc}", DEBUG)
            return
        known = set(self._get_bags_list(api_data))
        for entry in os.listdir(bags_dir):
            if len(entry) != BAG_ID_LENGTH:
                continue
            if entry not in known:
                target = bags_dir / entry
                self.app.add_log(f"Cleaning up orphan BAG: {target}", WARNING)
                shutil.rmtree(target)

    def get_commands(self) -> list[Command]:
        return [
            Command(
                name="bags_list",
                func=self._cmd_bags_list,
                description=self.app.translate("bags_list_cmd"),
            ),
            Command(
                name="verify_bag",
                func=self._cmd_verify_bag,
                description=self.app.translate("verify_bag_cmd"),
            ),
            Command(
                name="storage_log",
                func=self._cmd_storage_log,
                description=self.app.translate("storage_log_cmd"),
            ),
        ]

    def install(self, context: InstallContext) -> None:
        """Build tonutils-storage, configure storage dir, create service."""
        self.app.add_log(f"Installing {self.name} module")

        if os.geteuid() != 0:
            raise RuntimeError(f"{self.name}: install must be run as root (use sudo)")

        try:
            pwd.getpwnam(context.user)
        except KeyError as exc:
            raise RuntimeError(f"{self.name}: user {context.user!r} does not exist") from exc

        if context.storage_path is None:
            raise RuntimeError(f"{self.name}: storage_path is required")
        storage_path = context.storage_path
        db_dir = storage_path / DB_SUBDIR
        storage_config_path = db_dir / STORAGE_CONFIG_NAME

        udp_port = randint(constants.PORT_RANGE_MIN, constants.PORT_RANGE_MAX)
        api_port = randint(constants.PORT_RANGE_MIN, constants.PORT_RANGE_MAX)

        try:
            update_args = self.build_update_args(self.default_channel())
            subprocess.run(update_args, check=True, timeout=INSTALL_BUILD_TIMEOUT_SEC)

            storage_path.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["chown", f"{context.user}:{context.user}", str(storage_path)],
                check=True,
            )

            start_cmd = (
                f"{BIN_PATH} --daemon "
                f"--db {db_dir} "
                f"--api {API_HOST}:{api_port} "
                f"-network-config {constants.GLOBAL_CONFIG_PATH} "
                f"--no-verify"
            )
            add2systemd(
                name=self.service_name,
                user=context.user,
                start=start_cmd,
                workdir=str(storage_path),
                force=True,
            )

            self.app.add_log(f"Starting {self.service_name} to materialize storage config")
            self.app.start_service(self.service_name, sleep=SERVICE_START_SLEEP_SEC)
            self.app.stop_service(self.service_name)

            storage_config = read_config_from_file(str(storage_config_path))
            storage_config.ListenAddr = f"0.0.0.0:{udp_port}"
            storage_config.ExternalIP = get_own_ip()
            write_config_to_file(str(storage_config_path), storage_config)

            config_path = get_config_path()
            mconfig = read_config_from_file(str(config_path))
            ton_storage = Dict()
            ton_storage.storage_path = str(storage_path)
            ton_storage.config_path = str(storage_config_path)
            ton_storage.api = Dict()
            ton_storage.api.host = API_HOST
            ton_storage.api.port = api_port
            mconfig.ton_storage = ton_storage
            write_config_to_file(str(config_path), mconfig)
            self.app.db.ton_storage = ton_storage

            self.app.add_log(f"Starting {self.service_name} service")
            self.app.start_service(self.service_name)
        except Exception:
            self.app.add_log(f"{self.name}: install failed, rolling back mconfig", ERROR)
            self._rollback_mconfig()
            raise

    def _rollback_mconfig(self) -> None:
        """Best-effort removal of the ``ton_storage`` section from mconfig."""
        config_path = get_config_path()
        try:
            mconfig = read_config_from_file(str(config_path))
        except Exception as exc:
            self.app.add_log(f"{self.name}: rollback read failed: {exc}", ERROR)
            return
        if "ton_storage" not in mconfig:
            return
        del mconfig["ton_storage"]
        try:
            write_config_to_file(str(config_path), mconfig)
        except Exception as exc:
            self.app.add_log(f"{self.name}: rollback write failed: {exc}", ERROR)
            return
        self.app.db.pop("ton_storage", None)

    def _check_update_background(self) -> None:
        try:
            self._update_status = self.check_update()
        except (RuntimeError, ValueError) as exc:
            self.app.add_log(f"{self.name}: update check failed: {exc}", DEBUG)
            self._update_status = None

    def _check_port_background(self) -> None:
        try:
            storage_config = self._read_storage_config()
            own_ip = get_own_ip()
            if storage_config.ExternalIP != own_ip:
                raise RuntimeError(
                    f"storage_config.ExternalIP ({storage_config.ExternalIP}) != own_ip ({own_ip})"
                )
            _listen_ip, storage_port_str = storage_config.ListenAddr.split(":")
            storage_port = int(storage_port_str)
            pubkey = PrivateKey(storage_config.Key).public_key.as_hex.upper()
        except (RuntimeError, ValueError, AttributeError, TypeError) as exc:
            self.app.add_log(f"{self.name}: port check setup failed: {exc}", DEBUG)
            self._port_check_ok = None
            self._port_check_error = str(exc)
            return

        ok, error = check_adnl_connection(own_ip, storage_port, pubkey)
        self._port_check_ok = ok
        self._port_check_error = error
        if not ok:
            self.app.add_log(f"{self.name}: ADNL port check failed: {error}", DEBUG)

    def _read_storage_config(self) -> Dict:
        return read_config_from_file(str(self.app.db.ton_storage.config_path))

    def get_storage_pubkey(self) -> str:
        """Return the storage daemon's ADNL public key (uppercase hex)."""
        return PrivateKey(self._read_storage_config().Key).public_key.as_hex.upper()

    def _get_api_data(self) -> Dict:
        api = self.app.db.ton_storage.api
        url = f"http://{api.host}:{api.port}/api/v1/list"
        try:
            response = requests.get(url, timeout=API_TIMEOUT_LIST_SEC)
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to reach {url}: {exc}") from exc
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get provider api data from {url}: HTTP {response.status_code}")
        return Dict(response.json())

    @staticmethod
    def _get_bags_num(api_data: Dict) -> int:
        bags = api_data.bags or []
        return len(bags)

    @staticmethod
    def _get_bags_list(api_data: Dict) -> list[str]:
        bags = api_data.bags or []
        return [bag.bag_id for bag in bags]

    @staticmethod
    def _get_bags_size_gb(api_data: Dict) -> float:
        bags = api_data.bags or []
        total_bytes = sum(bag.size for bag in bags)
        return convert_bytes(total_bytes, ByteUnit.GB, ndigits=2)

    def _get_bags_verify_state(self) -> dict[str, int]:
        ts = self.app.db.ton_storage
        if ts is None:
            return {}
        return cast("dict[str, int]", ts.get("bags_verify_state", {}))

    def _save_verify_result(self, bag_id: str, ok: bool) -> None:
        if self.app.db.ton_storage is None:
            return
        if self.app.db.ton_storage.bags_verify_state is None:
            self.app.db.ton_storage.bags_verify_state = Dict()
        self.app.db.ton_storage.bags_verify_state[bag_id.upper()] = get_timestamp()
        write_config_to_file(str(get_config_path()), self.app.db)
        if ok:
            self.app.add_log(f"BAG {bag_id} verified OK", INFO)
        else:
            self.app.add_log(f"BAG {bag_id} verification FAILED, redownload started", WARNING)

    def _do_verify_bag(self, bag_id: str) -> bool:
        api = self.app.db.ton_storage.api
        url = f"http://{api.host}:{api.port}/api/v1/verify"
        try:
            response = requests.post(url, json={"bag_id": bag_id}, timeout=API_TIMEOUT_VERIFY_SEC)
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to verify bag {bag_id}: {exc}") from exc
        if response.status_code != 200:
            try:
                payload = response.json()
                error = payload.get("error", "unknown error")
            except ValueError:
                error = response.text
            raise RuntimeError(f"Failed to verify bag {bag_id}: HTTP {response.status_code} ({error})")
        result = response.json()
        return bool(result.get("ok", False))

    def _set_log_level(self, verbosity: int) -> None:
        api = self.app.db.ton_storage.api
        url = f"http://{api.host}:{api.port}/api/v1/logger"
        try:
            response = requests.post(url, json={"verbosity": verbosity}, timeout=API_TIMEOUT_LOGGER_SEC)
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to set log level: {exc}") from exc
        if response.status_code != 200:
            raise RuntimeError(f"Failed to set log level: HTTP {response.status_code}")

    def _cmd_bags_list(self, args: list[str]) -> None:
        try:
            api_data = self._get_api_data()
        except RuntimeError as exc:
            color_print(f"{{red}}Error:{{endc}} {exc}")
            return

        bags = api_data.bags
        if not bags:
            print("no data")
            return

        verify_state = self._get_bags_verify_state()
        table: list[list[Any]] = [[
            "Bag id", "Progress", "Size", "Files",
            "Peers", "Download speed", "Upload speed", "Last verified",
        ]]
        for bag in bags:
            size = convert_bytes(bag.size, ByteUnit.GB, ndigits=2)
            download = convert_bytes(bag.download_speed, ByteUnit.MB, ndigits=2)
            upload = convert_bytes(bag.upload_speed, ByteUnit.MB, ndigits=2)
            last_verified_ts = verify_state.get(bag.bag_id.upper(), 0)
            last_verified_text = timeago(last_verified_ts) if last_verified_ts else "never"
            table.append([
                shorten_bag_id(bag.bag_id),
                f"{self._get_bag_progress(bag)}%",
                f"{size} GB",
                bag.files_count,
                bag.peers,
                f"{download} MB/s",
                f"{upload} MB/s",
                last_verified_text,
            ])
        print_table(table)

    def _cmd_verify_bag(self, args: list[str]) -> None:
        if not args:
            color_print("{red}Bad args. Usage:{endc} verify_bag <bag_id>")
            return
        bag_id = args[0].strip().upper()
        if len(bag_id) != BAG_ID_LENGTH or not all(c in "0123456789ABCDEF" for c in bag_id):
            color_print(
                f"{{red}}Error: bag_id must be a {BAG_ID_LENGTH}-character hex string{{endc}}"
            )
            return

        color_print(f"Verifying BAG: {{yellow}}{bag_id}{{endc}}")
        try:
            ok = self._do_verify_bag(bag_id)
        except RuntimeError as exc:
            color_print(f"{{red}}Error:{{endc}} {exc}")
            return
        self._save_verify_result(bag_id, ok)
        if ok:
            color_print("{green}BAG verified OK - files are intact{endc}")
        else:
            color_print("{yellow}BAG verification failed - redownload started{endc}")

    def _cmd_storage_log(self, args: list[str]) -> None:
        try:
            verbosity = int(args[0])
        except (IndexError, ValueError):
            color_print("{red}Bad args. Usage:{endc} storage_log <verbosity>")
            color_print("Verbosity: 0-1=error, 2=info, 3-10=debug, 11-13=debug+loggers")
            return
        if verbosity < STORAGE_LOG_VERBOSITY_MIN or verbosity > STORAGE_LOG_VERBOSITY_MAX:
            color_print(
                f"{{red}}Error: verbosity must be "
                f"{STORAGE_LOG_VERBOSITY_MIN}-{STORAGE_LOG_VERBOSITY_MAX}{{endc}}"
            )
            return
        try:
            self._set_log_level(verbosity)
        except RuntimeError as exc:
            color_print(f"{{red}}Error:{{endc}} {exc}")
            return
        color_print(f"ton-storage log level set to {{green}}{verbosity}{{endc}}")

    @staticmethod
    def _get_bag_progress(bag: Dict) -> float:
        if bag.size == 0:
            return 0.0
        return round(float(bag.downloaded) / float(bag.size) * 100, 2)

    def _print_module_name(self) -> None:
        module_name = bcolors.yellow_text(self.name)
        text = self.app.translate("module_name").format(module_name)
        print(text)

    def _print_bags_num(self) -> None:
        try:
            api_data = self._get_api_data()
            bags_num_text = bcolors.green_text(self._get_bags_num(api_data))
            used_text = bcolors.green_text(self._get_bags_size_gb(api_data))
        except (RuntimeError, AttributeError, TypeError):
            bags_num_text = bcolors.red_text("n/a")
            used_text = bcolors.red_text("n/a")
        text = self.app.translate("bags_num").format(bags_num_text, used_text)
        print(text)

    def _print_disk_space(self) -> None:
        try:
            storage_path = self.app.db.ton_storage.storage_path
            disk = get_disk_space(storage_path, unit=ByteUnit.GB, ndigits=2)
            used_text = bcolors.green_text(disk.used)
            total_text = bcolors.yellow_text(disk.total)
        except (RuntimeError, OSError, AttributeError):
            used_text = bcolors.red_text("n/a")
            total_text = bcolors.red_text("n/a")
        text = self.app.translate("disk_space").format(used_text, total_text)
        print(text)

    def _print_port_status(self) -> None:
        try:
            storage_config = self._read_storage_config()
            _, storage_port_str = storage_config.ListenAddr.split(":")
        except (RuntimeError, AttributeError, ValueError):
            storage_port_str = "?"
        port_color = bcolors.yellow_text(f"{storage_port_str} udp")
        if self._port_check_ok:
            status_color = bcolors.green_text("open")
        elif self._port_check_ok is False:
            status_color = bcolors.red_text("closed")
        else:
            status_color = bcolors.red_text("n/a")
        text = self.app.translate("port_status").format(port_color, status_color)
        color_print(text)

    def _print_service_status(self) -> None:
        is_active = get_service_status(self.service_name)
        uptime = get_service_uptime(self.service_name) or 0
        status_color = get_service_status_color(is_active)
        uptime_color = bcolors.green_text(time2human(uptime))
        text = self.app.translate("service_status_and_uptime").format(status_color, uptime_color)
        color_print(text)

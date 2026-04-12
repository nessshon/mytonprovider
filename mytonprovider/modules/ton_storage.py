from __future__ import annotations

import io
import os
import pwd
import shutil
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from random import randint
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast

import requests
from mypylib import (
    DEBUG,
    ERROR,
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
from mytonprovider.types import Command, InstallContext, StatusBlock
from mytonprovider.utils import (
    check_adnl_connection,
    read_git_clone_version,
    render_status_block,
)

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from mytonprovider.types import Channel, InstalledVersion


DAEMON_INTERVAL_SEC: Final[int] = 86400
SERVICE_START_SLEEP_SEC: Final[int] = 10
INSTALL_BUILD_TIMEOUT_SEC: Final[int] = 300

API_HOST: Final[str] = "localhost"
API_TIMEOUT_LIST_SEC: Final[float] = 0.3
API_TIMEOUT_VERIFY_SEC: Final[float] = 60.0
API_TIMEOUT_LOGGER_SEC: Final[float] = 3.0

BAG_ID_LENGTH: Final[int] = 64

STORAGE_LOG_VERBOSITY_MIN: Final[int] = 0
STORAGE_LOG_VERBOSITY_MAX: Final[int] = 13

BAGS_SUBDIR: Final[str] = "provider"
DB_SUBDIR: Final[str] = "db"
STORAGE_CONFIG_NAME: Final[str] = "config.json"

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
    daemon_interval = DAEMON_INTERVAL_SEC

    github_author = constants.TON_STORAGE_AUTHOR
    github_repo = constants.TON_STORAGE_REPO
    default_version = constants.TON_STORAGE_VERSION
    entry_point: ClassVar[str] = "cli/main.go"

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
        block = StatusBlock(
            name=self.name,
            version=self.format_version(),
            card=self._get_card(),
            rows=[
                self._get_bags_num(),
                self._get_disk_space(),
                self._get_port_status(),
            ],
            service_text=self._get_service_text(),
            update_text=self._get_update_text(),
        )
        render_status_block(block)

    def get_used_space_gb(self) -> float:
        """Return total size of tracked BAGs in GB."""
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
        print(f"Installing {self.name} module")

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
            with redirect_stdout(io.StringIO()):
                add2systemd(
                    name=self.service_name,
                    user=context.user,
                    start=start_cmd,
                    workdir=str(storage_path),
                    force=True,
                )

            print(f"Starting {self.service_name} to generate config")
            self.app.start_service(self.service_name, sleep=SERVICE_START_SLEEP_SEC)
            self.app.stop_service(self.service_name)

            storage_config = read_config_from_file(str(storage_config_path))
            storage_config.ListenAddr = f"0.0.0.0:{udp_port}"
            storage_config.ExternalIP = get_own_ip()
            write_config_to_file(str(storage_config_path), storage_config)

            ton_storage = Dict()
            ton_storage.storage_path = str(storage_path)
            ton_storage.config_path = str(storage_config_path)
            ton_storage.api = Dict()
            ton_storage.api.host = API_HOST
            ton_storage.api.port = api_port
            self.app.db.ton_storage = ton_storage
            self.app.save()

            print(f"Starting {self.service_name} service")
            self.app.start_service(self.service_name)
        except Exception:
            color_print(f"{{red}}{self.name}: install failed, rolling back{{endc}}")
            self._rollback_mconfig()
            raise

    def _rollback_mconfig(self) -> None:
        """Best-effort removal of the ``ton_storage`` section from db."""
        self.app.db.pop("ton_storage", None)
        try:
            self.app.save()
        except Exception as exc:
            self.app.add_log(f"{self.name}: rollback save failed: {exc}", ERROR)

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
    def _get_bags_num_count(api_data: Dict) -> int:
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
        self.app.save()

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
                f"{bag.bag_id[:6]}...{bag.bag_id[-6:]}",
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

    def _get_card(self) -> list[tuple[str, str]]:
        card: list[tuple[str, str]] = []
        try:
            card.append(("Storage path", bcolors.yellow_text(self.app.db.ton_storage.storage_path)))
        except (AttributeError, TypeError):
            card.append(("Storage path", bcolors.red_text("n/a")))
        try:
            card.append(("ADNL key", bcolors.yellow_text(self.get_storage_pubkey())))
        except (RuntimeError, AttributeError, TypeError):
            card.append(("ADNL key", bcolors.red_text("n/a")))
        return card

    def _get_bags_num(self) -> tuple[str, str]:
        try:
            api_data = self._get_api_data()
            count = bcolors.green_text(self._get_bags_num_count(api_data))
            size = bcolors.green_text(f"{self._get_bags_size_gb(api_data)} GB")
            return ("Stored containers", f"{count} ({size})")
        except (RuntimeError, AttributeError, TypeError):
            return ("Stored containers", bcolors.red_text("n/a"))

    def _get_disk_space(self) -> tuple[str, str]:
        try:
            storage_path = self.app.db.ton_storage.storage_path
            disk = get_disk_space(storage_path, unit=ByteUnit.GB, ndigits=2)
            used = bcolors.green_text(disk.used)
            total = bcolors.yellow_text(disk.total)
            return ("Disk space used / total", f"{used} / {total} GB")
        except (RuntimeError, OSError, AttributeError):
            return ("Disk space used / total", bcolors.red_text("n/a"))

    def _get_port_status(self) -> tuple[str, str]:
        try:
            storage_config = self._read_storage_config()
            _, port_str = storage_config.ListenAddr.split(":")
        except (RuntimeError, AttributeError, ValueError):
            port_str = "?"
        if self._port_check_ok:
            status = f"{bcolors.green_text('✓')} {bcolors.green_text('open')}"
        elif self._port_check_ok is False:
            status = f"{bcolors.red_text('✗')} {bcolors.red_text('closed')}"
        else:
            status = bcolors.red_text("n/a")
        return (f"Port {port_str} udp", status)

    def _get_service_text(self) -> str:
        is_active = get_service_status(self.service_name)
        uptime = get_service_uptime(self.service_name) or 0
        if is_active:
            indicator = bcolors.green_text("✓")
            status = bcolors.green_text("working")
            return f"{indicator} {status}, uptime {bcolors.green_text(time2human(uptime))}"
        return f"{bcolors.red_text('✗')} {bcolors.red_text('not working')}"

    def _get_update_text(self) -> str | None:
        status = self._update_status
        if status and status.available and status.target:
            return f"Update available: {status.target.ref}"
        return None

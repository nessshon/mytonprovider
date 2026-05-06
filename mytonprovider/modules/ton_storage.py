import base64
import re
import shutil
import time
from pathlib import Path
from random import randint
from typing import Any, ClassVar, Final

from mypycli import (
    Commandable,
    Daemonic,
    Installable,
    Startable,
    Statusable,
    Updatable,
    utils,
)
from mypycli.console.ansi import colorize_text, colorize_threshold
from mypycli.types import BoxStyle, ByteUnit, Color, ColorText, Command
from pydantic import BaseModel, ConfigDict, Field

from mytonprovider import constants
from mytonprovider.clients.ton_storage import BagDetails, BagInfo, BagsListResponse, StorageApi
from mytonprovider.locales import _, lang
from mytonprovider.utils import (
    check_adnl_connection,
    check_repo_update,
    create_status_footer,
    create_status_header,
)


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    key: str = Field(default="", alias="Key")
    listen_addr: str = Field(default="", alias="ListenAddr")
    external_ip: str = Field(default="", alias="ExternalIP")

    @property
    def pubkey(self) -> str:
        return base64.b64decode(self.key)[32:64].hex().upper()


class VerifyStateConfig(BaseModel):
    last_verified: dict[str, int] = Field(default_factory=dict)


class TonStorageModule(
    Startable,
    Statusable,
    Installable,
    Updatable,
    Daemonic,
    Commandable,
):
    mandatory: ClassVar[bool] = True
    name: ClassVar[str] = "ton-storage"
    label: ClassVar[str] = "TON Storage"

    SERVICE_NAME: Final[str] = "ton-storage"
    CLEANUP_BAGS_INTERVAL_SEC: Final[int] = 86400
    VERIFY_BAG_STATE_FILENAME: Final[str] = "ton-storage.verify.json"
    VERIFY_BAG_THRESHOLD_SEC: Final[int] = 30 * 86400
    VERIFY_BAG_INTERVAL_SEC: Final[int] = 3600
    LOG_VERBOSITY_MIN: Final[int] = 0
    LOG_VERBOSITY_MAX: Final[int] = 13
    BAG_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{64}$")

    GO_PACKAGE_REPO: ClassVar[str] = "tonutils-storage"
    GO_PACKAGE_ENTRY: ClassVar[str] = "cli/main.go"

    service: ClassVar[utils.SystemdService] = utils.SystemdService(SERVICE_NAME)
    src_path: ClassVar[Path] = constants.SRC_DIR / GO_PACKAGE_REPO
    bin_path: ClassVar[Path] = constants.BIN_DIR / GO_PACKAGE_REPO

    _update_available: bool | None = None
    _update_target: str | None = None
    _port_open: bool | None = None

    @property
    def api(self) -> StorageApi:
        cfg = self.app.db.settings.storage_api
        return StorageApi(
            "localhost",
            self.app.db.modules.ton_storage.api_port,
            request_timeout=cfg.request_timeout,
            verify_timeout=cfg.verify_timeout,
        )

    @property
    def repo(self) -> utils.LocalGitRepo:
        return utils.LocalGitRepo(self.src_path)

    @property
    def version(self) -> str:
        info = self.repo.info
        return info.version if info.tag else info.commit_short

    @property
    def storage_path(self) -> Path:
        return Path(self.app.db.modules.ton_storage.storage_path)

    @property
    def bags_path(self) -> Path:
        return self.storage_path / "provider"

    @property
    def config_path(self) -> Path:
        return self.storage_path / "db" / "config.json"

    def get_storage_config(self) -> StorageConfig:
        return utils.read_config(self.config_path, StorageConfig)

    def update_storage_config(self, config: StorageConfig) -> None:
        utils.write_config(self.config_path, config)

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "bags",
                description=_("modules.ton_storage.cmd.bags.group"),
                children=[
                    Command(
                        "list",
                        self._cmd_bags_list,
                        _("modules.ton_storage.cmd.bags.list"),
                        "[page]",
                    ),
                    Command(
                        "info",
                        self._cmd_bags_info,
                        _("modules.ton_storage.cmd.bags.info"),
                        "<bag_id>",
                    ),
                    Command(
                        "add",
                        self._cmd_bags_add,
                        _("modules.ton_storage.cmd.bags.add"),
                        "<bag_id> [--no-download]",
                    ),
                    Command(
                        "remove",
                        self._cmd_bags_remove,
                        _("modules.ton_storage.cmd.bags.remove"),
                        "<bag_id> [--with-files]",
                    ),
                    Command(
                        "start",
                        self._cmd_bags_start,
                        _("modules.ton_storage.cmd.bags.start"),
                        "<bag_id>",
                    ),
                    Command(
                        "stop",
                        self._cmd_bags_stop,
                        _("modules.ton_storage.cmd.bags.stop"),
                        "<bag_id>",
                    ),
                    Command(
                        "verify",
                        self._cmd_bags_verify,
                        _("modules.ton_storage.cmd.bags.verify"),
                        "<bag_id>",
                    ),
                ],
            ),
            Command(
                "storage",
                description=_("modules.ton_storage.cmd.storage.group"),
                children=[
                    Command(
                        "info",
                        self._cmd_storage_info,
                        _("modules.ton_storage.cmd.storage.info"),
                    ),
                    Command(
                        "log",
                        self._cmd_storage_log,
                        _("modules.ton_storage.cmd.storage.log"),
                        "<0-13>",
                    ),
                ],
            ),
        ]

    def on_install(self) -> None:
        if not self.bin_path.exists():
            raise RuntimeError(f"{self.name}: binary not found at {self.bin_path}")

        storage_path = Path(
            self.app.console.input(
                _("modules.ton_storage.install.storage_path"),
                default=self.app.db.install_args.ton_storage_path or constants.TON_STORAGE_DEFAULT_STORAGE_PATH,
                env_var="TON_STORAGE_PATH",
            )
        )
        self.app.db.install_args.ton_storage_path = str(storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)
        owner = self.app.work_dir.owner()
        shutil.chown(storage_path, user=owner, group=owner)

        state = self.app.db.modules.ton_storage
        state.storage_path = str(storage_path)
        state.udp_port = randint(36000, 36999)
        state.api_port = randint(37000, 37999)

        exec_start = (
            f"{self.bin_path} --daemon"
            f" --db {storage_path}/db"
            f" --api localhost:{state.api_port}"
            f" --network-config {constants.TON_CONFIG_PATH}"
            f" --no-verify"
        )
        self.service.create(
            exec_start=exec_start,
            user=self.app.work_dir.owner(),
            work_dir=str(storage_path),
            description=f"{self.SERVICE_NAME} daemon",
        )
        self.service.enable()
        self.service.start()
        time.sleep(10)
        self.service.stop()

        config = self.get_storage_config()
        config.listen_addr = f"0.0.0.0:{state.udp_port}"
        config.external_ip = utils.get_public_ip() or ""
        self.update_storage_config(config)
        self.service.start()
        state.enabled = True

    def on_uninstall(self) -> None:
        self.app.db.modules.ton_storage.enabled = False
        self.service.disable()
        self.service.remove()

    def on_update(self) -> None:
        repo = self.repo
        info = repo.info
        if repo.has_updates(by="version" if info.tag else "commit"):
            repo.update()
            self.build()

    def build(self) -> None:
        self._build_go_binary()
        self.service.restart()

    def on_daemon(self) -> None:
        self.run_cycle(self.cycle_cleanup_bags, seconds=self.CLEANUP_BAGS_INTERVAL_SEC)
        self.run_cycle(self.cycle_verify_bag, seconds=self.VERIFY_BAG_INTERVAL_SEC)

    def on_start(self) -> None:
        self.run_task(self.task_check_update)
        self.run_task(self.task_check_port)

    def on_stop(self) -> None:
        self._update_available = None
        self._update_target = None
        self._port_open = None

    def show_status(self) -> None:
        bags_data: BagsListResponse | None
        try:
            bags_data = self.api.list_bags()
        except Exception as exc:
            self.logger.debug(f"status: list_bags failed: {exc}")
            bags_data = None

        self.app.console.print_panel(
            [
                self._status_udp_port(),
                self._status_bags(bags_data),
                self._status_disk_space(),
            ],
            header=create_status_header(
                self.label,
                self.version,
                target=self._update_target,
                available=bool(self._update_available),
            ),
            footer=create_status_footer(self.service, lang=lang()),
            min_width=constants.STATUS_PANEL_WIDTH,
        )

    def cycle_cleanup_bags(self) -> None:
        try:
            data = self.api.list_bags()
        except Exception as exc:
            self.logger.warning(f"API unreachable: {exc}")
            return
        known = {b.bag_id.upper() for b in data.bags}
        if not self.bags_path.exists():
            return
        for entry in self.bags_path.iterdir():
            if not entry.is_dir() or not self.BAG_ID_RE.fullmatch(entry.name):
                continue
            if entry.name.upper() not in known:
                self.logger.warning(f"removing orphan bag: {entry}")
                shutil.rmtree(entry, ignore_errors=True)

    def cycle_verify_bag(self) -> None:
        try:
            data = self.api.list_bags()
        except Exception as exc:
            self.logger.warning(f"API unreachable: {exc}")
            return
        state = self._read_verify_state()
        now = int(time.time())
        overdue = [
            (b, state.last_verified.get(b.bag_id.upper(), 0))
            for b in data.bags
            if now - state.last_verified.get(b.bag_id.upper(), 0) >= self.VERIFY_BAG_THRESHOLD_SEC
        ]
        if not overdue:
            return
        bag = min(overdue, key=lambda x: x[1])[0]
        ok = self.api.verify_bag(bag.bag_id)
        state.last_verified[bag.bag_id.upper()] = now
        self._write_verify_state(state)
        if ok:
            self.logger.info(f"{bag.bag_id} intact")
        else:
            self.logger.warning(f"{bag.bag_id} corrupted, re-downloading")

    def task_check_update(self) -> None:
        self._update_available, self._update_target = check_repo_update(self.repo)

    def task_check_port(self) -> None:
        config = self.get_storage_config()
        own_ip = config.external_ip or utils.get_public_ip()
        if not own_ip:
            self.logger.debug("external IP unknown")
            return
        if not config.pubkey:
            self.logger.debug("pubkey is empty")
            return
        self._port_open = check_adnl_connection(
            own_ip,
            self.app.db.modules.ton_storage.udp_port,
            config.pubkey,
            timeout=self.app.db.settings.adnl_checker_api.request_timeout,
        )

    def _cmd_bags_list(self, _app: Any, args: list[str]) -> None:
        page = 1
        if args:
            try:
                page = max(1, int(args[0]))
            except ValueError:
                self.app.console.print(f"{_('common.usage_prefix')} bags list [page]", Color.YELLOW)
                return

        data = self.api.list_bags()
        if not data.bags:
            self.app.console.print(_("modules.ton_storage.bags.empty"), Color.GRAY)
            return

        page_size = 50
        total = len(data.bags)
        pages = (total + page_size - 1) // page_size
        page = min(page, pages)
        start = (page - 1) * page_size
        chunk = data.bags[start : start + page_size]
        verify_state = self._read_verify_state()

        def t(key: str) -> ColorText:
            return ColorText(_(f"modules.ton_storage.table.{key}"), color=Color.CYAN)

        rows: list[list[str | ColorText]] = [
            [t("id"), t("progress"), t("size"), t("files"), t("peers"), t("download"), t("upload"), t("verified")]
        ]
        rows.extend(self._format_bag_row(bag, verify_state) for bag in chunk)
        footer = None
        if pages > 1:
            footer = colorize_text(
                _(
                    "modules.ton_storage.bags.list_page",
                    page=page,
                    pages=pages,
                    total=total,
                ),
                Color.GRAY,
            )
        self.app.console.print_table(rows, style=BoxStyle.SHARP, footer=footer)

    def _cmd_bags_info(self, _app: Any, args: list[str]) -> None:
        bag_id = self._parse_bag_id(args, "bags info <bag_id>")
        if bag_id is None:
            return
        bag = self.api.get_bag(bag_id)

        def t(key: str) -> ColorText:
            return ColorText(_(f"modules.ton_storage.table.{key}"), color=Color.CYAN)

        progress = f"{bag.downloaded / bag.size * 100:.1f}%" if bag.size else "—"
        color = self._bag_status_color(bag)
        bag_id_cell = ColorText(bag.bag_id, color=color)
        status_cell = ColorText(self._bag_status_text(bag), color=color)
        verified_ts = self._read_verify_state().last_verified.get(bag.bag_id.upper(), 0)
        verified_text = utils.format_time_ago(verified_ts, lang=lang()) if verified_ts else "—"
        rows: list[list[str | ColorText]] = [
            [t("metric"), t("value")],
            [t("bag_id"), bag_id_cell],
            [t("bag_path"), bag.path or "—"],
            [t("description"), bag.description or "—"],
            [t("size"), utils.format_bytes(bag.size)],
            [t("progress"), progress],
            [t("files"), str(bag.files_count)],
            [t("peers"), str(len(bag.peers))],
            [t("status"), status_cell],
            [t("verified"), verified_text],
        ]
        self.app.console.print_table(rows, style=BoxStyle.SHARP)

    def _cmd_bags_add(self, _app: Any, args: list[str]) -> None:
        bag_id = self._parse_bag_id(args, "bags add <bag_id> [--no-download]")
        if bag_id is None:
            return
        download_all = "--no-download" not in args[1:]
        self.bags_path.mkdir(parents=True, exist_ok=True)
        self.api.add_bag(bag_id, path=str(self.bags_path), download_all=download_all)
        key = "added" if download_all else "added_idle"
        self.app.console.print(_(f"modules.ton_storage.bags.{key}", bag_id=bag_id), Color.GREEN)

    def _cmd_bags_remove(self, _app: Any, args: list[str]) -> None:
        bag_id = self._parse_bag_id(args, "bags remove <bag_id> [--with-files]")
        if bag_id is None:
            return
        with_files = "--with-files" in args[1:]
        if with_files:
            self.api.remove_bag(bag_id, with_files=True)
            self.app.console.print(_("modules.ton_storage.bags.removed_with_files", bag_id=bag_id), Color.GREEN)
            return
        bag_path = self.api.get_bag(bag_id).path or str(self.bags_path / bag_id)
        self.api.remove_bag(bag_id, with_files=False)
        self.app.console.print(_("modules.ton_storage.bags.removed", bag_id=bag_id), Color.GREEN)
        self.app.console.print(_("modules.ton_storage.bags.removed_keep_hint", path=bag_path), Color.GRAY)

    def _cmd_bags_start(self, _app: Any, args: list[str]) -> None:
        bag_id = self._parse_bag_id(args, "bags start <bag_id>")
        if bag_id is None:
            return
        self.bags_path.mkdir(parents=True, exist_ok=True)
        self.api.add_bag(bag_id, path=str(self.bags_path), download_all=True)
        self.app.console.print(_("modules.ton_storage.bags.started", bag_id=bag_id), Color.GREEN)

    def _cmd_bags_stop(self, _app: Any, args: list[str]) -> None:
        bag_id = self._parse_bag_id(args, "bags stop <bag_id>")
        if bag_id is None:
            return
        self.api.stop_bag(bag_id)
        self.app.console.print(_("modules.ton_storage.bags.stopped", bag_id=bag_id), Color.GREEN)

    def _cmd_bags_verify(self, _app: Any, args: list[str]) -> None:
        bag_id = self._parse_bag_id(args, "bags verify <bag_id>")
        if bag_id is None:
            return
        ok = self.api.verify_bag(bag_id)
        state = self._read_verify_state()
        state.last_verified[bag_id.upper()] = int(time.time())
        self._write_verify_state(state)
        if ok:
            self.app.console.print(_("modules.ton_storage.bags.verify_ok", bag_id=bag_id), Color.GREEN)
        else:
            self.app.console.print(_("modules.ton_storage.bags.verify_failed", bag_id=bag_id), Color.YELLOW)

    def _cmd_storage_info(self, _app: Any, _args: list[str]) -> None:
        config = self.get_storage_config()

        def t(key: str) -> ColorText:
            return ColorText(_(f"modules.ton_storage.info.{key}"), color=Color.CYAN)

        rows: list[list[str | ColorText]] = [
            [t("metric"), t("value")],
            [t("adnl_pubkey"), config.pubkey or "—"],
            [t("listen_addr"), config.listen_addr or "—"],
            [t("external_ip"), config.external_ip or "—"],
            [t("api_endpoint"), f"localhost:{self.app.db.modules.ton_storage.api_port}"],
            [t("storage_path"), str(self.storage_path)],
            [t("config_path"), str(self.config_path)],
        ]
        self.app.console.print_table(rows, style=BoxStyle.SHARP)

    def _cmd_storage_log(self, _app: Any, args: list[str]) -> None:
        bounds = {"min": self.LOG_VERBOSITY_MIN, "max": self.LOG_VERBOSITY_MAX}
        if not args:
            self.app.console.print(
                f"{_('common.usage_prefix')} storage log <{self.LOG_VERBOSITY_MIN}-{self.LOG_VERBOSITY_MAX}>",
                Color.YELLOW,
            )
            return
        try:
            verbosity = int(args[0])
        except ValueError:
            self.app.console.print(_("modules.ton_storage.log.invalid", **bounds), Color.YELLOW)
            return
        if not self.LOG_VERBOSITY_MIN <= verbosity <= self.LOG_VERBOSITY_MAX:
            self.app.console.print(_("modules.ton_storage.log.invalid", **bounds), Color.YELLOW)
            return
        self.api.set_verbosity(verbosity)
        self.app.console.print(_("modules.ton_storage.log.updated", verbosity=verbosity), Color.GREEN)

    def _status_udp_port(self) -> tuple[str, str]:
        label = _("modules.ton_storage.status.udp_port")
        port = colorize_text(f"{self.app.db.modules.ton_storage.udp_port}", Color.CYAN)
        if self._port_open is None:
            status = colorize_text(_("common.status.collecting"), Color.GRAY)
        elif self._port_open:
            status = colorize_text(_("common.status.open"), Color.GREEN)
        else:
            status = colorize_text(_("common.status.closed"), Color.RED)
        return label, f"{port} · {status}"

    @staticmethod
    def _status_bags(data: BagsListResponse | None) -> tuple[str, str]:
        label = _("modules.ton_storage.status.bags")
        if data is None:
            return label, colorize_text(_("common.status.collecting"), Color.GRAY)
        count = colorize_text(str(len(data.bags)), Color.CYAN)
        total = utils.format_bytes(sum(b.size for b in data.bags))
        return label, f"{count} ({total})"

    def _status_disk_space(self) -> tuple[str, str]:
        label = _("modules.ton_storage.status.disk_space")
        if not self.app.db.modules.ton_storage.storage_path:
            return label, colorize_text(_("common.status.collecting"), Color.GRAY)
        path = colorize_text(self.app.db.modules.ton_storage.storage_path, Color.CYAN)
        usage = utils.sysinfo.get_disk_usage(self.app.db.modules.ton_storage.storage_path)
        used_gb = utils.bytes_to(usage.used, ByteUnit.GB)
        total_gb = utils.bytes_to(usage.total, ByteUnit.GB)
        pct = colorize_threshold(usage.percent, 90, logic="less", ending="%", precision=1)
        return label, f"{path} {used_gb:.1f}/{total_gb:.1f} GB ({pct})"

    def _build_go_binary(self) -> None:
        build_args = ["go", "build", "-o", str(self.bin_path), self.GO_PACKAGE_ENTRY]
        utils.run(build_args, cwd=str(self.src_path), check=True, timeout=600)

    def _read_verify_state(self) -> VerifyStateConfig:
        try:
            return utils.read_config(self.app.work_dir / self.VERIFY_BAG_STATE_FILENAME, VerifyStateConfig)
        except FileNotFoundError:
            return VerifyStateConfig()

    def _write_verify_state(self, state: VerifyStateConfig) -> None:
        utils.write_config(self.app.work_dir / self.VERIFY_BAG_STATE_FILENAME, state)

    def _format_bag_row(
        self,
        bag: BagInfo,
        verify_state: VerifyStateConfig,
    ) -> list[str | ColorText]:
        progress = f"{bag.downloaded / bag.size * 100:.1f}%" if bag.size else "—"
        verified_ts = verify_state.last_verified.get(bag.bag_id.upper(), 0)
        verified_text = utils.format_time_ago(verified_ts, lang=lang()) if verified_ts else "—"
        return [
            ColorText(bag.bag_id, color=self._bag_status_color(bag)),
            progress,
            utils.format_bytes(bag.size),
            str(bag.files_count),
            str(bag.peers),
            utils.format_bitrate(bag.download_speed * 8),
            utils.format_bitrate(bag.upload_speed * 8),
            verified_text,
        ]

    def _parse_bag_id(self, args: list[str], usage: str) -> str | None:
        if not args or not self.BAG_ID_RE.fullmatch(args[0]):
            self.app.console.print(f"{_('common.usage_prefix')} {usage}", Color.YELLOW)
            return None
        return args[0]

    @staticmethod
    def _bag_status_color(bag: BagInfo | BagDetails) -> Color:
        if not bag.active:
            return Color.YELLOW
        if not bag.download_all:
            return Color.GRAY
        if bag.completed:
            return Color.CYAN
        return Color.GREEN

    @staticmethod
    def _bag_status_text(bag: BagInfo | BagDetails) -> str:
        if not bag.active:
            key = "stopped"
        elif not bag.download_all:
            key = "idle"
        elif not bag.completed:
            key = "downloading"
        elif bag.seeding:
            key = "seeding"
        else:
            key = "completed"
        return _(f"modules.ton_storage.bags.status.{key}")

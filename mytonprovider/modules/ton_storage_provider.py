import ipaddress
import time
from collections.abc import Callable
from pathlib import Path
from random import randint
from typing import Any, ClassVar, Final

from mypycli import (
    Commandable,
    Installable,
    Startable,
    Statusable,
    Updatable,
    utils,
)
from mypycli.console.ansi import colorize_text, colorize_threshold
from mypycli.types import BoxStyle, ByteUnit, Color, ColorText, Command, StatusPanel
from pydantic import BaseModel, ConfigDict, Field
from ton_core import PrivateKey

from mytonprovider import constants
from mytonprovider.locales import _, lang
from mytonprovider.modules.ton_storage import TonStorageModule
from mytonprovider.utils import (
    build_go_binary,
    check_adnl_connection,
    check_update,
    chown_owner,
    clone_repo,
    create_status_footer,
    create_status_header,
    display_version,
)


class ProviderStorageEndpoint(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    base_url: str = Field(default="", alias="BaseURL")
    space_to_provide_megabytes: int = Field(default=0, alias="SpaceToProvideMegabytes")


class ProviderCronConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    enabled: bool = Field(default=True, alias="Enabled")


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    adnl_key: str = Field(default="", alias="ADNLKey")
    provider_key: str = Field(default="", alias="ProviderKey")
    listen_addr: str = Field(default="", alias="ListenAddr")
    external_ip: str = Field(default="", alias="ExternalIP")
    min_rate_per_mb_day: str = Field(default="0", alias="MinRatePerMBDay")
    min_span: int = Field(default=0, alias="MinSpan")
    max_span: int = Field(default=0, alias="MaxSpan")
    max_bag_size_bytes: int = Field(default=0, alias="MaxBagSizeBytes")
    storages: list[ProviderStorageEndpoint] = Field(default_factory=list, alias="Storages")
    cron: ProviderCronConfig = Field(default_factory=ProviderCronConfig, alias="CRON")

    @property
    def udp_port(self) -> int:
        return int(self.listen_addr.split(":")[1]) if ":" in self.listen_addr else 0

    @property
    def adnl_pubkey(self) -> str:
        return PrivateKey(self.adnl_key).public_key.as_hex.upper()

    @property
    def provider_pubkey(self) -> str:
        return self.provider_private_key.public_key.as_hex.upper()

    @property
    def provider_private_key(self) -> PrivateKey:
        return PrivateKey(self.provider_key)

    @property
    def storage_cost(self) -> float:
        return round(float(self.min_rate_per_mb_day) * 200 * 1024 * 30, 2)

    @property
    def space_gb(self) -> int:
        return self.storages[0].space_to_provide_megabytes // 1024 if self.storages else 0

    @property
    def max_bag_size_gb(self) -> int:
        return self.max_bag_size_bytes // 1024**3


class TonStorageProviderModule(
    Startable,
    Statusable,
    Installable,
    Updatable,
    Commandable,
):
    mandatory: ClassVar[bool] = True
    name: ClassVar[str] = "ton-storage-provider"
    label: ClassVar[str] = "TON Storage Provider"

    SERVICE_NAME: Final[str] = "ton-storage-provider"
    GIT_AUTHOR: ClassVar[str] = "xssnick"
    GIT_REPO: ClassVar[str] = "tonutils-storage-provider"
    GO_PACKAGE_ENTRY: ClassVar[str] = "cmd/main.go"

    CHECK_UPDATE_INTERVAL_SEC: Final[int] = 300
    BOOTSTRAP_WAIT_SEC: Final[int] = 10
    GO_BUILD_TIMEOUT_SEC: Final[int] = 60
    ADNL_CHECK_TIMEOUT_SEC: Final[float] = 2.5

    STORAGE_COST_REFERENCE_GB: Final[int] = 200
    PROVIDER_MIN_SPAN_SEC: Final[int] = 7 * 86400
    UDP_PORT_RANGE: Final[tuple[int, int]] = (38000, 38999)

    service: ClassVar[utils.SystemdService] = utils.SystemdService(SERVICE_NAME)
    src_path: ClassVar[Path] = constants.SRC_DIR / GIT_REPO
    bin_path: ClassVar[Path] = constants.BIN_DIR / GIT_REPO

    _update_available: bool | None = None
    _update_target: str | None = None
    _port_open: bool | None = None

    @property
    def repo(self) -> utils.LocalGitRepo:
        return utils.LocalGitRepo(self.src_path)

    @property
    def version(self) -> str:
        return display_version(self.repo, author=self.GIT_AUTHOR, repo_name=self.GIT_REPO)

    @property
    def storage_path(self) -> Path:
        ts = self.app.modules.get_by_class(TonStorageModule)
        return ts.storage_path / "provider"

    @property
    def config_path(self) -> Path:
        return self.storage_path / "config.json"

    def get_provider_config(self) -> ProviderConfig:
        return utils.read_config(self.config_path, ProviderConfig)

    def update_provider_config(self, config: ProviderConfig) -> None:
        utils.write_config(self.config_path, config)

    def apply_config(self, mutator: Callable[[ProviderConfig], None]) -> None:
        config = self.get_provider_config()
        mutator(config)
        self.update_provider_config(config)
        self.service.restart()

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "provider",
                description=_("modules.ton_storage_provider.cmd.provider.group"),
                children=[
                    Command(
                        "info",
                        self._cmd_info,
                        _("modules.ton_storage_provider.cmd.provider.info"),
                    ),
                    Command(
                        "set-cost",
                        self._cmd_set_cost,
                        _("modules.ton_storage_provider.cmd.provider.set_cost"),
                        "<ton-per-200gb-month>",
                    ),
                    Command(
                        "set-space",
                        self._cmd_set_space,
                        _("modules.ton_storage_provider.cmd.provider.set_space"),
                        "<gigabytes>",
                    ),
                    Command(
                        "set-external-ip",
                        self._cmd_set_external_ip,
                        _("modules.ton_storage_provider.cmd.provider.set_external_ip"),
                        "[ip]",
                    ),
                ],
            ),
        ]

    def on_install(self) -> None:
        self.app.console.print(_("modules.ton_storage_provider.install.building"), Color.GRAY)
        clone_repo(self.src_path, self.GIT_AUTHOR, self.GIT_REPO)
        self.build()

        ts = self.app.modules.get_by_class(TonStorageModule)
        if ts is None or not ts.service.exists:
            raise RuntimeError(f"{self.name}: ton-storage module must be installed first")

        install_args = self.app.db.install_args
        storage_cost = float(
            self.app.console.input(
                _("modules.ton_storage_provider.install.storage_cost"),
                default=str(
                    install_args.ton_storage_provider_storage_cost or constants.TON_STORAGE_PROVIDER_DEFAULT_COST
                ),
                validate=self._validate_storage_cost,
                env_var="TON_STORAGE_PROVIDER_STORAGE_COST",
            )
        )
        install_args.ton_storage_provider_storage_cost = storage_cost

        disk = utils.sysinfo.get_disk_usage(str(ts.storage_path))
        free_gb = int(utils.bytes_to(disk.free, ByteUnit.GB))
        total_gb = int(utils.bytes_to(disk.total, ByteUnit.GB))
        saved_space = install_args.ton_storage_provider_space_gb
        space_gb = int(
            self.app.console.input(
                _("modules.ton_storage_provider.install.space_to_provide", free=free_gb, total=total_gb),
                default=str(saved_space if saved_space is not None else int(free_gb * 0.9)),
                validate=lambda v: self._validate_space_gb(v, free_gb),
                env_var="TON_STORAGE_PROVIDER_SPACE_GB",
            )
        )
        install_args.ton_storage_provider_space_gb = space_gb
        max_bag_size_gb = min(constants.TON_STORAGE_PROVIDER_DEFAULT_MAX_BAG_SIZE, space_gb)

        self.storage_path.mkdir(parents=True, exist_ok=True)
        chown_owner(self.storage_path, self.app.work_dir)

        exec_start = (
            f"{self.bin_path}"
            f" --db {self.storage_path}/db"
            f" --config {self.config_path}"
            f" --network-config {constants.TON_CONFIG_PATH}"
        )
        self.service.create(
            exec_start=exec_start,
            user=self.app.work_dir.owner(),
            work_dir=str(self.storage_path),
            description=f"{self.SERVICE_NAME} daemon",
        )
        self.service.enable()
        self.service.start()
        time.sleep(self.BOOTSTRAP_WAIT_SEC)
        self.service.stop()

        udp_port = randint(*self.UDP_PORT_RANGE)
        config = self.get_provider_config()
        config.listen_addr = f"0.0.0.0:{udp_port}"
        config.external_ip = utils.get_public_ip() or ""
        config.min_span = self.PROVIDER_MIN_SPAN_SEC
        config.max_span = self._calculate_max_span(storage_cost)
        config.min_rate_per_mb_day = self._calculate_min_rate_per_mb_day(storage_cost)
        config.max_bag_size_bytes = max_bag_size_gb * 1024**3
        config.cron.enabled = True
        if not config.storages:
            config.storages.append(ProviderStorageEndpoint())
        config.storages[0].base_url = f"http://localhost:{self.app.db.modules.ton_storage.api_port}"
        config.storages[0].space_to_provide_megabytes = space_gb * 1024
        self.update_provider_config(config)
        chown_owner(self.storage_path, self.app.work_dir)
        self.service.start()

    def on_uninstall(self) -> None:
        self.service.disable()
        self.service.remove()

    def on_update(self) -> None:
        avail, _target = check_update(self.repo)
        if avail:
            self.repo.update()
            self.build()

    def build(self) -> None:
        build_go_binary(self.src_path, self.bin_path, self.GO_PACKAGE_ENTRY, timeout=self.GO_BUILD_TIMEOUT_SEC)
        chown_owner(self.src_path, self.app.work_dir)
        if self.service.exists:
            self.service.restart()

    def on_start(self) -> None:
        self.run_cycle(self.task_check_update, seconds=self.CHECK_UPDATE_INTERVAL_SEC)
        self.run_task(self.task_check_port)

    def on_stop(self) -> None:
        self._update_available = None
        self._update_target = None
        self._port_open = None

    def show_status(self) -> StatusPanel:
        config = self.get_provider_config()
        return StatusPanel(
            items=[
                self._status_udp_port(config),
                self._status_provider_pubkey(config),
                (),
                self._status_storage_cost(config),
                self._status_profit(config),
                self._status_provided(config),
                self._status_max_bag_size(config),
            ],
            header=create_status_header(
                self.label,
                self.version,
                target=self._update_target,
                available=bool(self._update_available),
            ),
            footer=create_status_footer(self.service, lang=lang()),
        )

    def task_check_update(self) -> None:
        try:
            self._update_available, self._update_target = check_update(self.repo)
        except Exception as exc:
            self.logger.warning(f"update check failed: {exc}")

    def task_check_port(self) -> None:
        config = self.get_provider_config()
        if not config.external_ip:
            self.logger.debug("external IP not configured")
            return
        public_ip = utils.get_public_ip()
        if public_ip and public_ip != config.external_ip:
            msg = _(
                "modules.ton_storage_provider.msg.external_ip_mismatch",
                ip=config.external_ip,
                public_ip=public_ip,
            )
            self.logger.warning(msg)
            self.app.console.print(msg, Color.YELLOW)
        if not config.adnl_key:
            self.logger.debug("adnl key empty")
            return
        if ":" not in config.listen_addr:
            self.logger.debug("listen_addr empty or invalid")
            return
        self._port_open = check_adnl_connection(
            config.external_ip,
            config.udp_port,
            config.adnl_pubkey,
            timeout=self.ADNL_CHECK_TIMEOUT_SEC,
        )

    def _cmd_info(self, app: Any, _args: list[str]) -> None:
        config = self.get_provider_config()

        def t(key: str) -> ColorText:
            return ColorText(_(f"modules.ton_storage_provider.info.{key}"), color=Color.CYAN)

        rows: list[list[str | ColorText]] = [
            [t("metric"), t("value")],
            [t("pubkey"), config.provider_pubkey],
            [t("adnl_pubkey"), config.adnl_pubkey],
            [t("listen_addr"), config.listen_addr or "—"],
            [t("external_ip"), config.external_ip or "—"],
            [t("storage_path"), str(self.storage_path)],
            [t("config_path"), str(self.config_path)],
        ]
        app.console.print_table(rows, style=BoxStyle.SHARP)

    def _cmd_set_cost(self, app: Any, args: list[str]) -> None:
        if not args:
            app.console.print(f"{_('common.usage_prefix')} provider set-cost <ton-per-200gb-month>", Color.YELLOW)
            return
        err = self._validate_storage_cost(args[0])
        if err is not None:
            app.console.print(err, Color.RED)
            return

        cost = float(args[0])

        def mutate(cfg: ProviderConfig) -> None:
            cfg.min_rate_per_mb_day = self._calculate_min_rate_per_mb_day(cost)
            cfg.max_span = self._calculate_max_span(cost)

        self.apply_config(mutate)
        app.console.print(_("modules.ton_storage_provider.provider.cost_set", cost=cost), Color.GREEN)

    def _cmd_set_space(self, app: Any, args: list[str]) -> None:
        if not args:
            app.console.print(f"{_('common.usage_prefix')} provider set-space <gigabytes>", Color.YELLOW)
            return
        ts = app.modules.get_by_class(TonStorageModule)
        disk = utils.sysinfo.get_disk_usage(str(ts.storage_path))
        free_gb = int(utils.bytes_to(disk.free, ByteUnit.GB))
        max_gb = free_gb + self.get_provider_config().space_gb

        err = self._validate_space_gb(args[0], max_gb)
        if err is not None:
            app.console.print(err, Color.RED)
            return

        space = int(args[0])

        def mutate(cfg: ProviderConfig) -> None:
            if not cfg.storages:
                cfg.storages.append(ProviderStorageEndpoint())
            cfg.storages[0].space_to_provide_megabytes = space * 1024

        self.apply_config(mutate)
        app.console.print(_("modules.ton_storage_provider.provider.space_set", space=space), Color.GREEN)

    def _cmd_set_external_ip(self, app: Any, args: list[str]) -> None:
        ip = args[0] if args else (utils.get_public_ip() or "")
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            app.console.print(_("modules.ton_storage_provider.msg.bad_ip", ip=ip), Color.RED)
            return

        def mutate(cfg: ProviderConfig) -> None:
            cfg.external_ip = ip

        self.apply_config(mutate)
        app.console.print(_("modules.ton_storage_provider.msg.external_ip_set", ip=ip), Color.GREEN)

    def _status_udp_port(self, config: ProviderConfig) -> tuple[str, str]:
        label = _("modules.ton_storage_provider.status.udp_port")
        port = colorize_text(str(config.udp_port), Color.CYAN)
        if self._port_open is None:
            status = colorize_text(_("common.status.collecting"), Color.GRAY)
        elif self._port_open:
            status = colorize_text(_("common.status.open"), Color.GREEN)
        else:
            status = colorize_text(_("common.status.closed"), Color.RED)
        return label, f"{port} · {status}"

    @staticmethod
    def _status_provider_pubkey(config: ProviderConfig) -> tuple[str, str]:
        label = _("modules.ton_storage_provider.status.pubkey")
        return label, colorize_text(config.provider_pubkey, Color.CYAN)

    @staticmethod
    def _status_storage_cost(config: ProviderConfig) -> tuple[str, str]:
        label = _("modules.ton_storage_provider.status.storage_cost")
        return label, f"{config.storage_cost} TON/200GB/mo"

    def _status_profit(self, config: ProviderConfig) -> tuple[str, str]:
        label = _("modules.ton_storage_provider.status.profit")
        used_gb = self.get_used_space_gb()
        total_gb = config.space_gb
        rate = config.storage_cost / 200
        real = round(used_gb * rate, 2)
        maximum = round(total_gb * rate, 2)
        real_text = colorize_text(f"{real}", Color.GREEN)
        max_text = colorize_text(f"{maximum}", Color.YELLOW)
        return label, f"{real_text} TON (max {max_text} TON)"

    def _status_provided(self, config: ProviderConfig) -> tuple[str, str]:
        label = _("modules.ton_storage_provider.status.provided")
        used_gb = self.get_used_space_gb()
        total_gb = config.space_gb
        pct = (used_gb / total_gb * 100) if total_gb else 0.0
        pct_text = colorize_threshold(pct, 90, logic="less", ending="%", precision=1)
        return label, f"{used_gb:.2f}/{total_gb} GB ({pct_text})"

    @staticmethod
    def _status_max_bag_size(config: ProviderConfig) -> tuple[str, str]:
        label = _("modules.ton_storage_provider.status.max_bag_size")
        return label, f"{config.max_bag_size_gb} GB"

    def get_used_space_gb(self) -> float:
        try:
            ts = self.app.modules.get_by_class(TonStorageModule)
            data = ts.api.list_bags()
        except Exception:
            return 0.0
        total_bytes = sum(b.size for b in data.bags)
        return float(utils.bytes_to(total_bytes, ByteUnit.GB))

    def _calculate_max_span(self, storage_cost: float) -> int:
        max_span_hard_limit = 4_294_967_290
        min_max_span_sec = 30 * 86400
        min_proof_cost_ton = 0.05
        min_bag_size_mb = 400
        rate_per_mb_sec = float(storage_cost) / self.STORAGE_COST_REFERENCE_GB / 1024 / 30 / 24 / 3600
        max_span = int(min_proof_cost_ton / (rate_per_mb_sec * min_bag_size_mb))
        if max_span < min_max_span_sec:
            return min_max_span_sec
        return min(max_span, max_span_hard_limit)

    @staticmethod
    def _calculate_min_rate_per_mb_day(storage_cost: float) -> str:
        rate = float(storage_cost) / 200 / 1024 / 30
        return f"{rate:.9f}"

    @staticmethod
    def _validate_storage_cost(value: str) -> str | None:
        try:
            cost = float(value)
        except ValueError:
            return _("modules.ton_storage_provider.provider.bad_cost")
        if cost <= 0:
            return _("modules.ton_storage_provider.provider.bad_cost")
        return None

    @staticmethod
    def _validate_space_gb(value: str, max_gb: int) -> str | None:
        try:
            space = int(value)
        except ValueError:
            return _("modules.ton_storage_provider.provider.bad_space", min=1, max=max_gb)
        if not 1 <= space <= max_gb:
            return _("modules.ton_storage_provider.provider.bad_space", min=1, max=max_gb)
        return None

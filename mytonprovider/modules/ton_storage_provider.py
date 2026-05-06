import shutil
import time
from collections.abc import Callable
from pathlib import Path
from random import randint
from typing import Any, ClassVar, Final, cast

from mypycli import (
    Commandable,
    Installable,
    Startable,
    Statusable,
    Updatable,
    utils,
)
from mypycli.console.ansi import colorize_text, colorize_threshold
from mypycli.types import BoxStyle, ByteUnit, Color, ColorText, Command
from pydantic import BaseModel, ConfigDict, Field
from ton_core import PrivateKey

from mytonprovider import constants
from mytonprovider.locales import _, lang
from mytonprovider.modules.ton_storage import TonStorageModule
from mytonprovider.utils import (
    check_adnl_connection,
    check_repo_update,
    create_status_footer,
    create_status_header,
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
    STORAGE_COST_REFERENCE_GB: Final[int] = 200
    PROVIDER_MIN_SPAN_SEC: Final[int] = 7 * 86400
    MAX_BAG_SIZE_GB_MIN: Final[int] = 1
    MAX_BAG_SIZE_GB_MAX: Final[int] = 1024

    GO_PACKAGE_REPO: ClassVar[str] = "tonutils-storage-provider"
    GO_PACKAGE_ENTRY: ClassVar[str] = "cmd/main.go"

    service: ClassVar[utils.SystemdService] = utils.SystemdService(SERVICE_NAME)
    src_path: ClassVar[Path] = constants.SRC_DIR / GO_PACKAGE_REPO
    bin_path: ClassVar[Path] = constants.BIN_DIR / GO_PACKAGE_REPO

    _update_available: bool | None = None
    _update_target: str | None = None
    _port_open: bool | None = None

    @property
    def repo(self) -> utils.LocalGitRepo:
        return utils.LocalGitRepo(self.src_path)

    @property
    def version(self) -> str:
        info = self.repo.info
        return info.version if info.tag else info.commit_short

    @property
    def storage_path(self) -> Path:
        ts = cast(TonStorageModule, self.app.modules.get("ton-storage"))
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
        self.service.stop()
        self.update_provider_config(config)
        self.service.start()

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "provider",
                description=_("modules.ton_storage_provider.cmd.provider.group"),
                children=[
                    Command(
                        "info",
                        self._cmd_provider_info,
                        _("modules.ton_storage_provider.cmd.provider.info"),
                    ),
                    Command(
                        "set-cost",
                        self._cmd_provider_set_cost,
                        _("modules.ton_storage_provider.cmd.provider.set_cost"),
                        "<ton-per-200gb-month>",
                    ),
                    Command(
                        "set-space",
                        self._cmd_provider_set_space,
                        _("modules.ton_storage_provider.cmd.provider.set_space"),
                        "<gigabytes>",
                    ),
                    Command(
                        "set-bag-size",
                        self._cmd_provider_set_bag_size,
                        _("modules.ton_storage_provider.cmd.provider.set_bag_size"),
                        "<gigabytes>",
                    ),
                ],
            ),
        ]

    def on_install(self) -> None:
        if not self.bin_path.exists():
            raise RuntimeError(f"{self.name}: binary not found at {self.bin_path}")

        ts = cast(TonStorageModule, self.app.modules.get("ton-storage"))
        if ts is None or not self.app.db.modules.ton_storage.enabled:
            raise RuntimeError(f"{self.name}: ton-storage module must be installed first")

        install_args = self.app.db.install_args
        default_cost = install_args.ton_storage_provider_storage_cost or constants.TON_STORAGE_PROVIDER_DEFAULT_COST
        storage_cost = float(
            self.app.console.input(
                _("modules.ton_storage_provider.install.storage_cost"),
                default=str(default_cost),
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
                default=str(saved_space) if saved_space is not None else None,
                validate=lambda v: self._validate_space_gb(v, free_gb),
                env_var="TON_STORAGE_PROVIDER_SPACE_GB",
            )
        )
        install_args.ton_storage_provider_space_gb = space_gb

        max_bag_size_gb = int(
            self.app.console.input(
                _(
                    "modules.ton_storage_provider.install.max_bag_size",
                    min=self.MAX_BAG_SIZE_GB_MIN,
                    max=self.MAX_BAG_SIZE_GB_MAX,
                ),
                default=str(
                    install_args.ton_storage_provider_max_bag_size_gb
                    or constants.TON_STORAGE_PROVIDER_DEFAULT_MAX_BAG_SIZE
                ),
                validate=self._validate_max_bag_size,
                env_var="TON_STORAGE_PROVIDER_MAX_BAG_SIZE_GB",
            )
        )
        install_args.ton_storage_provider_max_bag_size_gb = max_bag_size_gb

        self.storage_path.mkdir(parents=True, exist_ok=True)
        owner = self.app.work_dir.owner()
        shutil.chown(self.storage_path, user=owner, group=owner)

        exec_start = (
            f"{self.bin_path}"
            f" --db {self.storage_path}/db"
            f" --config {self.config_path}"
            f" --network-config {constants.TON_CONFIG_PATH}"
        )
        self.service.create(
            exec_start=exec_start,
            user=owner,
            work_dir=str(self.storage_path),
            description=f"{self.SERVICE_NAME} daemon",
        )
        self.service.enable()
        self.service.start()
        time.sleep(10)
        self.service.stop()

        udp_port = randint(38000, 38999)
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
        self.service.start()

    def on_uninstall(self) -> None:
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

    def on_start(self) -> None:
        self.run_task(self.task_check_update)
        self.run_task(self.task_check_port)

    def on_stop(self) -> None:
        self._update_available = None
        self._update_target = None
        self._port_open = None

    def show_status(self) -> None:
        config = self.get_provider_config()
        self.app.console.print_panel(
            [
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
            min_width=constants.STATUS_PANEL_WIDTH,
        )

    def task_check_update(self) -> None:
        self._update_available, self._update_target = check_repo_update(self.repo)

    def task_check_port(self) -> None:
        config = self.get_provider_config()
        own_ip = config.external_ip or utils.get_public_ip()
        if not own_ip:
            self.logger.debug("external IP unknown")
            return
        if not config.adnl_key:
            self.logger.debug("adnl key empty")
            return
        if ":" not in config.listen_addr:
            self.logger.debug("listen_addr empty or invalid")
            return
        self._port_open = check_adnl_connection(
            own_ip,
            config.udp_port,
            config.adnl_pubkey,
            timeout=self.app.db.settings.adnl_checker_api.request_timeout,
        )

    def _cmd_provider_info(self, _app: Any, _args: list[str]) -> None:
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
        self.app.console.print_table(rows, style=BoxStyle.SHARP)

    def _cmd_provider_set_cost(self, _app: Any, args: list[str]) -> None:
        if not args:
            self.app.console.print(f"{_('common.usage_prefix')} provider set-cost <ton-per-200gb-month>", Color.YELLOW)
            return
        err = self._validate_storage_cost(args[0])
        if err is not None:
            self.app.console.print(err, Color.RED)
            return

        cost = float(args[0])

        def mutate(cfg: ProviderConfig) -> None:
            cfg.min_rate_per_mb_day = self._calculate_min_rate_per_mb_day(cost)
            cfg.max_span = self._calculate_max_span(cost)

        self.apply_config(mutate)
        self.app.console.print(_("modules.ton_storage_provider.provider.cost_set", cost=cost), Color.GREEN)

    def _cmd_provider_set_space(self, _app: Any, args: list[str]) -> None:
        if not args:
            self.app.console.print(f"{_('common.usage_prefix')} provider set-space <gigabytes>", Color.YELLOW)
            return
        ts = cast(TonStorageModule, self.app.modules.get("ton-storage"))
        disk = utils.sysinfo.get_disk_usage(str(ts.storage_path))
        free_gb = int(utils.bytes_to(disk.free, ByteUnit.GB))
        max_gb = free_gb + self.get_provider_config().space_gb

        err = self._validate_space_gb(args[0], max_gb)
        if err is not None:
            self.app.console.print(err, Color.RED)
            return

        space = int(args[0])

        def mutate(cfg: ProviderConfig) -> None:
            if not cfg.storages:
                cfg.storages.append(ProviderStorageEndpoint())
            cfg.storages[0].space_to_provide_megabytes = space * 1024

        self.apply_config(mutate)
        self.app.console.print(_("modules.ton_storage_provider.provider.space_set", space=space), Color.GREEN)

    def _cmd_provider_set_bag_size(self, _app: Any, args: list[str]) -> None:
        if not args:
            self.app.console.print(f"{_('common.usage_prefix')} provider set-bag-size <gigabytes>", Color.YELLOW)
            return
        err = self._validate_max_bag_size(args[0])
        if err is not None:
            self.app.console.print(err, Color.RED)
            return

        size = int(args[0])
        self.apply_config(lambda cfg: setattr(cfg, "max_bag_size_bytes", size * 1024**3))
        self.app.console.print(_("modules.ton_storage_provider.provider.bag_size_set", size=size), Color.GREEN)

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

    def _build_go_binary(self) -> None:
        build_args = ["go", "build", "-o", str(self.bin_path), self.GO_PACKAGE_ENTRY]
        utils.run(build_args, cwd=str(self.src_path), check=True, timeout=600)

    def get_used_space_gb(self) -> float:
        try:
            ts = cast(TonStorageModule, self.app.modules.get("ton-storage"))
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

    def _validate_max_bag_size(self, value: str) -> str | None:
        bounds = {"min": self.MAX_BAG_SIZE_GB_MIN, "max": self.MAX_BAG_SIZE_GB_MAX}
        try:
            size = int(value)
        except ValueError:
            return _("modules.ton_storage_provider.provider.bad_bag_size", **bounds)
        if not self.MAX_BAG_SIZE_GB_MIN <= size <= self.MAX_BAG_SIZE_GB_MAX:
            return _("modules.ton_storage_provider.provider.bad_bag_size", **bounds)
        return None

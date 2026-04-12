from __future__ import annotations

import asyncio
import os
import pwd
import subprocess
import time
from pathlib import Path
from random import randint
from typing import TYPE_CHECKING, ClassVar, Final

from asgiref.sync import async_to_sync
from mypylib import (
    DEBUG,
    ERROR,
    ByteUnit,
    Dict,
    add2systemd,
    bcolors,
    color_print,
    get_disk_space,
    get_own_ip,
    get_service_status,
    get_service_uptime,
    read_config_from_file,
    time2human,
    write_config_to_file,
)
from ton_core import (
    Address,
    NetworkGlobalID,
    PrivateKey,
    normalize_hash,
    to_amount,
    to_nano,
)
from tonutils.clients import LiteBalancer
from tonutils.contracts import WalletV3R2
from tonutils.types import DEFAULT_ADNL_RETRY_POLICY

from mytonprovider import constants
from mytonprovider.modules.core import (
    Commandable,
    Installable,
    Startable,
    Statusable,
    Updatable,
)
from mytonprovider.modules.ton_storage import TonStorageModule
from mytonprovider.types import Command, InstallContext
from mytonprovider.utils import (
    check_adnl_connection,
    get_service_status_color,
    read_git_clone_version,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from mypylib import MyPyClass

    from mytonprovider.types import Channel, InstalledVersion


SERVICE_START_SLEEP_SEC: Final[int] = 10
INSTALL_BUILD_TIMEOUT_SEC: Final[int] = 300

DEFAULT_SEND_TIMEOUT_SEC: Final[float] = 60.0
REGISTRATION_WAIT_TIMEOUT_SEC: Final[float] = 60.0
TRANSFER_WAIT_TIMEOUT_SEC: Final[float] = 60.0
WAIT_FOR_MESSAGE_POLL_INTERVAL_SEC: Final[float] = 2.0
GET_TRANSACTIONS_LIMIT: Final[int] = 10

PROVIDER_SUBDIR: Final[str] = "provider"
DB_SUBDIR: Final[str] = "db"
PROVIDER_CONFIG_NAME: Final[str] = "config.json"

GIT_CLONE_DIR: Final[Path] = Path("/usr/src") / constants.TON_STORAGE_PROVIDER_REPO
BIN_PATH: Final[Path] = Path("/usr/local/bin") / constants.TON_STORAGE_PROVIDER_REPO

# Pricing formulas from xssnick/tonutils-storage-provider
STORAGE_COST_REFERENCE_GB: Final[int] = 200
PROVIDER_MIN_SPAN_SEC: Final[int] = 7 * 86400
MIN_MAX_SPAN_SEC: Final[int] = 30 * 86400
MAX_SPAN_HARD_LIMIT: Final[int] = 4_294_967_290  # uint32 max - 5
MIN_PROOF_COST_TON: Final[float] = 0.05
MIN_BAG_SIZE_BYTES: Final[int] = 400

MAX_BAG_SIZE_GB_MIN: Final[int] = 1
MAX_BAG_SIZE_GB_MAX: Final[int] = 1024


class TonStorageProviderModule(
    Startable,
    Statusable,
    Installable,
    Updatable,
    Commandable,
):
    """Wraps the ``ton-storage-provider`` Go daemon (xssnick/tonutils-storage-provider)."""

    name = "ton-storage-provider"
    service_name = "ton-storage-provider"
    mandatory = False

    github_author = constants.TON_STORAGE_PROVIDER_AUTHOR
    github_repo = constants.TON_STORAGE_PROVIDER_REPO
    default_version = constants.TON_STORAGE_PROVIDER_VERSION
    entry_point: ClassVar[str] = "cmd/main.go"

    def __init__(self, app: MyPyClass) -> None:
        super().__init__(app)
        self._port_check_ok: bool | None = None
        self._port_check_error: str | None = None
        self._ton_client: LiteBalancer | None = None

    @property
    def ton_client(self) -> LiteBalancer:
        if self._ton_client is None:
            self._ton_client = LiteBalancer.from_config(
                network=NetworkGlobalID.MAINNET,
                config=str(constants.GLOBAL_CONFIG_PATH),
                retry_policy=DEFAULT_ADNL_RETRY_POLICY,
            )
        return self._ton_client

    @property
    def is_enabled(self) -> bool:
        ts = self.app.db.ton_storage
        return ts is not None and "provider" in ts

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
        color_print("{cyan}===[ Local provider status ]==={endc}")
        self._print_module_name()
        self._print_provider_pubkey()
        self._print_provider_wallet()
        self._print_storage_cost()
        self._print_profit()
        self._print_provider_space()
        self._print_max_bag_size()
        self._print_port_status()
        self._print_service_status()
        self._print_version()

    def get_commands(self) -> list[Command]:
        return [
            Command(
                name="register",
                func=self._cmd_register,
                description=self.app.translate("register_cmd"),
            ),
            Command(
                name="import_wallet",
                func=self._cmd_import_wallet,
                description=self.app.translate("import_wallet_cmd"),
            ),
            Command(
                name="export_wallet",
                func=self._cmd_export_wallet,
                description=self.app.translate("export_wallet_cmd"),
            ),
            Command(
                name="transfer_ton",
                func=self._cmd_transfer_ton,
                description=self.app.translate("transfer_ton_cmd"),
            ),
            Command(
                name="set_storage_cost",
                func=self._cmd_set_storage_cost,
                description=self.app.translate("set_storage_cost_cmd"),
            ),
            Command(
                name="set_provider_space",
                func=self._cmd_set_provider_space,
                description=self.app.translate("set_provider_space_cmd"),
            ),
            Command(
                name="set_max_bag_size",
                func=self._cmd_set_max_bag_size,
                description=self.app.translate("set_max_bag_size_cmd"),
            ),
        ]

    def install(self, context: InstallContext) -> None:
        """Build tonutils-storage-provider, materialize config, create service."""
        print(f"Installing {self.name} module")

        if os.geteuid() != 0:
            raise RuntimeError(f"{self.name}: install must be run as root (use sudo)")

        try:
            pwd.getpwnam(context.user)
        except KeyError as exc:
            raise RuntimeError(f"{self.name}: user {context.user!r} does not exist") from exc

        if self.app.db.ton_storage is None:
            raise RuntimeError(
                f"{self.name}: ton_storage module must be installed before provider"
            )

        if context.storage_path is None:
            raise RuntimeError(f"{self.name}: storage_path is required")
        if context.storage_cost is None:
            raise RuntimeError(f"{self.name}: storage_cost is required")
        if context.space_to_provide_gigabytes is None:
            raise RuntimeError(f"{self.name}: space_to_provide_gigabytes is required")
        if context.max_bag_size_gigabytes is None:
            raise RuntimeError(f"{self.name}: max_bag_size_gigabytes is required")

        provider_path = context.storage_path / PROVIDER_SUBDIR
        db_dir = provider_path / DB_SUBDIR
        provider_config_path = provider_path / PROVIDER_CONFIG_NAME

        udp_port = randint(constants.PORT_RANGE_MIN, constants.PORT_RANGE_MAX)

        try:
            update_args = self.build_update_args(self.default_channel())
            subprocess.run(update_args, check=True, timeout=INSTALL_BUILD_TIMEOUT_SEC)

            provider_path.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["chown", f"{context.user}:{context.user}", str(provider_path)],
                check=True,
            )

            start_cmd = (
                f"{BIN_PATH} "
                f"--db {db_dir} "
                f"--config {provider_config_path} "
                f"-network-config {constants.GLOBAL_CONFIG_PATH}"
            )
            add2systemd(
                name=self.service_name,
                user=context.user,
                start=start_cmd,
                workdir=str(provider_path),
                force=True,
            )

            print(f"Starting {self.service_name} to generate config")
            self.app.start_service(self.service_name, sleep=SERVICE_START_SLEEP_SEC)
            self.app.stop_service(self.service_name)

            provider_config = read_config_from_file(str(provider_config_path))
            api = self.app.db.ton_storage.api
            provider_config.ListenAddr = f"0.0.0.0:{udp_port}"
            provider_config.ExternalIP = get_own_ip()
            provider_config.MinSpan = PROVIDER_MIN_SPAN_SEC
            provider_config.MaxSpan = self._calculate_max_span(context.storage_cost)
            provider_config.MinRatePerMBDay = self._calculate_min_rate_per_mb_day(context.storage_cost)
            provider_config.MaxBagSizeBytes = context.max_bag_size_gigabytes * 1024**3
            provider_config.Storages[0].BaseURL = f"http://{api.host}:{api.port}"
            provider_config.Storages[0].SpaceToProvideMegabytes = self._calculate_space_to_provide_megabytes(
                context.space_to_provide_gigabytes,
            )
            provider_config.CRON.Enabled = True
            write_config_to_file(str(provider_config_path), provider_config)

            provider = Dict()
            provider.config_path = str(provider_config_path)
            provider.is_already_registered = False
            self.app.db.ton_storage.provider = provider
            self.app.save()

            print(f"Starting {self.service_name} service")
            self.app.start_service(self.service_name)
        except Exception:
            color_print(f"{{red}}{self.name}: install failed, rolling back{{endc}}")
            self._rollback_mconfig()
            raise

    def _rollback_mconfig(self) -> None:
        """Best-effort removal of the ``ton_storage.provider`` section from db."""
        if self.app.db.ton_storage is None:
            return
        if "provider" not in self.app.db.ton_storage:
            return
        del self.app.db.ton_storage["provider"]
        try:
            self.app.save()
        except Exception as exc:
            self.app.add_log(f"{self.name}: rollback save failed: {exc}", ERROR)
            self.app.db.ton_storage.pop("provider", None)

    def _check_update_background(self) -> None:
        try:
            self._update_status = self.check_update()
        except (RuntimeError, ValueError) as exc:
            self.app.add_log(f"{self.name}: update check failed: {exc}", DEBUG)
            self._update_status = None

    def _check_port_background(self) -> None:
        try:
            provider_config = self._read_provider_config()
            own_ip = get_own_ip()
            if provider_config.ExternalIP != own_ip:
                raise RuntimeError(
                    f"provider_config.ExternalIP ({provider_config.ExternalIP}) != own_ip ({own_ip})"
                )
            _listen_ip, port_str = provider_config.ListenAddr.split(":")
            port = int(port_str)
            adnl_pubkey = PrivateKey(provider_config.ADNLKey).public_key.as_hex.upper()
        except (RuntimeError, ValueError, AttributeError, TypeError) as exc:
            self.app.add_log(f"{self.name}: port check setup failed: {exc}", DEBUG)
            self._port_check_ok = None
            self._port_check_error = str(exc)
            return

        ok, error = check_adnl_connection(own_ip, port, adnl_pubkey)
        self._port_check_ok = ok
        self._port_check_error = error
        if not ok:
            self.app.add_log(f"{self.name}: ADNL port check failed: {error}", DEBUG)

    def _read_provider_config(self) -> Dict:
        provider = self.app.db.ton_storage.provider
        return read_config_from_file(str(provider.config_path))

    def _write_provider_config(self, provider_config: Dict) -> None:
        provider = self.app.db.ton_storage.provider
        write_config_to_file(str(provider.config_path), provider_config)

    def _apply_provider_config(self, mutator: Callable[[Dict], None]) -> None:
        """Apply *mutator* to provider config and restart the service."""
        provider_config = self._read_provider_config()
        mutator(provider_config)

        config_path = str(self.app.db.ton_storage.provider.config_path)
        self.app.stop_service(self.service_name)
        try:
            write_config_to_file(config_path, provider_config)
        finally:
            self.app.start_service(self.service_name, sleep=SERVICE_START_SLEEP_SEC)

    def get_provider_pubkey(self) -> str:
        """Return the provider wallet's public key (uppercase hex)."""
        return PrivateKey(self._read_provider_config().ProviderKey).public_key.as_hex.upper()

    def get_adnl_pubkey(self) -> str:
        """Return the provider's ADNL public key (uppercase hex)."""
        return PrivateKey(self._read_provider_config().ADNLKey).public_key.as_hex.upper()

    async def _get_refreshed_wallet(self) -> WalletV3R2:
        """Construct provider wallet from ProviderKey and refresh its on-chain state."""
        private_key = PrivateKey(self._read_provider_config().ProviderKey)
        wallet = WalletV3R2.from_private_key(self.ton_client, private_key)
        await wallet.refresh()
        return wallet

    async def _send_and_wait(
        self,
        wallet: WalletV3R2,
        destination: Address,
        amount: int,
        body: str | None = None,
        *,
        timeout: float = DEFAULT_SEND_TIMEOUT_SEC,
    ) -> str:
        """Send *amount* from *wallet* to *destination* and wait for on-chain confirmation."""
        end_lt = wallet.last_transaction_lt or 0
        msg = await wallet.transfer(
            destination=destination,
            amount=amount,
            body=body,
        )
        await self._wait_for_message(
            wallet.address, msg.normalized_hash, end_lt, timeout=timeout,
        )
        return msg.normalized_hash

    async def _wait_for_message(
        self,
        address: Address,
        target_hash: str,
        end_lt: int,
        *,
        timeout: float = DEFAULT_SEND_TIMEOUT_SEC,
        poll_interval: float = WAIT_FOR_MESSAGE_POLL_INTERVAL_SEC,
    ) -> None:
        """Poll transactions until a message with *target_hash* lands at *address*."""
        target = target_hash.lower()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            txs = await self.ton_client.get_transactions(
                address, limit=GET_TRANSACTIONS_LIMIT,
            )
            for tx in txs:
                if tx.lt <= end_lt:
                    continue
                if tx.in_msg is not None and normalize_hash(tx.in_msg).lower() == target:
                    return
                for out_msg in tx.out_msgs:
                    if normalize_hash(out_msg).lower() == target:
                        return
            await asyncio.sleep(poll_interval)
        raise TimeoutError(
            f"Message {target_hash} not found at "
            f"{address.to_str(is_bounceable=False)} within {timeout}s"
        )

    @async_to_sync
    async def _cmd_register(self, args: list[str]) -> None:
        provider = self.app.db.ton_storage.provider
        if provider and provider.is_already_registered and "--force" not in args:
            color_print(f"{{green}}{self.app.translate('provider_already_registered')}{{endc}}")
            return

        try:
            async with self.ton_client:
                wallet = await self._get_refreshed_wallet()
                if wallet.balance < to_nano(constants.REGISTRATION_MIN_BALANCE):
                    color_print(f"{{red}}{self.app.translate('low_provider_balance')}{{endc}}")
                    return
                body = f"{constants.REGISTRATION_COMMENT_PREFIX}{self.get_provider_pubkey().lower()}"
                await self._send_and_wait(
                    wallet,
                    destination=Address(constants.REGISTRATION_ADDRESS),
                    amount=to_nano(constants.REGISTRATION_AMOUNT),
                    body=body,
                    timeout=REGISTRATION_WAIT_TIMEOUT_SEC,
                )
        except Exception as exc:
            color_print(f"{{red}}Register failed:{{endc}} {exc}")
            return

        self.app.db.ton_storage.provider.is_already_registered = True
        self.app.save()
        color_print("provider register {green}OK{endc}")

    def _cmd_import_wallet(self, args: list[str]) -> None:
        if not args:
            color_print("{red}Usage:{endc} import_wallet <privkey | mnemonic-words...>")
            return
        words = " ".join(args).strip().split()
        try:
            if len(words) == 1:
                private_key = PrivateKey(words[0])
                wallet = WalletV3R2.from_private_key(self.ton_client, private_key)
            else:
                wallet, _pub, private_key, _mnemo = WalletV3R2.from_mnemonic(
                    self.ton_client, words,
                )
        except Exception as exc:
            color_print(f"{{red}}Error:{{endc}} invalid key or mnemonic: {exc}")
            return

        provider_config = self._read_provider_config()
        provider_config.ProviderKey = private_key.keypair.as_b64
        self._write_provider_config(provider_config)
        address = wallet.address.to_str(is_bounceable=False)
        color_print(f"import_wallet {{green}}OK{{endc}} — address: {address}")

    @async_to_sync
    async def _cmd_export_wallet(self, args: list[str]) -> None:
        try:
            async with self.ton_client:
                wallet = await self._get_refreshed_wallet()
        except Exception as exc:
            color_print(f"{{red}}Error:{{endc}} {exc}")
            return

        private_key = PrivateKey(self._read_provider_config().ProviderKey)
        seed = PrivateKey(private_key.as_bytes)

        print(f"Address:           {wallet.address.to_str(is_bounceable=False)}")
        print(f"Balance:           {to_amount(wallet.balance, precision=4)} TON")
        print(f"Private key (b64): {seed.as_b64}")
        print(f"Private key (hex): {seed.as_hex}")

    @async_to_sync
    async def _cmd_transfer_ton(self, args: list[str]) -> None:
        if len(args) < 2:
            color_print("{red}Usage:{endc} transfer_ton <address> <amount> [comment...]")
            return

        try:
            destination = Address(args[0])
        except Exception as exc:
            color_print(f"{{red}}Error: invalid address: {exc}{{endc}}")
            return

        try:
            amount_nanoton = to_nano(args[1])
        except Exception:
            color_print(f"{{red}}Error: amount must be a number (got {args[1]!r}){{endc}}")
            return

        body: str | None = " ".join(args[2:]) if len(args) > 2 else None

        amount_ton = to_amount(amount_nanoton, precision=4)
        dest_str = destination.to_str(is_bounceable=False)
        comment_suffix = f" with comment {body!r}" if body else ""
        prompt = f"Transfer {amount_ton} TON to {dest_str}{comment_suffix}? [y/N]: "
        if input(prompt).strip().lower() != "y":
            color_print("{yellow}Cancelled{endc}")
            return

        try:
            async with self.ton_client:
                wallet = await self._get_refreshed_wallet()
                msg_hash = await self._send_and_wait(
                    wallet,
                    destination=destination,
                    amount=amount_nanoton,
                    body=body,
                    timeout=TRANSFER_WAIT_TIMEOUT_SEC,
                )
        except Exception as exc:
            color_print(f"{{red}}transfer_ton failed:{{endc}} {exc}")
            return

        color_print(f"transfer_ton {{green}}OK{{endc}} — hash: {msg_hash}")

    def _cmd_set_storage_cost(self, args: list[str]) -> None:
        try:
            cost = float(args[0])
        except (IndexError, ValueError):
            color_print("{red}Usage:{endc} set_storage_cost <ton_per_200gb_month>")
            return
        if cost <= 0:
            color_print("{red}Error: storage_cost must be > 0{endc}")
            return

        def mutate(cfg: Dict) -> None:
            cfg.MinRatePerMBDay = self._calculate_min_rate_per_mb_day(cost)
            cfg.MaxSpan = self._calculate_max_span(cost)

        try:
            self._apply_provider_config(mutate)
        except Exception as exc:
            color_print(f"{{red}}set_storage_cost failed:{{endc}} {exc}")
            return

        color_print(f"set_storage_cost = {cost} TON {{green}}OK{{endc}}")

    def _cmd_set_provider_space(self, args: list[str]) -> None:
        try:
            requested_gb = int(args[0])
        except (IndexError, ValueError):
            color_print("{red}Usage:{endc} set_provider_space <gigabytes>")
            return
        if requested_gb < 1:
            color_print("{red}Error: provider_space must be >= 1 GB{endc}")
            return

        try:
            storage_path = self.app.db.ton_storage.storage_path
            disk = get_disk_space(storage_path, unit=ByteUnit.GB, ndigits=2)
            currently_allocated = self.get_total_space_gb()
        except (RuntimeError, OSError, AttributeError) as exc:
            color_print(f"{{red}}Error:{{endc}} cannot determine disk state: {exc}")
            return

        max_allowable = min(disk.total, disk.free + currently_allocated)
        if requested_gb > max_allowable:
            color_print(
                f"{{red}}Error: requested {requested_gb} GB exceeds "
                f"available {max_allowable:.2f} GB "
                f"(disk total {disk.total}, free {disk.free}){{endc}}"
            )
            return

        def mutate(cfg: Dict) -> None:
            cfg.Storages[0].SpaceToProvideMegabytes = requested_gb * 1024

        try:
            self._apply_provider_config(mutate)
        except Exception as exc:
            color_print(f"{{red}}set_provider_space failed:{{endc}} {exc}")
            return

        color_print(f"set_provider_space = {requested_gb} GB {{green}}OK{{endc}}")

    def _cmd_set_max_bag_size(self, args: list[str]) -> None:
        try:
            gb = int(args[0])
        except (IndexError, ValueError):
            color_print("{red}Usage:{endc} set_max_bag_size <gigabytes>")
            return
        if not MAX_BAG_SIZE_GB_MIN <= gb <= MAX_BAG_SIZE_GB_MAX:
            color_print(
                f"{{red}}Error: max_bag_size must be between "
                f"{MAX_BAG_SIZE_GB_MIN} and {MAX_BAG_SIZE_GB_MAX} GB{{endc}}"
            )
            return

        def mutate(cfg: Dict) -> None:
            cfg.MaxBagSizeBytes = gb * 1024**3

        try:
            self._apply_provider_config(mutate)
        except Exception as exc:
            color_print(f"{{red}}set_max_bag_size failed:{{endc}} {exc}")
            return

        color_print(f"set_max_bag_size = {gb} GB {{green}}OK{{endc}}")

    def _print_module_name(self) -> None:
        module_name = bcolors.yellow_text(self.name)
        text = self.app.translate("module_name").format(module_name)
        print(text)

    def _print_provider_pubkey(self) -> None:
        try:
            pubkey = self.get_provider_pubkey()
            pubkey_text = bcolors.yellow_text(pubkey)
        except (RuntimeError, AttributeError, TypeError):
            pubkey_text = bcolors.red_text("n/a")
        print(self.app.translate("provider_pubkey").format(pubkey_text))

    @async_to_sync
    async def _print_provider_wallet(self) -> None:
        try:
            async with self.ton_client:
                wallet = await self._get_refreshed_wallet()
            addr_text = bcolors.yellow_text(wallet.address.to_str(is_bounceable=False))
            balance_text = bcolors.green_text(to_amount(wallet.balance, precision=4))
        except Exception as exc:
            self.app.add_log(f"{self.name}: wallet fetch failed: {exc}", DEBUG)
            addr_text = bcolors.red_text("n/a")
            balance_text = bcolors.red_text("n/a")
        print(self.app.translate("provider_wallet").format(addr_text))
        print(self.app.translate("provider_balance").format(balance_text))

    def _print_storage_cost(self) -> None:
        try:
            cost = self._get_storage_cost()
            cost_text = bcolors.yellow_text(cost)
        except (RuntimeError, AttributeError, TypeError):
            cost_text = bcolors.red_text("n/a")
        print(self.app.translate("storage_cost").format(cost_text))

    def _print_profit(self) -> None:
        try:
            real_profit, max_profit = self._get_profit()
            real_text = bcolors.green_text(real_profit)
            max_text = bcolors.yellow_text(max_profit)
        except (RuntimeError, AttributeError, TypeError):
            real_text = bcolors.red_text("n/a")
            max_text = bcolors.red_text("n/a")
        print(self.app.translate("provider_profit").format(real_text, max_text))

    def _print_provider_space(self) -> None:
        try:
            used_gb = self.registry.get_by_class(TonStorageModule).get_used_space_gb()
            total_gb = self.get_total_space_gb()
            used_text = bcolors.green_text(used_gb)
            total_text = bcolors.yellow_text(total_gb)
        except (RuntimeError, AttributeError, TypeError, KeyError):
            used_text = bcolors.red_text("n/a")
            total_text = bcolors.red_text("n/a")
        print(self.app.translate("provider_space").format(used_text, total_text))

    def _print_max_bag_size(self) -> None:
        try:
            gb_text = bcolors.yellow_text(self.get_max_bag_size_gb())
        except (RuntimeError, AttributeError, TypeError, ValueError):
            gb_text = bcolors.red_text("n/a")
        print(self.app.translate("max_bag_size").format(gb_text))

    def _print_port_status(self) -> None:
        try:
            provider_config = self._read_provider_config()
            _, port_str = provider_config.ListenAddr.split(":")
        except (RuntimeError, AttributeError, ValueError):
            port_str = "?"
        port_color = bcolors.yellow_text(f"{port_str} udp")
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

    def _get_storage_cost(self) -> float:
        """Reverse ``MinRatePerMBDay`` into the user-facing ``200GB/month`` price."""
        provider_config = self._read_provider_config()
        rate_per_mb_day = float(provider_config.MinRatePerMBDay)
        return round(rate_per_mb_day * STORAGE_COST_REFERENCE_GB * 1024 * 30, 2)

    def _get_profit(self) -> tuple[float, float]:
        """Return ``(real_profit, max_profit)`` per month in TON."""
        provider_config = self._read_provider_config()
        ton_storage = self.registry.get_by_class(TonStorageModule)
        used_mb = ton_storage.get_used_space_gb() * 1024
        total_mb = self.get_total_space_gb() * 1024
        rate_per_mb_day = float(provider_config.MinRatePerMBDay)
        real = round(used_mb * rate_per_mb_day * 30, 2)
        maximum = round(total_mb * rate_per_mb_day * 30, 2)
        return real, maximum

    def get_total_space_gb(self) -> float:
        """Return ``SpaceToProvideMegabytes`` converted to GB."""
        provider_config = self._read_provider_config()
        megabytes = int(provider_config.Storages[0].SpaceToProvideMegabytes)
        return round(megabytes / 1024, 2)

    def get_max_bag_size_bytes(self) -> int:
        """Return raw ``MaxBagSizeBytes`` from provider config."""
        return int(self._read_provider_config().MaxBagSizeBytes)

    def get_max_bag_size_gb(self) -> float:
        """Return ``MaxBagSizeBytes`` converted to GB (for display)."""
        return round(self.get_max_bag_size_bytes() / 1024**3, 2)

    @staticmethod
    def _calculate_space_to_provide_megabytes(gigabytes: int) -> int:
        return int(gigabytes) * 1024

    @staticmethod
    def _calculate_max_span(storage_cost: float) -> int:
        """Derive ``MaxSpan`` (seconds) so each proof costs at least ``MIN_PROOF_COST_TON``."""
        rate_per_mb_sec = float(storage_cost) / STORAGE_COST_REFERENCE_GB / 1024 / 30 / 24 / 3600
        max_span = int(MIN_PROOF_COST_TON / (rate_per_mb_sec * MIN_BAG_SIZE_BYTES))
        if max_span < MIN_MAX_SPAN_SEC:
            return MIN_MAX_SPAN_SEC
        return min(max_span, MAX_SPAN_HARD_LIMIT)

    @staticmethod
    def _calculate_min_rate_per_mb_day(storage_cost: float) -> str:
        """Derive ``MinRatePerMBDay`` as a formatted decimal string."""
        rate = float(storage_cost) / STORAGE_COST_REFERENCE_GB / 1024 / 30
        return f"{rate:.9f}"

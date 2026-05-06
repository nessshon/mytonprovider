import asyncio
import time
from typing import Any, ClassVar, Final, cast

from mypycli import Commandable, Startable, Statusable
from mypycli.console.ansi import colorize_text, colorize_threshold
from mypycli.types import BoxStyle, Color, ColorText, Command
from ton_core import (
    Address,
    AddressError,
    DNSCategory,
    DNSRecordWallet,
    NetworkGlobalID,
    PrivateKey,
    mnemonic_to_private_key,
    normalize_hash,
    to_amount,
    to_nano,
)
from tonutils.clients import LiteBalancer
from tonutils.contracts import WalletV3R2
from tonutils.types import (
    RetryPolicy,
    RetryRule,
)

from mytonprovider import constants
from mytonprovider.locales import _
from mytonprovider.modules.ton_storage_provider import TonStorageProviderModule
from mytonprovider.utils import create_status_header


class TonWalletModule(
    Startable,
    Statusable,
    Commandable,
):
    mandatory: ClassVar[bool] = True
    name: ClassVar[str] = "ton-wallet"
    label: ClassVar[str] = "TON Wallet"

    TX_WAIT_TIMEOUT_SEC: Final[int] = 15

    _ton_client: LiteBalancer | None = None

    async def get_wallet(self) -> WalletV3R2:
        if self._ton_client is None:
            raise RuntimeError("ton client is not initialized")
        provider_config = self._provider.get_provider_config()
        wallet = WalletV3R2.from_private_key(self._ton_client, provider_config.provider_private_key)
        await wallet.refresh()
        return wallet

    async def send_and_wait(
        self,
        destination: Address,
        amount_nano: int,
        body: str | None = None,
    ) -> str:
        if self._ton_client is None:
            raise RuntimeError("ton client is not initialized")
        wallet = await self.get_wallet()
        end_lt = wallet.last_transaction_lt or 0
        msg = await wallet.transfer(destination=destination, amount=amount_nano, body=body)
        target = msg.normalized_hash
        deadline = time.monotonic() + self.TX_WAIT_TIMEOUT_SEC
        while time.monotonic() < deadline:
            txs = await self._ton_client.get_transactions(wallet.address, to_lt=end_lt)
            for tx in txs:
                if tx.in_msg is not None and normalize_hash(tx.in_msg) == target:
                    return msg.normalized_hash
                for out_msg in tx.out_msgs:
                    if normalize_hash(out_msg) == target:
                        return msg.normalized_hash
            await asyncio.sleep(1)
        raise TimeoutError(f"message {msg.normalized_hash} not found within {self.TX_WAIT_TIMEOUT_SEC}s")

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "register",
                self._cmd_register,
                _("modules.ton_wallet.cmd.register"),
                "[--force]",
            ),
            Command(
                "wallet",
                description=_("modules.ton_wallet.cmd.group"),
                children=[
                    Command(
                        "export",
                        self._cmd_export,
                        _("modules.ton_wallet.cmd.export"),
                    ),
                    Command(
                        "import",
                        self._cmd_import,
                        _("modules.ton_wallet.cmd.import"),
                    ),
                    Command(
                        "transfer",
                        self._cmd_transfer,
                        _("modules.ton_wallet.cmd.transfer"),
                        "<address|domain> <amount> [comment]",
                    ),
                ],
            ),
        ]

    def on_start(self) -> None:
        self.run_async(self._init_ton_client())

    def on_stop(self) -> None:
        self.run_async(self._close_ton_client())

    def show_status(self) -> None:
        wallet: WalletV3R2 | None
        try:
            wallet = self.run_async(self.get_wallet())
        except Exception as exc:
            self.logger.debug(f"status: wallet fetch failed: {exc}")
            wallet = None

        self.app.console.print_panel(
            [
                self._status_address(wallet),
                self._status_balance(wallet),
            ],
            header=create_status_header(self.label, WalletV3R2.VERSION.value.removeprefix("wallet_")),
            footer=self._status_footer(wallet),
            min_width=constants.STATUS_PANEL_WIDTH,
        )

    def _cmd_import(self, app: Any, _args: list[str]) -> None:
        # Read the secret via getpass so it never enters the readline buffer
        # and is not persisted to the console history file.
        raw = app.console.secret(_("modules.ton_wallet.msg.import_prompt")).strip()
        if not raw:
            return
        words = raw.split()
        try:
            if len(words) > 1:
                WalletV3R2.validate_mnemonic(words)
            private_key = PrivateKey(words[0] if len(words) == 1 else mnemonic_to_private_key(words)[1])
        except Exception as exc:
            app.console.print(_("modules.ton_wallet.msg.bad_key", error=exc), Color.RED)
            return

        self._provider.apply_config(lambda cfg: setattr(cfg, "provider_key", private_key.keypair.as_b64))
        self.app.db.modules.ton_wallet.registered = False

        if self._ton_client is None:
            app.console.print(_("modules.ton_wallet.msg.imported", address="—"), Color.GREEN)
            return
        wallet = WalletV3R2.from_private_key(self._ton_client, private_key)
        address = wallet.address.to_str(is_bounceable=False)
        app.console.print(_("modules.ton_wallet.msg.imported", address=address), Color.GREEN)

    def _cmd_export(self, app: Any, _args: list[str]) -> None:
        try:
            wallet = self.run_async(self.get_wallet())
        except Exception as exc:
            self.logger.warning(f"wallet export failed: {exc}")
            app.console.print(str(exc), Color.RED)
            return

        private_key = self._provider.get_provider_config().provider_private_key
        address = wallet.address.to_str(is_bounceable=False)

        def t(key: str) -> ColorText:
            return ColorText(_(f"modules.ton_wallet.info.{key}"), color=Color.CYAN)

        rows: list[list[str | ColorText]] = [
            [t("metric"), t("value")],
            [t("address"), address],
            [t("private_b64"), private_key.as_b64],
            [t("private_hex"), private_key.as_hex],
        ]
        app.console.print_table(rows, style=BoxStyle.SHARP)

    def _cmd_transfer(self, app: Any, args: list[str]) -> None:
        if len(args) < 2:
            app.console.print(
                f"{_('common.usage_prefix')} wallet transfer <address|domain> <amount> [comment]", Color.YELLOW
            )
            return

        try:
            destination = self.run_async(self._resolve_address(args[0]))
        except Exception as exc:
            app.console.print(_("modules.ton_wallet.msg.bad_address", error=exc), Color.RED)
            return

        try:
            amount_nano = to_nano(args[1])
        except Exception as exc:
            app.console.print(_("modules.ton_wallet.msg.bad_amount", error=exc), Color.RED)
            return

        body: str | None = " ".join(args[2:]) if len(args) > 2 else None
        amount_ton = float(to_amount(amount_nano, precision=4))
        addr_str = destination.to_str(is_bounceable=False)

        try:
            wallet = self.run_async(self.get_wallet())
        except Exception as exc:
            self.logger.warning(f"wallet transfer: wallet fetch failed: {exc}")
            app.console.print(str(exc), Color.RED)
            return

        needed_nano = amount_nano + to_nano(constants.WALLET_GAS_RESERVE)
        if wallet.balance < needed_nano:
            balance_ton = float(to_amount(wallet.balance, precision=4))
            shortage_ton = float(to_amount(needed_nano - wallet.balance, precision=4))
            app.console.print(
                _("modules.ton_wallet.msg.low_balance", balance=balance_ton, shortage=shortage_ton),
                Color.RED,
            )
            return

        remaining_nano = wallet.balance - amount_nano
        if remaining_nano < to_nano(constants.WALLET_MIN_BALANCE):
            remaining_ton = float(to_amount(remaining_nano, precision=4))
            app.console.print(
                _(
                    "modules.ton_wallet.msg.balance_warning",
                    remaining=remaining_ton,
                    recommended=constants.WALLET_MIN_BALANCE,
                ),
                Color.YELLOW,
            )

        if not app.console.confirm(
            _("modules.ton_wallet.msg.transfer_prompt", amount=amount_ton, address=addr_str), default=False
        ):
            app.console.print(_("modules.ton_wallet.msg.cancelled"), Color.YELLOW)
            return

        try:
            msg_hash = self.run_async(self.send_and_wait(destination, amount_nano, body))
        except Exception as exc:
            self.logger.warning(f"wallet transfer failed: {exc}")
            app.console.print(str(exc), Color.RED)
            return

        app.console.print(_("modules.ton_wallet.msg.transferred", hash=msg_hash), Color.GREEN)

    def _cmd_register(self, app: Any, args: list[str]) -> None:
        force = "--force" in args
        if self.app.db.modules.ton_wallet.registered and not force:
            app.console.print(_("modules.ton_wallet.register.already"), Color.GREEN)
            return

        try:
            wallet = self.run_async(self.get_wallet())
        except Exception as exc:
            self.logger.warning(f"wallet register: wallet fetch failed: {exc}")
            app.console.print(str(exc), Color.RED)
            return

        required_nano = to_nano(constants.REGISTRATION_MIN_BALANCE)
        if wallet.balance < required_nano:
            balance_ton = float(to_amount(wallet.balance, precision=4))
            shortage_ton = float(to_amount(required_nano - wallet.balance, precision=4))
            app.console.print(
                _("modules.ton_wallet.msg.low_balance", balance=balance_ton, shortage=shortage_ton),
                Color.RED,
            )
            return

        provider_pubkey = self._provider.get_provider_config().provider_pubkey
        body = f"{constants.REGISTRATION_COMMENT_PREFIX}{provider_pubkey.lower()}"
        try:
            msg_hash = self.run_async(
                self.send_and_wait(
                    Address(constants.REGISTRATION_ADDRESS),
                    to_nano(constants.REGISTRATION_AMOUNT),
                    body,
                )
            )
        except Exception as exc:
            self.logger.warning(f"wallet register failed: {exc}")
            app.console.print(str(exc), Color.RED)
            return

        self.app.db.modules.ton_wallet.registered = True
        app.console.print(_("modules.ton_wallet.register.success", hash=msg_hash), Color.GREEN)

    @staticmethod
    def _status_address(wallet: WalletV3R2 | None) -> tuple[str, str]:
        label = _("modules.ton_wallet.status.address")
        if wallet is None:
            return label, colorize_text(_("common.status.collecting"), Color.GRAY)
        return label, colorize_text(wallet.address.to_str(is_bounceable=False), Color.CYAN)

    @staticmethod
    def _status_balance(wallet: WalletV3R2 | None) -> tuple[str, str]:
        label = _("modules.ton_wallet.status.balance")
        if wallet is None:
            return label, colorize_text(_("common.status.collecting"), Color.GRAY)
        balance_ton = float(to_amount(wallet.balance, precision=4))
        return label, colorize_threshold(
            balance_ton if balance_ton > 0 else 0,
            constants.REGISTRATION_MIN_BALANCE,
            logic="more",
            ending=" TON",
            precision=4,
        )

    @staticmethod
    def _status_footer(wallet: WalletV3R2 | None) -> str:
        if wallet is None:
            return colorize_text(_("common.status.collecting"), Color.GRAY)
        state_colors: dict[str, Color] = {
            "active": Color.GREEN,
            "uninit": Color.YELLOW,
            "frozen": Color.BLUE,
            "nonexist": Color.GRAY,
        }
        state_icons: dict[str, str] = {
            "active": "✓",
            "uninit": "⚠",
            "frozen": "✕",
            "nonexist": "✕",
        }
        key = wallet.state.value
        if key not in state_colors:
            key = "nonexist"
        text = _(f"modules.ton_wallet.state.{key}")
        return colorize_text(f"{state_icons[key]} {text}", state_colors[key])

    @property
    def _provider(self) -> TonStorageProviderModule:
        provider = cast(TonStorageProviderModule, self.app.modules.get("ton-storage-provider"))
        if provider is None:
            raise RuntimeError("ton-storage-provider module is not available")
        return provider

    async def _resolve_address(self, raw: str) -> Address:
        if self._ton_client is None:
            raise RuntimeError("ton client is not initialized")
        try:
            return Address(raw)
        except AddressError:
            pass
        record = await self._ton_client.dnsresolve(raw, DNSCategory.WALLET)
        if not isinstance(record, DNSRecordWallet) or record.value is None:
            raise ValueError(f"DNS resolve failed: {raw}")
        return cast(Address, record.value)

    async def _init_ton_client(self) -> None:
        cfg = self.app.db.settings.lite_balancer
        self._ton_client = LiteBalancer.from_config(
            network=NetworkGlobalID.MAINNET,
            config=cfg.config,
            rps_limit=cfg.rps_limit,
            rps_per_client=True,
            connect_timeout=cfg.connect_timeout,
            client_connect_timeout=cfg.client_connect_timeout,
            request_timeout=cfg.request_timeout,
            client_request_timeout=cfg.client_request_timeout,
            retry_policy=RetryPolicy(
                rules=(
                    # rate limit
                    RetryRule(codes=frozenset({228, 5556}), max_retries=cfg.retry_rule_rate_limit),
                    # cannot load block
                    RetryRule(codes=frozenset({651}), max_retries=cfg.retry_rule_cannot_load_block),
                    # backend node timeout
                    RetryRule(codes=frozenset({502}), max_retries=cfg.retry_rule_backend_timeout),
                ),
                total_timeout=cfg.retry_total_timeout,
            ),
        )
        await self._ton_client.connect()

    async def _close_ton_client(self) -> None:
        if self._ton_client is not None:
            await self._ton_client.close()
            self._ton_client = None

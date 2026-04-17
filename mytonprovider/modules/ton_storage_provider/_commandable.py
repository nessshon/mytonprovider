from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mypycli import Commandable
from mypycli.types import BoxStyle, Color, ColorText, Command
from ton_core import Address, ContractState, DNSCategory, PrivateKey, to_amount, to_nano

from mytonprovider import constants
from mytonprovider.utils import (
    calculate_max_span,
    calculate_min_rate_per_mb_day,
    calculate_space_to_provide_megabytes,
    read_config,
    write_config,
)

from .config import ProviderConfig
from .wallet import Wallet

if TYPE_CHECKING:
    from mypycli import Application
    from tonutils.clients import LiteBalancer


class CommandableMixin(Commandable):
    __abstract__ = True

    ton_client: LiteBalancer

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "register",
                self._cmd_register,
                "Register provider",
            ),
            Command(
                "provider",
                description="Provider config",
                children=[
                    Command(
                        "set-storage-price",
                        self._cmd_set_storage_price,
                        "Set price per 200GB per month",
                        usage="<ton>",
                    ),
                    Command(
                        "set-provided-space",
                        self._cmd_set_provided_space,
                        "Set provided space",
                        usage="<gb>",
                    ),
                    Command(
                        "set-max-bag-size",
                        self._cmd_set_max_bag_size,
                        "Set max bag size",
                        usage="<gb>",
                    ),
                ],
            ),
            Command(
                "wallet",
                description="Wallet operations",
                children=[
                    Command("export", self._cmd_export, "Show wallet info with keys"),
                    Command(
                        "import",
                        self._cmd_import,
                        "Import wallet and show info",
                        usage="<key | word1 word2 ...>",
                    ),
                    Command(
                        "transfer",
                        self._cmd_transfer,
                        "Transfer TON to address or domain",
                        usage="<address|domain> <ton> [comment]",
                    ),
                ],
            ),
        ]

    def _cmd_register(self, app: Application[Any], _args: list[str]) -> None:
        if not app.console.confirm(
            f"Register provider? This will send {constants.REGISTRATION_AMOUNT} TON.",
            default=False,
        ):
            app.console.print("Cancelled.", color=Color.YELLOW)
            return
        self.run_async(self._register_async())

    def _cmd_import(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: wallet import <key | mnemonic words>", color=Color.RED)
            return
        self.run_async(self._import_async(args))

    def _cmd_export(self, _app: Application[Any], _args: list[str]) -> None:
        self.run_async(self._export_async())

    def _cmd_transfer(self, app: Application[Any], args: list[str]) -> None:
        if len(args) < 2:
            app.console.print("Usage: wallet transfer <address|domain> <ton> [comment]", color=Color.RED)
            return
        try:
            amount_ton = float(args[1])
        except ValueError:
            app.console.print(f"Invalid amount: {args[1]}", color=Color.RED)
            return
        try:
            address = self.run_async(self._resolve_address(args[0]))
        except Exception as exc:
            app.console.print(f"Invalid address: {exc}", color=Color.RED)
            return
        comment = " ".join(args[2:]) or None
        comment_suffix = f" with comment {comment!r}" if comment else ""
        if not app.console.confirm(
            f"Transfer {amount_ton} TON to {address.to_str(is_bounceable=False)}{comment_suffix}?",
            default=False,
        ):
            app.console.print("Cancelled.", color=Color.YELLOW)
            return
        self.run_async(self._transfer_async(address, amount_ton, comment))

    def _cmd_set_storage_price(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: provider set-storage-price <ton>", color=Color.RED)
            return
        try:
            price = int(args[0])
        except ValueError:
            app.console.print(f"Invalid price: {args[0]}", color=Color.RED)
            return
        self._mutate_config(
            app,
            lambda cfg: _apply_storage_price(cfg, price),
            success=f"Storage price set to {price} TON / 200GB / month.",
        )

    def _cmd_set_provided_space(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: provider set-provided-space <gb>", color=Color.RED)
            return
        try:
            gb = int(args[0])
        except ValueError:
            app.console.print(f"Invalid space: {args[0]}", color=Color.RED)
            return
        self._mutate_config(
            app,
            lambda cfg: _apply_provided_space(cfg, gb),
            success=f"Provided space set to {gb} GB.",
        )

    def _cmd_set_max_bag_size(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: provider set-max-bag-size <gb>", color=Color.RED)
            return
        try:
            gb = int(args[0])
        except ValueError:
            app.console.print(f"Invalid size: {args[0]}", color=Color.RED)
            return
        self._mutate_config(
            app,
            lambda cfg: cfg.__setattr__("max_bag_size_bytes", gb * 1024**3),
            success=f"Max bag size set to {gb} GB.",
        )

    def _mutate_config(
        self,
        app: Application[Any],
        mutate: Any,
        *,
        success: str,
    ) -> None:
        try:
            cfg = read_config(self.db.config_path, ProviderConfig)
            mutate(cfg)
            write_config(self.db.config_path, cfg)
        except Exception as exc:
            app.console.print(f"Failed to update config: {exc}", color=Color.RED)
            return
        app.console.print(success, color=Color.GREEN)
        app.console.print(
            "Restart ton-storage-provider to apply: sudo systemctl restart ton-storage-provider",
            color=Color.YELLOW,
        )

    async def _register_async(self) -> None:
        if self.db.is_already_registered:
            self.app.console.print("Provider is already registered.", color=Color.YELLOW)
            return
        config = read_config(self.db.config_path, ProviderConfig)
        wallet = await Wallet.from_private_key(self.ton_client, config.provider_key)
        if wallet.balance < to_nano(constants.REGISTRATION_MIN_BALANCE):
            self.app.console.print(
                f"Low balance: {to_amount(wallet.balance, precision=4)} TON "
                f"(required >= {constants.REGISTRATION_MIN_BALANCE} TON)",
                color=Color.RED,
            )
            return
        body = f"{constants.REGISTRATION_COMMENT_PREFIX}{config.provider_key.public_key.as_hex.lower()}"
        try:
            tx_hash = await wallet.send(
                Address(constants.REGISTRATION_ADDRESS),
                to_nano(constants.REGISTRATION_AMOUNT),
                body,
            )
        except TimeoutError as exc:
            self.app.console.print(f"Register failed: {exc}", color=Color.RED)
            return
        self.db.is_already_registered = True
        self.app.console.print(f"Registered: {tx_hash}", color=Color.GREEN)

    async def _import_async(self, args: list[str]) -> None:
        if len(args) == 1:
            try:
                private_key = PrivateKey(args[0])
            except Exception as exc:
                self.app.console.print(f"Invalid private key: {exc}", color=Color.RED)
                return
            wallet = await Wallet.from_private_key(self.ton_client, private_key)
        else:
            try:
                wallet, private_key = await Wallet.from_mnemonic(self.ton_client, args)
            except Exception as exc:
                self.app.console.print(f"Invalid mnemonic: {exc}", color=Color.RED)
                return
        config = read_config(self.db.config_path, ProviderConfig)
        config.provider_key = private_key
        write_config(self.db.config_path, config)
        self._show_wallet_panel(wallet, private_key, show_keys=False)

    async def _export_async(self) -> None:
        config = read_config(self.db.config_path, ProviderConfig)
        wallet = await Wallet.from_private_key(self.ton_client, config.provider_key)
        self._show_wallet_panel(wallet, config.provider_key, show_keys=True)

    def _show_wallet_panel(
        self,
        wallet: Wallet,
        private_key: PrivateKey,
        *,
        show_keys: bool,
    ) -> None:
        color = _STATE_COLORS.get(wallet.state, Color.MAGENTA)
        items: list[tuple[str | ColorText, str | ColorText] | tuple[()]] = [
            (ColorText("Address", Color.CYAN), wallet.address.to_str(is_bounceable=False)),
            (ColorText("Balance", Color.CYAN), f"{to_amount(wallet.balance, precision=4)} TON"),
        ]
        if show_keys:
            seed = PrivateKey(private_key.as_bytes)
            items.extend(
                [
                    (),
                    (ColorText("Private Key (b64)", Color.CYAN), seed.as_b64),
                    (ColorText("Private Key (hex)", Color.CYAN), seed.as_hex),
                ]
            )
        self.app.console.print_panel(
            items=items,
            header="Wallet v3r2",
            footer=ColorText(f"● {wallet.state.value}", color),
            style=BoxStyle.SHARP,
        )

    async def _resolve_address(self, target: str) -> Address:
        try:
            return Address(target)
        except Exception:
            pass
        if target.lower().endswith((".ton", ".t.me")):
            record = await self.ton_client.dnsresolve(target, DNSCategory.WALLET)
            resolved = getattr(record, "value", None)
            if not isinstance(resolved, Address):
                raise ValueError(f"no wallet DNS record for {target}")
            return resolved
        raise ValueError(f"expected TON address (EQ..., UQ...) or DNS domain (*.ton, *.t.me); got {target!r}")

    async def _transfer_async(
        self,
        destination: Address,
        amount_ton: float,
        comment: str | None,
    ) -> None:
        config = read_config(self.db.config_path, ProviderConfig)
        wallet = await Wallet.from_private_key(self.ton_client, config.provider_key)
        try:
            tx_hash = await wallet.send(destination, to_nano(amount_ton), comment)
        except TimeoutError as exc:
            self.app.console.print(f"Transfer failed: {exc}", color=Color.RED)
            return
        self.app.console.print(f"Transferred {amount_ton} TON: {tx_hash}", color=Color.GREEN)


def _apply_storage_price(cfg: ProviderConfig, price: int) -> None:
    cfg.min_rate_per_mb_day = calculate_min_rate_per_mb_day(price)
    cfg.max_span = calculate_max_span(price)


def _apply_provided_space(cfg: ProviderConfig, gb: int) -> None:
    if not cfg.storages:
        raise ValueError("no storage backends configured")
    cfg.storages[0].space_to_provide_megabytes = calculate_space_to_provide_megabytes(gb)


_STATE_COLORS: dict[ContractState, Color] = {
    ContractState.ACTIVE: Color.GREEN,
    ContractState.FROZEN: Color.BLUE,
    ContractState.UNINIT: Color.YELLOW,
    ContractState.NONEXIST: Color.RED,
}

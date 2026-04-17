from __future__ import annotations

from typing import TYPE_CHECKING

from mypycli import Statusable
from mypycli.types import BoxStyle, Color, ColorText
from mypycli.utils.convert import format_duration
from mypycli.utils.service import SystemdService
from ton_core import to_amount

from mytonprovider.modules.ton_storage.api.client import StorageApi
from mytonprovider.utils import read_config, version_rows

from ._installable import SERVICE_NAME
from ._updatable import SRC_PATH
from .config import ProviderConfig
from .wallet import Wallet

if TYPE_CHECKING:
    from tonutils.clients import LiteBalancer


class StatusableMixin(Statusable):
    __abstract__ = True

    ton_client: LiteBalancer

    def show_status(self) -> None:
        svc = SystemdService(SERVICE_NAME)
        active = svc.is_active

        cfg: ProviderConfig | None
        try:
            cfg = read_config(self.db.config_path, ProviderConfig)
        except (FileNotFoundError, ValueError):
            cfg = None

        port_num = cfg.listen_addr.rsplit(":", 1)[-1] if cfg else "?"
        port_state: str | ColorText = (
            ColorText(f"{port_num} open", Color.GREEN)
            if self.db.port_reachable
            else ColorText(f"{port_num} closed", Color.RED)
        )

        pubkey = cfg.provider_key.public_key.as_hex.upper() if cfg else "—"
        wallet_addr, balance = self._wallet_info(cfg)
        used_mb, total_mb = self._space(cfg)
        rate = float(cfg.min_rate_per_mb_day) if cfg else 0.0
        price = rate * 200 * 1024 * 30

        def cyan(t: str) -> ColorText:
            return ColorText(t, Color.CYAN)

        items: list[tuple[str | ColorText, str | ColorText] | tuple[()]] = list(version_rows(self.name, SRC_PATH))
        items.extend(
            [
                (),
                (cyan("UDP port"), port_state),
                (),
                (cyan("Public key"), pubkey),
                (cyan("Wallet address"), wallet_addr),
                (),
                (cyan("Wallet balance"), balance),
                (cyan("Profit per month (real / max)"), f"{used_mb * rate * 30:.2f} / {total_mb * rate * 30:.2f} TON"),
                (cyan("Provided space (used / total)"), f"{used_mb / 1024:.2f} / {total_mb / 1024:.2f} GB"),
                (),
                (cyan("Storage price per month (200GB)"), f"{price:.2f} TON"),
                (cyan("Max bag size"), _format_bag_size(cfg)),
            ]
        )
        self.app.console.print_panel(
            items=items,
            header=self.display_name,
            footer=_service_footer(active, svc.uptime),
            style=BoxStyle.ROUNDED,
        )

    def _wallet_info(self, cfg: ProviderConfig | None) -> tuple[str, str]:
        if cfg is None:
            return "—", "—"
        try:
            wallet = self.run_async(Wallet.from_private_key(self.ton_client, cfg.provider_key))
        except Exception:
            self.logger.debug("status: wallet query failed", exc_info=True)
            return "—", "—"
        return (
            wallet.address.to_str(is_bounceable=False),
            f"{to_amount(wallet.balance, precision=4)} TON",
        )

    def _space(self, cfg: ProviderConfig | None) -> tuple[float, float]:
        total = float(cfg.storages[0].space_to_provide_megabytes) if cfg and cfg.storages else 0.0
        ts = self.app.modules.get("ton-storage")
        try:
            bags = StorageApi(ts.db.api_host, ts.db.api_port).list_bags().bags
        except Exception:
            self.logger.debug("status: bag list unavailable", exc_info=True)
            return 0.0, total
        return sum(b.size for b in bags) / 1024**2, total


def _format_bag_size(cfg: ProviderConfig | None) -> str:
    if cfg is None:
        return "—"
    return f"{cfg.max_bag_size_bytes / 1024**3:.2f} GB"


def _service_footer(active: bool, uptime: int | None) -> ColorText:
    if active:
        return ColorText(f"\u25cf running \u00b7 {format_duration(uptime or 0)}", Color.GREEN)
    return ColorText("\u25cb stopped", Color.YELLOW)

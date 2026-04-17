from __future__ import annotations

from mypycli import Statusable
from mypycli.types import BoxStyle, Color, ColorText
from mypycli.utils.convert import format_bytes, format_duration
from mypycli.utils.service import SystemdService
from mypycli.utils.sysinfo import sysinfo

from mytonprovider.utils import read_config, version_rows

from ._installable import SERVICE_NAME
from ._updatable import SRC_PATH
from .api.client import StorageApi
from .config import StorageConfig


class StatusableMixin(Statusable):
    __abstract__ = True

    def show_status(self) -> None:
        svc = SystemdService(SERVICE_NAME)
        active = svc.is_active

        cfg: StorageConfig | None
        try:
            cfg = read_config(self.db.config_path, StorageConfig)
        except (FileNotFoundError, ValueError):
            cfg = None

        port_num = cfg.listen_addr.rsplit(":", 1)[-1] if cfg else "?"
        if self.db.port_reachable:
            port_state: str | ColorText = ColorText(f"{port_num} open", Color.GREEN)
        else:
            port_state = ColorText(f"{port_num} closed", Color.RED)

        pubkey = cfg.pubkey_hex if cfg else "—"
        bags_line = self._bags_line()
        disk_line = self._disk_line()

        def cyan(t: str) -> ColorText:
            return ColorText(t, Color.CYAN)

        items: list[tuple[str | ColorText, str | ColorText] | tuple[()]] = list(version_rows(self.name, SRC_PATH))
        items.extend(
            [
                (),
                (cyan("UDP port"), port_state),
                (),
                (cyan("Storage path"), self.db.storage_path or "—"),
                (cyan("Public key"), pubkey),
                (cyan("API endpoint"), f"{self.db.api_host}:{self.db.api_port}"),
                (),
                (cyan("Bags count (total size)"), bags_line),
                (cyan("Disk usage (used / total)"), disk_line),
            ]
        )
        self.app.console.print_panel(
            items=items,
            header=self.display_name,
            footer=_service_footer(active, svc.uptime),
            style=BoxStyle.ROUNDED,
        )

    def _bags_line(self) -> str:
        try:
            bags = StorageApi(self.db.api_host, self.db.api_port).list_bags().bags
        except Exception:
            self.logger.debug("status: bag list unavailable", exc_info=True)
            return "—"
        return f"{len(bags)} ({format_bytes(sum(b.size for b in bags))})"

    def _disk_line(self) -> str:
        if not self.db.storage_path:
            return "—"
        try:
            disk = sysinfo.get_disk_usage(self.db.storage_path)
        except OSError:
            return "—"
        return f"{format_bytes(disk.used)} / {format_bytes(disk.total)}"


def _service_footer(active: bool, uptime: int | None) -> ColorText:
    if active:
        return ColorText(f"\u25cf running \u00b7 {format_duration(uptime or 0)}", Color.GREEN)
    return ColorText("\u25cb stopped", Color.YELLOW)

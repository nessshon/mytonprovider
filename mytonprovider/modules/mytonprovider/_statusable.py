from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

from mypycli import Statusable
from mypycli.console.ansi import colorize_text
from mypycli.types import BoxStyle, Color, ColorText, MemoryInfo
from mypycli.utils.convert import format_bytes, format_duration
from mypycli.utils.daemon import is_alive, read_pid
from mypycli.utils.sysinfo import sysinfo

from mytonprovider.modules.benchmark.schemas import BenchmarkResult
from mytonprovider.modules.statistics.schemas import DiskAverages, StatsSnapshot
from mytonprovider.utils import version_rows

from ._updatable import SRC_PATH

if TYPE_CHECKING:
    from pathlib import Path


_PanelItem = tuple[str | ColorText, str | ColorText] | tuple[()]


def _cyan(t: str) -> ColorText:
    return ColorText(t, Color.CYAN)


class StatusableMixin(Statusable):
    __abstract__ = True

    def show_status(self) -> None:
        pid_path = self.app.pid_path

        items: list[_PanelItem] = list(version_rows(self.name, SRC_PATH))
        items.append(())
        items.extend(
            [
                (_cyan("Debug"), ColorText("on", Color.GREEN) if self.app.db.debug else ColorText("off", Color.YELLOW)),
                (_cyan("Registered"), _registered_cell(self.app)),
                (),
                (_cyan("Python"), sys.executable),
                (_cyan("DB file"), _file_summary(self.app.db.path)),
                (_cyan("Log file"), _log_summary(self.app.log_path)),
            ]
        )

        load = self._load_section()
        if load:
            items.append(())
            items.extend(load)
        bench = self._bench_section()
        if bench:
            items.append(())
            items.extend(bench)

        self.app.console.print_panel(
            items=items,
            header=self.display_name,
            footer=_daemon_footer(pid_path),
            style=BoxStyle.ROUNDED,
        )

    def _load_section(self) -> list[_PanelItem]:
        cpu = sysinfo.cpu
        rows: list[_PanelItem] = [
            (_cyan(f"CPU [{cpu.count_logical}]"), f"{cpu.load_1m:.2f}, {cpu.load_5m:.2f}, {cpu.load_15m:.2f}"),
            (_cyan("RAM"), _memory_line(sysinfo.ram)),
        ]
        if sysinfo.swap.total > 0:
            rows.append((_cyan("Swap"), _memory_line(sysinfo.swap)))
        snap = self._snapshot()
        if snap is not None and snap.net is not None:
            rows.append((_cyan("Network avg"), _avg_line(snap.net.load, "Mbit/s")))
        if snap is not None and snap.disks:
            disks_line = _disks_line(snap.disks)
            if disks_line:
                rows.append((_cyan("Disks load"), disks_line))
        return rows

    def _bench_section(self) -> list[_PanelItem]:
        last = self._last_bench()
        if last is None:
            return []
        return [
            (_cyan("Disk read"), f"QD1 {last.disk.qd1.read}, QD64 {last.disk.qd64.read}"),
            (_cyan("Disk write"), f"QD1 {last.disk.qd1.write}, QD64 {last.disk.qd64.write}"),
            (_cyan("Network"), _bench_net_line(last.network)),
        ]

    def _snapshot(self) -> StatsSnapshot | None:
        try:
            mod = self.app.modules.get("statistics")
        except KeyError:
            return None
        value = getattr(mod.db, "snapshot", None)
        return value if isinstance(value, StatsSnapshot) else None

    def _last_bench(self) -> BenchmarkResult | None:
        try:
            mod = self.app.modules.get("benchmark")
        except KeyError:
            return None
        value = getattr(mod.db, "last", None)
        return value if isinstance(value, BenchmarkResult) else None


def _daemon_footer(pid_path: Path) -> ColorText:
    if not pid_path.exists():
        return ColorText("\u25cb stopped", Color.YELLOW)
    pid = read_pid(pid_path)
    if pid is None:
        return ColorText("\u2716 pid file unreadable", Color.RED)
    alive = is_alive(pid)
    if alive is False:
        return ColorText("\u2716 process dead", Color.RED)
    try:
        uptime = format_duration(time.time() - pid_path.stat().st_mtime)
    except OSError:
        uptime = "unknown"
    if alive is None:
        return ColorText(f"\u25cf running (other user) \u00b7 {uptime}", Color.YELLOW)
    return ColorText(f"\u25cf running \u00b7 {uptime}", Color.GREEN)


def _file_summary(path: Path) -> str:
    if not path.exists():
        return f"{path} ({colorize_text('not created', Color.YELLOW)})"
    try:
        size = path.stat().st_size
    except OSError:
        return f"{path} (?)"
    return f"{path} ({format_bytes(size)})"


def _log_summary(path: Path) -> str:
    if not path.exists():
        return f"{path} ({colorize_text('not created', Color.YELLOW)})"
    try:
        size = path.stat().st_size
    except OSError:
        return f"{path} (?)"
    rotated: list[str] = []
    for i in range(1, 10):
        backup = path.parent / f"{path.name}.{i}"
        if not backup.exists():
            break
        rotated.append(f".{i}")
    rot_info = f", rotated: {' '.join(rotated)}" if rotated else ""
    return f"{path} ({format_bytes(size)}{rot_info})"


def _registered_cell(app: object) -> ColorText:
    try:
        tsp = app.modules.get("ton-storage-provider")  # type: ignore[attr-defined]
    except KeyError:
        return ColorText("—", Color.YELLOW)
    return (
        ColorText("yes", Color.GREEN)
        if getattr(tsp.db, "is_already_registered", False)
        else ColorText("no", Color.RED)
    )


def _memory_line(mem: MemoryInfo) -> str:
    return f"{mem.used / 10**9:.2f} / {mem.total / 10**9:.2f} GB ({mem.percent:.0f}%)"


def _avg_line(values: tuple[float, float, float], unit: str) -> str:
    return f"{values[0]:.2f} / {values[1]:.2f} / {values[2]:.2f} {unit}"


def _disks_line(disks: dict[str, DiskAverages]) -> str:
    parts: list[str] = []
    for name, d in disks.items():
        if d.load[2] == 0 and d.load_percent[2] == 0:
            continue
        parts.append(f"{name} {d.load[2]:.2f} MB/s ({d.load_percent[2]:.0f}%)")
    return ", ".join(parts)


def _bench_net_line(net: object) -> str:
    download = getattr(net, "download", 0.0) / 10**6
    upload = getattr(net, "upload", 0.0) / 10**6
    ping = getattr(net, "ping", 0.0)
    return f"\u2193{download:.0f} \u2191{upload:.0f} Mbps, {ping:.0f}ms ping"

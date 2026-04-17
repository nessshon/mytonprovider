from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mypycli import Commandable
from mypycli.types import BoxStyle, Color, ColorText, Command
from mypycli.utils.convert import format_time_ago

from .runner import run_benchmark

if TYPE_CHECKING:
    from mypycli import Application

    from .schemas import BenchmarkResult


class CommandableMixin(Commandable):
    __abstract__ = True

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "benchmark",
                description="Benchmark operations",
                children=[
                    Command("show", self._cmd_show, "Show benchmark"),
                    Command("run", self._cmd_run, "Run benchmark"),
                ],
            ),
        ]

    def _cmd_show(self, app: Application[Any], _args: list[str]) -> None:
        last = self.db.last
        if last is None:
            app.console.print("No cached benchmark; run `benchmark run` to generate one.", color=Color.YELLOW)
            return
        _render_benchmark(app, last)

    def _cmd_run(self, app: Application[Any], _args: list[str]) -> None:
        ts = self.app.modules.get("ton-storage")
        storage_path = ts.db.storage_path
        if not storage_path:
            app.console.print("ton-storage is not installed; cannot run benchmark.", color=Color.RED)
            return
        app.console.print("Running benchmark; this takes ~2 minutes...", color=Color.YELLOW)
        try:
            result = run_benchmark(storage_path)
        except Exception as exc:
            app.console.print(f"Benchmark failed: {exc}", color=Color.RED)
            return
        self.db.last = result
        _render_benchmark(app, result)


def _render_benchmark(app: Application[Any], result: BenchmarkResult) -> None:
    disk_rows: list[list[ColorText | str]] = [
        [
            ColorText("Test", Color.CYAN),
            ColorText("Read", Color.CYAN),
            ColorText("Write", Color.CYAN),
            ColorText("Read IOPS", Color.CYAN),
            ColorText("Write IOPS", Color.CYAN),
        ],
        [
            result.disk.qd64.name,
            result.disk.qd64.read,
            result.disk.qd64.write,
            result.disk.qd64.read_iops,
            result.disk.qd64.write_iops,
        ],
        [
            result.disk.qd1.name,
            result.disk.qd1.read,
            result.disk.qd1.write,
            result.disk.qd1.read_iops,
            result.disk.qd1.write_iops,
        ],
    ]
    app.console.print_table(rows=disk_rows, header="Disk", style=BoxStyle.ROUNDED)

    net = result.network
    net_rows: list[list[ColorText | str]] = [
        [
            ColorText("Metric", Color.CYAN),
            ColorText("Value", Color.CYAN),
        ],
        ["Download", f"{net.download / 1024**2:.2f} Mbit/s"],
        ["Upload", f"{net.upload / 1024**2:.2f} Mbit/s"],
        ["Ping", f"{net.ping:.2f} ms"],
    ]
    app.console.print_table(rows=net_rows, header="Network", style=BoxStyle.ROUNDED)

    app.console.print(f"Benchmarked {format_time_ago(result.timestamp)}.", color=Color.BLUE)

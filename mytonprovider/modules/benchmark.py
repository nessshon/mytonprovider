import fcntl
import re
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, ClassVar, Final, Literal, cast

from mypycli import Commandable, Daemonic, utils
from mypycli.console.progress import ProgressLine
from mypycli.types import BoxStyle, Color, ColorText, Command
from speedtest import Speedtest

from mytonprovider.database import BenchmarkDisk, BenchmarkNetwork, BenchmarkSnapshot, FioResult
from mytonprovider.locales import _, lang
from mytonprovider.modules.ton_storage import TonStorageModule


class BenchmarkModule(Commandable, Daemonic):
    mandatory: ClassVar[bool] = True
    name: ClassVar[str] = "benchmark"
    label: ClassVar[str] = "Benchmark"

    REFRESH_SNAPSHOT_INTERVAL_SEC: Final[int] = 3600
    SNAPSHOT_TTL_SEC: Final[int] = 7 * 24 * 3600
    LOCK_FILENAME: ClassVar[str] = ".benchmark.lock"
    FIO_TEST_FILENAME: ClassVar[str] = "test.img"
    FIO_RUNTIME_SEC: ClassVar[int] = 15
    FIO_TIMEOUT_SEC: ClassVar[int] = 30
    FIO_BLOCKSIZE: ClassVar[str] = "4k"
    FIO_SIZE: ClassVar[str] = "4G"

    @property
    def snapshot(self) -> BenchmarkSnapshot | None:
        snap = self.app.db.modules.benchmark.snapshot
        if snap is None or (int(time.time()) - snap.timestamp) > self.SNAPSHOT_TTL_SEC:
            return None
        return cast(BenchmarkSnapshot, snap)

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "benchmark",
                description=_("modules.benchmark.cmd.group"),
                children=[
                    Command("run", self._cmd_run, _("modules.benchmark.cmd.run")),
                    Command("show", self._cmd_show, _("modules.benchmark.cmd.show")),
                ],
            ),
        ]

    def on_daemon(self) -> None:
        if self._get_ton_storage_path() is None:
            self.logger.warning("ton-storage path unavailable; skipping benchmark scheduling")
            return
        self.run_cycle(self.cycle_refresh_snapshot, seconds=self.REFRESH_SNAPSHOT_INTERVAL_SEC)

    def cycle_refresh_snapshot(self) -> None:
        if self.snapshot is not None:
            return
        path = self._get_ton_storage_path()
        if path is None:
            return
        with try_lock_file(self.app.work_dir / self.LOCK_FILENAME) as acquired:
            if not acquired:
                return
            with suppress(Exception):
                self.app.db.modules.benchmark.snapshot = self._run_benchmark(path)

    def _cmd_run(self, app: Any, _args: list[str]) -> None:
        storage_path = self._get_ton_storage_path()
        if storage_path is None:
            app.console.print(_("modules.benchmark.no_storage"), Color.RED)
            return
        with try_lock_file(app.work_dir / self.LOCK_FILENAME) as acquired:
            if not acquired:
                app.console.print(_("modules.benchmark.already_running"), Color.YELLOW)
                return
            result = self._run_benchmark(storage_path)
            self.app.db.modules.benchmark.snapshot = result
            app.console.print()
            self._print_result(result)

    def _cmd_show(self, app: Any, _args: list[str]) -> None:
        if self.app.db.modules.benchmark.snapshot is None:
            app.console.print(_("modules.benchmark.no_result"), Color.YELLOW)
            return
        when = utils.format_time_ago(self.app.db.modules.benchmark.snapshot.timestamp, lang=lang())
        app.console.print()
        self._print_result(self.app.db.modules.benchmark.snapshot)
        app.console.print()
        app.console.print(_("modules.benchmark.last_run", when=when), color=Color.CYAN)

    def _run_benchmark(self, storage_path: str | Path) -> BenchmarkSnapshot:
        total_steps = 7  # 3 speedtest stages + 2 QDs x (read + write)
        self.logger.info("Benchmark started")
        self.app.console.print(_("modules.benchmark.progress.start"), color=Color.CYAN)
        self.app.console.print()
        with self.app.console.print_progress(total=total_steps) as line:
            try:
                network = self._benchmark_network(line)
                disk = self._benchmark_disk(Path(storage_path), line)
            except Exception:
                self.logger.exception("Benchmark failed")
                line.fail(_("modules.benchmark.progress.failed"), color=Color.RED)
                raise
            line.finish(_("modules.benchmark.progress.done"), color=Color.GREEN)
        self.logger.info("Benchmark finished")
        return BenchmarkSnapshot(timestamp=int(time.time()), disk=disk, network=network)

    def _benchmark_disk(self, storage_path: Path, line: ProgressLine) -> BenchmarkDisk:
        test_file = storage_path / self.FIO_TEST_FILENAME
        test_file.unlink(missing_ok=True)
        try:
            return BenchmarkDisk(
                qd64=self._benchmark_qd(test_file, "RND-4K-QD64", qd=64, line=line),
                qd1=self._benchmark_qd(test_file, "RND-4K-QD1", qd=1, line=line),
            )
        finally:
            test_file.unlink(missing_ok=True)

    def _benchmark_qd(
        self,
        test_file: Path,
        name: str,
        *,
        qd: int,
        line: ProgressLine,
    ) -> FioResult:
        self.logger.debug("fio %s read starting", name)
        line.update(_("modules.benchmark.progress.fio_read", name=name))
        read_bw, read_iops = self._run_fio(test_file, rw="randread", qd=qd)

        self.logger.debug("fio %s write starting", name)
        line.update(_("modules.benchmark.progress.fio_write", name=name))
        write_bw, write_iops = self._run_fio(test_file, rw="randwrite", qd=qd)

        return FioResult(
            name=name,
            read=read_bw,
            read_iops=read_iops,
            write=write_bw,
            write_iops=write_iops,
        )

    def _run_fio(
        self,
        test_file: Path,
        *,
        rw: Literal["randread", "randwrite"],
        qd: int,
    ) -> tuple[str, str]:
        # libaio on Linux (native kernel AIO), posixaio elsewhere (POSIX portable).
        ioengine = "libaio" if sys.platform.startswith("linux") else "posixaio"
        result = utils.run(
            [
                "fio",
                "--name=test",
                f"--filename={test_file}",
                f"--runtime={self.FIO_RUNTIME_SEC}",
                f"--blocksize={self.FIO_BLOCKSIZE}",
                f"--size={self.FIO_SIZE}",
                f"--ioengine={ioengine}",
                "--direct=1",
                "--randrepeat=1",
                "--gtod_reduce=1",
                f"--readwrite={rw}",
                f"--iodepth={qd}",
            ],
            timeout=self.FIO_TIMEOUT_SEC,
            check=True,
        )
        mode: Literal["read", "write"] = "read" if rw == "randread" else "write"
        return self._parse_fio_summary(result.stdout, mode=mode)

    @staticmethod
    def _parse_fio_summary(output: str, *, mode: Literal["read", "write"]) -> tuple[str, str]:
        # Extract bw/iops from fio's "<mode>: IOPS=..., BW=..." summary line, as fio formats them.
        pattern = re.compile(rf"^\s*{mode}:\s+IOPS=(?P<iops>\S+?),\s+BW=(?P<bw>\S+?)\s", re.MULTILINE)
        match = pattern.search(output)
        if match is None:
            raise ValueError(f"fio summary line for mode={mode!r} not found in output")
        return match["bw"], match["iops"]

    def _benchmark_network(self, line: ProgressLine) -> BenchmarkNetwork:
        speedtest = Speedtest()

        self.logger.debug("speedtest ping starting")
        line.update(_("modules.benchmark.progress.speedtest_ping"))
        speedtest.get_best_server()

        self.logger.debug("speedtest download starting")
        line.update(_("modules.benchmark.progress.speedtest_download"))
        speedtest.download()

        self.logger.debug("speedtest upload starting")
        line.update(_("modules.benchmark.progress.speedtest_upload"))
        speedtest.upload()

        return BenchmarkNetwork.model_validate(speedtest.results.dict())

    def _print_result(self, r: BenchmarkSnapshot) -> None:
        def t(key: str, color: Color = Color.CYAN) -> ColorText:
            return ColorText(_(f"modules.benchmark.table.{key}"), color=color)

        def ping_color(ms: float) -> Color:
            if ms < 50:
                return Color.GREEN
            if ms < 150:
                return Color.YELLOW
            return Color.RED

        disk_rows: list[list[str | ColorText]] = [
            [t("test"), t("read"), t("write"), t("read_iops"), t("write_iops")],
            [r.disk.qd64.name, r.disk.qd64.read, r.disk.qd64.write, r.disk.qd64.read_iops, r.disk.qd64.write_iops],
            [r.disk.qd1.name, r.disk.qd1.read, r.disk.qd1.write, r.disk.qd1.read_iops, r.disk.qd1.write_iops],
        ]
        network_rows: list[list[str | ColorText]] = [
            [t("metric"), t("value")],
            [t("download", color=Color.WHITE), utils.format_bitrate(r.network.download, precision=0)],
            [t("upload", color=Color.WHITE), utils.format_bitrate(r.network.upload, precision=0)],
            [t("ping", color=Color.WHITE), ColorText(f"{r.network.ping:.1f} ms", ping_color(r.network.ping))],
        ]
        self.app.console.print_table(disk_rows, style=BoxStyle.SHARP)
        self.app.console.print()
        self.app.console.print_table(network_rows, style=BoxStyle.SHARP)

    def _get_ton_storage_path(self) -> Path | None:
        module = cast("TonStorageModule | None", self.app.modules.get("ton-storage"))
        if module is None or not self.app.db.modules.ton_storage.storage_path:
            return None
        return module.storage_path


@contextmanager
def try_lock_file(path: Path) -> Iterator[bool]:
    with path.open("a") as fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True

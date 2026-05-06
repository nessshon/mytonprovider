import fcntl
import io
import json
import platform
import re
import shutil
import sys
import tarfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, ClassVar, Literal

import requests
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

    REFRESH_SNAPSHOT_INTERVAL_SEC: ClassVar[int] = 3600
    SNAPSHOT_TTL_SEC: ClassVar[int] = 7 * 24 * 3600

    FIO_RUNTIME_SEC: ClassVar[int] = 15
    FIO_TIMEOUT_SEC: ClassVar[int] = 30
    SPEEDTEST_TIMEOUT_SEC: ClassVar[int] = 30
    LIBRESPEED_TIMEOUT_SEC: ClassVar[int] = 120
    LIBRESPEED_FETCH_TIMEOUT_SEC: ClassVar[int] = 30
    LIBRESPEED_SERVERS: ClassVar[tuple[int, ...]] = (
        102,  # Volzhsky, Russia (PowerNet)        — RU/CIS
        50,  # Frankfurt, Germany (Clouvider)      — Europe
        52,  # New York, USA (Clouvider)           — North America
        68,  # Singapore                           — South East Asia
        82,  # Tokyo, Japan (A573)                 — East Asia
    )

    LOCK_FILENAME: ClassVar[str] = ".benchmark.lock"
    FIO_TEST_FILENAME: ClassVar[str] = "test.img"

    @property
    def snapshot(self) -> BenchmarkSnapshot | None:
        snap: BenchmarkSnapshot | None = self.app.db.modules.benchmark.snapshot
        if snap is None or (int(time.time()) - snap.timestamp) > self.SNAPSHOT_TTL_SEC:
            return None
        return snap

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
        path = self._get_ton_storage_path()
        if path is None:
            self.logger.warning("ton-storage path unavailable; skipping benchmark scheduling")
            return
        (path / self.FIO_TEST_FILENAME).unlink(missing_ok=True)
        self.run_cycle(self.cycle_refresh_snapshot, seconds=self.REFRESH_SNAPSHOT_INTERVAL_SEC)

    def cycle_refresh_snapshot(self) -> None:
        if self.snapshot is not None:
            return
        path = self._get_ton_storage_path()
        if path is None:
            return
        with _try_lock(self.app.work_dir / self.LOCK_FILENAME) as acquired:
            if not acquired:
                return
            with suppress(Exception):
                self.app.db.modules.benchmark.snapshot = self._run_benchmark(path)

    def _cmd_run(self, app: Any, _args: list[str]) -> None:
        storage_path = self._get_ton_storage_path()
        if storage_path is None:
            app.console.print(_("modules.benchmark.no_storage"), Color.RED)
            return
        with _try_lock(self.app.work_dir / self.LOCK_FILENAME) as acquired:
            if not acquired:
                app.console.print(_("modules.benchmark.already_running"), Color.YELLOW)
                return
            result = self._run_benchmark(storage_path)
            app.db.modules.benchmark.snapshot = result
            app.console.print()
            self._print_result(result)

    def _cmd_show(self, app: Any, _args: list[str]) -> None:
        snapshot = app.db.modules.benchmark.snapshot
        if snapshot is None:
            app.console.print(_("modules.benchmark.no_result"), Color.YELLOW)
            return
        when = utils.format_time_ago(snapshot.timestamp, lang=lang())
        app.console.print()
        self._print_result(snapshot)
        app.console.print()
        app.console.print(_("modules.benchmark.last_run", when=when), color=Color.CYAN)

    def _run_benchmark(self, storage_path: str | Path) -> BenchmarkSnapshot:
        self.logger.info("Benchmark started")
        self.app.console.print(_("modules.benchmark.progress.start"), color=Color.CYAN)
        self.app.console.print()
        with self.app.console.print_progress(total=3) as line:
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
        line.update(_("modules.benchmark.progress.disk", name=name))
        read_bw, read_iops = self._run_fio(test_file, rw="randread", qd=qd)
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
        ioengine = "libaio" if sys.platform.startswith("linux") else "posixaio"
        result = utils.run(
            [
                "fio",
                "--name=test",
                f"--filename={test_file}",
                f"--runtime={self.FIO_RUNTIME_SEC}",
                "--blocksize=4k",
                "--size=4G",
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
        bw, iops = self._parse_fio_summary(result.stdout, mode=mode)
        self.logger.debug(f"fio {mode} qd{qd}: bw={bw}, iops={iops}")
        return bw, iops

    @staticmethod
    def _parse_fio_summary(output: str, *, mode: Literal["read", "write"]) -> tuple[str, str]:
        # Extract bw/iops from fio's "<mode>: IOPS=..., BW=..." summary line, as fio formats them.
        pattern = re.compile(rf"^\s*{mode}:\s+IOPS=(?P<iops>\S+?),\s+BW=(?P<bw>\S+?)\s", re.MULTILINE)
        match = pattern.search(output)
        if match is None:
            raise ValueError(f"fio summary line for mode={mode!r} not found in output")
        return match["bw"], match["iops"]

    def _benchmark_network(self, line: ProgressLine) -> BenchmarkNetwork:
        line.update(_("modules.benchmark.progress.speedtest"))

        for attempt in (1, 2, 3):
            try:
                result = self._benchmark_network_speedtest()
                self.logger.info(
                    f"speedtest via speedtest-cli succeeded (attempt {attempt}); "
                    f"down={result.download / 1_000_000:.1f} Mbit/s, "
                    f"up={result.upload / 1_000_000:.1f} Mbit/s, "
                    f"ping={result.ping:.1f}ms"
                )
                return result
            except Exception as exc:
                self.logger.warning(f"speedtest via speedtest-cli attempt {attempt} failed: {exc}")
                if attempt < 3:
                    time.sleep(5 * attempt)

        result = self._benchmark_network_librespeed()
        self.logger.info(
            f"speedtest via librespeed succeeded; "
            f"down={result.download / 1_000_000:.1f} Mbit/s, "
            f"up={result.upload / 1_000_000:.1f} Mbit/s, "
            f"ping={result.ping:.1f}ms"
        )
        return result

    def _benchmark_network_speedtest(self) -> BenchmarkNetwork:
        speedtest = Speedtest(timeout=self.SPEEDTEST_TIMEOUT_SEC)
        speedtest.download()
        speedtest.upload()
        return BenchmarkNetwork.model_validate(speedtest.results.dict())

    def _benchmark_network_librespeed(self) -> BenchmarkNetwork:
        binary = self._librespeed_binary()
        cmd_args = [str(binary), "--json"]
        for sid in self.LIBRESPEED_SERVERS:
            cmd_args.extend(["--server", str(sid)])
        result = utils.run(cmd_args, timeout=self.LIBRESPEED_TIMEOUT_SEC, check=True)
        results = json.loads(result.stdout)
        if not results:
            raise ValueError("librespeed-cli returned empty result")
        raw = results[0]
        return BenchmarkNetwork.model_validate(
            {
                "download": float(raw["download"]) * 1_000_000.0,
                "upload": float(raw["upload"]) * 1_000_000.0,
                "ping": float(raw["ping"]),
                "server": raw.get("server", {}),
                "isp": raw.get("client", {}).get("isp", ""),
            }
        )

    def _librespeed_binary(self) -> Path:
        system_bin = shutil.which("librespeed-cli")
        if system_bin:
            return Path(system_bin)
        cached = Path(sys.executable).parent / "librespeed-cli"
        if not cached.exists():
            self._fetch_librespeed_binary(cached)
        return cached

    def _fetch_librespeed_binary(self, target: Path) -> None:
        version = "1.0.13"
        arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
        if arch is None:
            raise RuntimeError(f"unsupported architecture for librespeed-cli: {platform.machine()}")
        url = (
            f"https://github.com/librespeed/speedtest-cli/releases/download/"
            f"v{version}/librespeed-cli_{version}_linux_{arch}.tar.gz"
        )
        self.logger.info(f"downloading librespeed-cli from {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, timeout=self.LIBRESPEED_FETCH_TIMEOUT_SEC)
        response.raise_for_status()
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
            # filter= added in 3.12 (backported to 3.10.12 / 3.11.4); guard older patch levels.
            if hasattr(tarfile, "data_filter"):
                tar.extract("librespeed-cli", path=target.parent, filter="data")
            else:
                tar.extract("librespeed-cli", path=target.parent)
        target.chmod(0o755)

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
        if not self.app.db.modules.ton_storage.storage_path:
            return None
        return self.app.modules.get_by_class(TonStorageModule).storage_path


@contextmanager
def _try_lock(path: Path) -> Iterator[bool]:
    with path.open("a") as fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True

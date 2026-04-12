from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Final, Literal, cast

from mypylib import (
    DEBUG,
    Dict,
    get_timestamp,
    print_table,
    run_subprocess,
    timeago,
)
from speedtest import Speedtest

from mytonprovider.modules.core import Commandable, Daemonic
from mytonprovider.types import Command

# Daemon timing
DAEMON_INTERVAL_SEC: Final[int] = 60

# Benchmark cache freshness (results older than this trigger a new run)
BENCHMARK_LIFETIME_SEC: Final[int] = 7 * 24 * 3600  # 1 week

# Delay before each benchmark run: lets boot-time CPU/IO noise settle so the
# measured values are not skewed by startup activity.
BENCHMARK_STARTUP_DELAY_SEC: Final[int] = 60

# fio test parameters
FIO_RUNTIME_SEC: Final[int] = 15
FIO_BLOCK_SIZE: Final[str] = "4k"
FIO_TEST_SIZE: Final[str] = "4G"
FIO_IODEPTH_QD64: Final[int] = 64
FIO_IODEPTH_QD1: Final[int] = 1
FIO_SUBPROCESS_TIMEOUT_SEC: Final[int] = 30

# Name of the temporary file created in `storage_path` for fio tests
TEST_FILE_NAME: Final[str] = "test.img"


class BenchmarkModule(Daemonic, Commandable):
    """Run disk (``fio``) and network (``speedtest``) benchmarks once a week."""

    name = "benchmark"
    mandatory = True
    daemon_interval = DAEMON_INTERVAL_SEC

    def daemon(self) -> None:
        """Check cache freshness; if stale, wait for noise to settle and run."""
        if self._is_benchmark_done():
            return
        time.sleep(BENCHMARK_STARTUP_DELAY_SEC)
        self._do_benchmark()

    def get_commands(self) -> list[Command]:
        return [
            Command(
                name="benchmark",
                func=self._run_benchmark,
                description=self.app.translate("benchmark_cmd"),
            ),
        ]

    def get_benchmark_data(self) -> Dict | None:
        """Return the cached benchmark payload, or ``None`` if it was never run."""
        return cast("Dict | None", self.app.db.benchmark)

    def _is_benchmark_done(self) -> bool:
        bench = self.app.db.benchmark
        if bench is None:
            return False
        return bool(bench.timestamp + BENCHMARK_LIFETIME_SEC >= get_timestamp())

    def _do_benchmark(self) -> tuple[Dict, Dict]:
        self.app.add_log("Running benchmark, this may take about two minutes")
        disk = self._disk_benchmark()
        network = self._network_benchmark()
        self._save_benchmark(disk, network)
        return disk, network

    def _save_benchmark(self, disk: Dict, network: Dict) -> None:
        self.app.add_log("Saving benchmark results", DEBUG)
        bench = Dict()
        bench.disk = disk
        bench.network = network
        bench.timestamp = get_timestamp()
        self.app.db.benchmark = bench

    def _network_benchmark(self) -> Dict:
        speedtest = Speedtest()
        self.app.add_log("Running Speedtest download", DEBUG)
        speedtest.download()
        self.app.add_log("Running Speedtest upload", DEBUG)
        speedtest.upload()
        return Dict(speedtest.results.dict())

    def _disk_benchmark(self) -> Dict:
        self.app.add_log("Running disk benchmark", DEBUG)

        if self.app.db.ton_storage is None:
            raise RuntimeError(f"{self.name}: ton_storage module is not configured")
        storage_path = self.app.db.ton_storage.storage_path
        if not storage_path:
            raise RuntimeError(f"{self.name}: ton_storage.storage_path is not set")

        test_file = Path(storage_path) / TEST_FILE_NAME
        try:
            fio_base = (
                f"fio --name=test --filename={test_file}"
                f" --runtime={FIO_RUNTIME_SEC} --blocksize={FIO_BLOCK_SIZE}"
                f" --ioengine=libaio --direct=1 --size={FIO_TEST_SIZE}"
                f" --randrepeat=1 --gtod_reduce=1"
            )
            read_args = f"{fio_base} --readwrite=randread"
            write_args = f"{fio_base} --readwrite=randwrite"

            result = Dict()
            result.qd64 = Dict()
            result.qd64.name = "RND-4K-QD64"
            result.qd1 = Dict()
            result.qd1.name = "RND-4K-QD1"

            self.app.add_log("Running RND-4K-QD64 read test", DEBUG)
            qd64_read_output = run_subprocess(
                f"{read_args} --iodepth={FIO_IODEPTH_QD64}",
                timeout=FIO_SUBPROCESS_TIMEOUT_SEC,
            )
            self.app.add_log("Running RND-4K-QD64 write test", DEBUG)
            qd64_write_output = run_subprocess(
                f"{write_args} --iodepth={FIO_IODEPTH_QD64}",
                timeout=FIO_SUBPROCESS_TIMEOUT_SEC,
            )
            self.app.add_log("Running RND-4K-QD1 read test", DEBUG)
            qd1_read_output = run_subprocess(
                f"{read_args} --iodepth={FIO_IODEPTH_QD1}",
                timeout=FIO_SUBPROCESS_TIMEOUT_SEC,
            )
            self.app.add_log("Running RND-4K-QD1 write test", DEBUG)
            qd1_write_output = run_subprocess(
                f"{write_args} --iodepth={FIO_IODEPTH_QD1}",
                timeout=FIO_SUBPROCESS_TIMEOUT_SEC,
            )

            result.qd64.read, result.qd64.read_iops = self._parse_fio_result(qd64_read_output, "read")
            result.qd64.write, result.qd64.write_iops = self._parse_fio_result(qd64_write_output, "write")
            result.qd1.read, result.qd1.read_iops = self._parse_fio_result(qd1_read_output, "read")
            result.qd1.write, result.qd1.write_iops = self._parse_fio_result(qd1_write_output, "write")
            return result
        finally:
            if test_file.exists():
                test_file.unlink()

    def _parse_fio_result(
        self,
        output: str,
        mode: Literal["read", "write"],
    ) -> tuple[str, str]:
        """Extract ``(bandwidth, iops)`` from an fio result block."""
        idx = output.find(f"{mode}:")
        if idx < 0:
            raise RuntimeError(f"{self.name}: fio output missing '{mode}:' line")
        # Expected fio line shape: "read: IOPS=1234, BW=12.3MiB/s ..."
        parts = output[idx:].split(" ")
        iops = parts[1].split("=")[1].replace(",", "")
        bw = parts[2].split("=")[1]
        return bw, iops

    def _run_benchmark(self, args: list[str]) -> None:
        """Console command: show cached benchmark or re-run if ``--force``."""
        if self._is_benchmark_done() and "--force" not in args:
            bench = self.app.db.benchmark
            print(f"last benchmark time: {timeago(bench.timestamp)}")
            print()
            disk = bench.disk
            network = bench.network
        else:
            disk, network = self._do_benchmark()

        disk_table: list[list[Any]] = [
            ["Test type", "Read speed", "Write speed", "Read iops", "Write iops"],
            [
                "RND-4K-QD64",
                disk.qd64.read,
                disk.qd64.write,
                disk.qd64.read_iops,
                disk.qd64.write_iops,
            ],
            [
                "RND-4K-QD1",
                disk.qd1.read,
                disk.qd1.write,
                disk.qd1.read_iops,
                disk.qd1.write_iops,
            ],
        ]
        print_table(disk_table)
        print()

        net_table: list[list[Any]] = [
            ["Test type", "Download (Mbit/s)", "Upload (Mbit/s)"],
            ["Speedtest", network.download // 1024**2, network.upload // 1024**2],
        ]
        print_table(net_table)

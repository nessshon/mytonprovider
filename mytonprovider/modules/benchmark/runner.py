from __future__ import annotations

import time
from pathlib import Path

from speedtest import Speedtest

from mytonprovider.utils import run_fio

from .schemas import BenchmarkDisk, BenchmarkNetwork, BenchmarkResult, FioResult

_TEST_FILENAME = "test.img"


def run_benchmark(storage_path: str | Path) -> BenchmarkResult:
    """Execute the full disk + network benchmark and return a typed result.

    Disk: four sequential fio passes (QD64 read/write, QD1 read/write) against
    ``<storage_path>/test.img`` which is deleted afterwards. Network: speedtest-cli
    download + upload tests.

    :raises RuntimeError: When any fio pass fails or the speedtest library errors out.
    """
    test_file = Path(storage_path) / _TEST_FILENAME
    # Clean up any orphan from a previous crashed run before fio expands to 4G again.
    test_file.unlink(missing_ok=True)
    try:
        qd64_read_bw, qd64_read_iops = run_fio(test_file, rw="randread", qd=64)
        qd64_write_bw, qd64_write_iops = run_fio(test_file, rw="randwrite", qd=64)
        qd1_read_bw, qd1_read_iops = run_fio(test_file, rw="randread", qd=1)
        qd1_write_bw, qd1_write_iops = run_fio(test_file, rw="randwrite", qd=1)
    finally:
        test_file.unlink(missing_ok=True)

    st = Speedtest()
    st.download()
    st.upload()
    network = BenchmarkNetwork.model_validate(st.results.dict())

    disk = BenchmarkDisk(
        qd64=FioResult(
            name="RND-4K-QD64",
            read=qd64_read_bw,
            read_iops=qd64_read_iops,
            write=qd64_write_bw,
            write_iops=qd64_write_iops,
        ),
        qd1=FioResult(
            name="RND-4K-QD1",
            read=qd1_read_bw,
            read_iops=qd1_read_iops,
            write=qd1_write_bw,
            write_iops=qd1_write_iops,
        ),
    )
    return BenchmarkResult(timestamp=int(time.time()), disk=disk, network=network)

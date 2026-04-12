"""Tests for BenchmarkModule fio output parsing."""
from __future__ import annotations

import pytest

from mytonprovider.modules.benchmark import BenchmarkModule


def _make_benchmark() -> BenchmarkModule:
    mod = object.__new__(BenchmarkModule)
    mod.name = "benchmark"
    return mod


class TestParseFioResult:
    FIO_OUTPUT = (
        "fio-test: (groupid=0, jobs=1): err= 0: pid=12345\n"
        "  read: IOPS=1234, BW=12.3MiB/s (12897792B/s)(100MiB/8127msec)\n"
        "  write: IOPS=567, BW=5.67MiB/s (5947392B/s)(100MiB/17637msec)\n"
    )

    def test_parse_read(self):
        mod = _make_benchmark()
        bw, iops = mod._parse_fio_result(self.FIO_OUTPUT, "read")
        assert iops == "1234"
        assert bw == "12.3MiB/s"

    def test_parse_write(self):
        mod = _make_benchmark()
        bw, iops = mod._parse_fio_result(self.FIO_OUTPUT, "write")
        assert iops == "567"
        assert bw == "5.67MiB/s"

    def test_missing_mode_raises(self):
        mod = _make_benchmark()
        with pytest.raises(RuntimeError, match="missing 'read:'"):
            mod._parse_fio_result("no matching output here", "read")

    def test_extra_whitespace_between_fields(self):
        """fio output may use variable spacing — split() handles this."""
        output = "  read:  IOPS=999,  BW=3.14MiB/s  (rest)\n"
        mod = _make_benchmark()
        bw, iops = mod._parse_fio_result(output, "read")
        assert iops == "999"
        assert bw == "3.14MiB/s"

    def test_fio_v3_k_suffix_iops(self):
        """fio v3 reports IOPS with k/M suffix (e.g. IOPS=12.3k)."""
        output = "  read: IOPS=12.3k, BW=48.1MiB/s (50.4MB/s)\n"
        mod = _make_benchmark()
        bw, iops = mod._parse_fio_result(output, "read")
        assert iops == "12.3k"
        assert bw == "48.1MiB/s"

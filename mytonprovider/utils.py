from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
from typing import Literal, TypeVar

import requests
from mypycli.console.ansi import colorize_text
from mypycli.types import Color, ColorText
from mypycli.utils.github import GitError, LocalGitRepo
from mypycli.utils.system import run_as_root
from pydantic import BaseModel

from mytonprovider import constants

T = TypeVar("T", bound=BaseModel)


def run_root_script(args: list[str | Path]) -> None:
    """Run a shell helper as root and raise when it exits non-zero.

    Wraps ``mypycli.utils.system.run_as_root`` (which never checks returncode)
    so a failed build or pip install aborts ``on_install``/``on_update`` cleanly
    instead of cascading into downstream misleading errors.
    """
    result = run_as_root(args)
    if result.returncode != 0:
        script = Path(str(args[0])).name
        raise RuntimeError(f"{script} failed with exit code {result.returncode}")


def read_config(path: str | Path, model: type[T]) -> T:
    data = json.loads(Path(path).read_text())
    return model.model_validate(data)


def write_config(path: str | Path, config: BaseModel) -> None:
    # Atomic write: serialize to a sibling .tmp, preserve existing file mode
    # (wallet keys require 0600) AND ownership (install wizard runs as root but
    # the daemon reads the file as the install user). Then rename into place.
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(config.model_dump_json(by_alias=True, indent=2) + "\n")
    if target.exists():
        st = target.stat()
        os.chmod(tmp, st.st_mode)
        # Running as a regular user: the file is already owned by us.
        with contextlib.suppress(PermissionError):
            os.chown(tmp, st.st_uid, st.st_gid)
    tmp.replace(target)


def hash_telemetry_password(password: str) -> str:
    digest = hashlib.sha256(f"{constants.TELEMETRY_URL}{password}".encode()).digest()
    return base64.b64encode(digest).decode("utf-8")


def calculate_min_rate_per_mb_day(storage_cost: int) -> str:
    # 200 GB (in MB) / month → per-MB-per-day rate.
    rate = storage_cost / 200 / 1024 / 30
    return f"{rate:.9f}"


def calculate_max_span(storage_cost: int) -> int:
    # 0.05 TON minimum proof reward, 400 MB minimum bag size for span sizing.
    # Result clamped to [30 days, uint32 max — Go storage-provider constraint].
    rate_per_mb_sec = storage_cost / 200 / 1024 / 30 / 24 / 3600
    max_span = int(0.05 / (rate_per_mb_sec * 400))
    return max(30 * 24 * 3600, min(max_span, 4_294_967_290))


def calculate_space_to_provide_megabytes(gigabytes: int) -> int:
    return gigabytes * 1024


def run_fio(file_path: str | Path, *, rw: Literal["randread", "randwrite"], qd: int) -> tuple[str, str]:
    """Run one fio pass against ``file_path`` and parse the bandwidth + IOPS.

    Matches the legacy mytonprovider invocation exactly (4K blocks, 15s runtime,
    libaio, direct I/O, 4G working set). The ``(bandwidth, iops)`` strings are
    preserved verbatim from fio output (e.g. ``"245MiB/s"`` and ``"62451"``) so
    downstream payloads match the wire protocol byte-for-byte.

    :raises RuntimeError: fio exits non-zero or its output cannot be parsed.
    """

    fio_args_common = (
        "--name=test",
        "--runtime=15",
        "--blocksize=4k",
        "--ioengine=libaio",
        "--direct=1",
        "--size=4G",
        "--randrepeat=1",
        "--gtod_reduce=1",
    )
    cmd = (
        "fio",
        *fio_args_common,
        f"--filename={file_path}",
        f"--readwrite={rw}",
        f"--iodepth={qd}",
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"fio failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    mode = "read" if rw == "randread" else "write"
    idx = result.stdout.find(f"{mode}:")
    if idx < 0:
        raise RuntimeError(f"fio output missing '{mode}:' line")
    parts = result.stdout[idx:].split(" ")
    if len(parts) < 3:
        raise RuntimeError(f"fio output malformed: {result.stdout[idx : idx + 80]}")
    iops = parts[1].split("=", 1)[1].rstrip(",")
    bandwidth = parts[2].split("=", 1)[1]
    return bandwidth, iops


def check_adnl_port(host: str, port: int, pubkey_hex: str) -> tuple[bool, str | None]:
    def _check_via(
        checker_host_: str,
        host_: str,
        port_: int,
        pubkey_hex_: str,
    ) -> tuple[bool, str | None]:
        url = f"http://{checker_host_}/adnl_check"
        payload = {"host": host_, "port": port_, "pubkey": pubkey_hex_}
        try:
            response = requests.post(url, json=payload, timeout=3)
            data = response.json()
        except Exception as exc:
            return False, f"{checker_host_}: {type(exc).__name__}: {exc}"
        if data.get("ok"):
            return True, None
        return False, f"{checker_host_}: {data.get('message', 'unknown error')}"

    last_error: str | None = None
    checkers = random.sample(
        constants.CHECKER_HOSTS,
        k=min(3, len(constants.CHECKER_HOSTS)),
    )
    for checker_host in checkers:
        ok, error = _check_via(checker_host, host, port, pubkey_hex)
        if ok:
            return True, None
        last_error = error
    return False, last_error


# Sentinel-by-presence map populated by :func:`cache_update_available`: ``None``
# means "checked, up to date"; a version string means "update available"; a
# missing key means "not checked yet".
_UPDATE_CACHE: dict[str, str | None] = {}


def cache_update_available(module_name: str, src_path: Path) -> None:
    """Probe ``origin`` for a newer tag and cache the result for :func:`version_rows`."""
    try:
        repo = LocalGitRepo(str(src_path))
        _UPDATE_CACHE[module_name] = repo.remote.info.latest_version if repo.has_updates(by="version") else None
    except GitError:
        _UPDATE_CACHE[module_name] = None


def version_rows(module_name: str, src_path: Path) -> list[tuple[ColorText, str | ColorText]]:
    """Build ``Module`` + ``Version`` rows; annotate Version with cached update state."""

    def label(t: str) -> ColorText:
        return ColorText(t, Color.CYAN)

    try:
        version_line = LocalGitRepo(str(src_path)).info.version
    except GitError:
        return [(label("Module"), module_name), (label("Version"), "unknown")]
    if module_name in _UPDATE_CACHE:
        latest = _UPDATE_CACHE[module_name]
        if latest:
            suffix = colorize_text(f"\u2192 {latest} available", Color.GREEN)
            version_line = f"{version_line} {suffix}"
        else:
            version_line = f"{version_line} latest"
    return [
        (label("Module"), module_name),
        (label("Version"), version_line),
    ]

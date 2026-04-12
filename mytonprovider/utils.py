from __future__ import annotations

import importlib.metadata
import json
import os
import pwd
import random
import re
import subprocess
from pathlib import Path
from typing import Final, Literal

import requests
from mypylib import (
    Dict,
    bcolors,
    parse_github_url,
)

from mytonprovider import constants
from mytonprovider.types import Channel, InstalledVersion, RefKind, StatusBlock

CLASSIFY_REF_TIMEOUT_SEC: Final[int] = 10
GIT_SUBPROCESS_TIMEOUT_SEC: Final[int] = 5

ADNL_CHECK_SAMPLE_SIZE: Final[int] = 3
ADNL_CHECK_TIMEOUT_SEC: Final[float] = 2.1

_SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+].*)?$")


def classify_ref(author: str, repo: str, ref: str) -> RefKind:
    """Classify a git ref as tag or branch via ``git ls-remote``."""
    url = f"https://github.com/{author}/{repo}.git"

    for kind, prefix in (("tag", "refs/tags/"), ("branch", "refs/heads/")):
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", url, f"{prefix}{ref}"],
            capture_output=True,
            check=False,
            timeout=CLASSIFY_REF_TIMEOUT_SEC,
        )
        if result.returncode == 0 and result.stdout.strip():
            return kind  # type: ignore[return-value]
        if result.returncode not in (0, 2):
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"git ls-remote failed for {url}: {stderr}")

    raise RuntimeError(f"ref {ref!r} not found in {author}/{repo} (neither tag nor branch)")


def parse_revision_kind(revision: str) -> RefKind:
    """Classify a revision string as tag or branch using a semver heuristic."""
    return "tag" if _SEMVER_RE.match(revision) else "branch"


def read_pep610_version(package_name: str) -> InstalledVersion:
    """Read installed version metadata via PEP 610 ``direct_url.json``."""
    try:
        dist = importlib.metadata.distribution(package_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"{package_name}: package not installed") from exc

    direct_url_text = dist.read_text("direct_url.json")
    if not direct_url_text:
        raise RuntimeError(
            f"{package_name}: direct_url.json not found — "
            "reinstall via 'pip install git+https://...@<ref>'"
        )

    data = json.loads(direct_url_text)
    vcs_info = data.get("vcs_info")
    if not vcs_info:
        raise RuntimeError(
            f"{package_name}: editable or non-VCS install — version tracking unavailable"
        )

    requested = vcs_info.get("requested_revision")
    if not requested:
        raise RuntimeError(
            f"{package_name}: install has no requested_revision — "
            "reinstall with explicit '@<ref>' (e.g. '@v1.0.0' or '@master')"
        )

    commit = vcs_info.get("commit_id")
    if not commit:
        raise RuntimeError(f"{package_name}: direct_url.json missing commit_id")

    url = data.get("url")
    if not url:
        raise RuntimeError(f"{package_name}: direct_url.json missing url")
    try:
        author, repo, _ = parse_github_url(str(url))
    except ValueError as exc:
        raise RuntimeError(f"{package_name}: invalid url in direct_url.json: {exc}") from exc

    return InstalledVersion(
        channel=Channel(
            author=author,
            repo=repo,
            ref=requested,
            ref_kind=parse_revision_kind(requested),
        ),
        commit=str(commit),
    )


def _run_git_local(args: list[str], cwd: Path) -> str:
    """Run a git command in *cwd* and return stripped stdout."""
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={cwd}", *args],
            cwd=str(cwd),
            capture_output=True,
            check=False,
            timeout=GIT_SUBPROCESS_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git {' '.join(args)} failed: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {stderr}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def read_git_clone_version(git_path: Path) -> InstalledVersion:
    """Read installed version metadata from a local git clone."""
    if not git_path.exists():
        raise RuntimeError(f"git clone not found: {git_path}")

    origin_url = _run_git_local(["remote", "get-url", "origin"], cwd=git_path)
    try:
        author, repo, _ = parse_github_url(origin_url)
    except ValueError as exc:
        raise RuntimeError(f"{git_path}: invalid origin url: {exc}") from exc

    commit = _run_git_local(["rev-parse", "HEAD"], cwd=git_path)

    ref: str
    ref_kind: RefKind
    try:
        ref = _run_git_local(["symbolic-ref", "--short", "HEAD"], cwd=git_path)
        ref_kind = "branch"
    except RuntimeError:
        # Detached HEAD — must be on an exact tag.
        try:
            ref = _run_git_local(["describe", "--tags", "--exact-match", "HEAD"], cwd=git_path)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{git_path}: detached HEAD is not on an exact tag — cannot classify ref"
            ) from exc
        ref_kind = "tag"

    return InstalledVersion(
        channel=Channel(author=author, repo=repo, ref=ref, ref_kind=ref_kind),
        commit=commit,
    )


def check_adnl_connection(host: str, port: int, pubkey: str) -> tuple[bool, str | None]:
    """Verify that an ADNL UDP node is reachable from the outside."""
    sample_size = min(ADNL_CHECK_SAMPLE_SIZE, len(constants.ADNL_CHECKER_HOSTS))
    checker_hosts = random.sample(constants.ADNL_CHECKER_HOSTS, k=sample_size)

    ok = False
    error: str | None = None
    for checker_host in checker_hosts:
        checker_url = f"http://{checker_host}/adnl_check"
        ok, error = _do_check_adnl_connection(checker_url, host, port, pubkey)
        if ok:
            return True, None
    return ok, error


def _do_check_adnl_connection(
    checker_url: str,
    host: str,
    port: int,
    pubkey: str,
) -> tuple[bool, str | None]:
    """Perform a single ADNL check request against *checker_url*."""
    payload = {"host": host, "port": port, "pubkey": pubkey}
    try:
        response = requests.post(checker_url, json=payload, timeout=ADNL_CHECK_TIMEOUT_SEC)
        data = Dict(response.json())
    except (requests.RequestException, ValueError) as exc:
        return False, (
            f"Failed to check ADNL connection to {host}:{port}: {type(exc).__name__}: {exc}"
        )

    if data.ok:
        return True, None
    return False, (
        f"Failed to check ADNL connection to {host}:{port}, pubkey={pubkey}: {data.message}"
    )


def get_threshold_color(
    value: float | None,
    threshold: float,
    logic: Literal["more", "less"],
    ending: str | None = None,
) -> str:
    """Color a numeric value green/red based on threshold comparison."""
    if value is None:
        return "n/a"
    is_good = value >= threshold if logic == "more" else value <= threshold
    if is_good:
        return bcolors.green_text(value, ending)
    return bcolors.red_text(value, ending)


def resolve_app_home() -> Path:
    """Return the home directory, resolving SUDO_USER when running as root."""
    if os.geteuid() != 0:
        return Path.home()

    for env_var in ("SUDO_USER", "DOAS_USER"):
        sudo_user = os.environ.get(env_var)
        if sudo_user and sudo_user != "root":
            try:
                return Path(pwd.getpwnam(sudo_user).pw_dir)
            except KeyError:
                continue

    system_bin = Path("/usr/local/bin") / constants.APP_NAME
    try:
        if system_bin.is_symlink() or system_bin.exists():
            owner = system_bin.resolve(strict=True).owner()
            if owner and owner != "root":
                return Path(pwd.getpwnam(owner).pw_dir)
    except (OSError, KeyError):
        pass

    return Path.home()


def get_config_path() -> Path:
    """Return absolute path to the local mytonprovider config DB."""
    return resolve_app_home() / constants.CONFIG_PATH


def is_newer_version(current: str, other: str) -> bool:
    """Return True if ``other`` is a newer semver version than ``current``."""

    def core_parts(v: str) -> tuple[int, ...]:
        core = v.lstrip("v").split("-", 1)[0].split("+", 1)[0]
        return tuple(int(p) for p in core.split("."))

    return core_parts(other) > core_parts(current)


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _visible_len(text: str) -> int:
    """Return the visible length of *text* after stripping ANSI escape codes."""
    return len(_ANSI_RE.sub("", text))


def render_status_block(block: StatusBlock) -> None:
    """Render a ``StatusBlock`` as a unified box-style status panel."""
    if not block.card and not block.rows:
        return

    def _format_group(group: list[tuple[str, str]]) -> list[str]:
        max_lbl = max((_visible_len(l) for l, _ in group if l), default=0)
        result: list[str] = []
        for label, value in group:
            if not label and not value:
                result.append("")
            else:
                pad = max_lbl - _visible_len(label)
                result.append(f"  {label}{' ' * pad}   {value}")
        return result

    lines: list[str] = []
    if block.card:
        card_rows = [(l + ":", v) for l, v in block.card]
        lines.extend(_format_group(card_rows))
        if block.rows:
            lines.append("")
    if block.rows:
        lines.extend(_format_group(block.rows))

    max_content = max((_visible_len(line) for line in lines if line), default=0)

    top_label = f"{bcolors.cyan_text(block.name)} {bcolors.yellow_text(block.version)}"
    top_label_vis = _visible_len(top_label)

    bottom_label = block.service_text
    bottom_label_vis = _visible_len(bottom_label)

    inner = max(
        max_content + 2,
        top_label_vis + 4,
        bottom_label_vis + 4,
    )

    top_fill = inner - top_label_vis - 4
    print(f"  ╭─ {top_label} {'─' * top_fill}─╮")

    print(f"  │{' ' * inner}│")
    for line in lines:
        if not line:
            print(f"  │{' ' * inner}│")
        else:
            pad_right = inner - _visible_len(line)
            print(f"  │{line}{' ' * pad_right}│")
    print(f"  │{' ' * inner}│")

    bottom_fill = inner - bottom_label_vis - 3
    print(f"  ╰{'─' * bottom_fill} {bottom_label} ─╯")

    if block.update_text:
        update_icon = bcolors.yellow_text("⚡")
        update_msg = bcolors.green_text(block.update_text)
        print(f"  {update_icon} {update_msg}")
        print()

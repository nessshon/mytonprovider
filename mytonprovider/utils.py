import random
import shutil
from pathlib import Path
from typing import Final, Literal

import requests
from mypycli.console import colorize_text
from mypycli.types import Color
from mypycli.utils import LocalGitRepo, RemoteGitRepo, SystemdService, format_duration, run

from mytonprovider.locales import _

ADNL_CHECKER_HOSTS: Final[tuple[str, ...]] = (
    "5.154.181.153",
    "45.129.96.53",
    "2.56.126.137",
)


def create_status_header(
    label: str,
    version: str | None = None,
    *,
    target: str | None = None,
    available: bool = False,
) -> str:
    parts = [colorize_text(f"● {label}", Color.CYAN)]
    if version:
        parts.append(colorize_text(version, Color.CYAN))
    if available and target:
        parts.append(colorize_text(f"↑ {target}", Color.MAGENTA))
    return " ".join(parts)


def create_status_footer(service: SystemdService, lang: Literal["en", "ru", "zh"] = "en") -> str:
    if service.is_active:
        state = colorize_text(f"✓ {_('common.status.active')}", Color.GREEN)
    else:
        state = colorize_text(f"✕ {_('common.status.inactive')}", Color.RED)
    if service.uptime is not None:
        duration = colorize_text(format_duration(service.uptime, lang=lang), Color.GREEN)
        state = f"{state} • {_('common.status.uptime')} {duration}"
    return state


def display_version(repo: LocalGitRepo, *, author: str, repo_name: str) -> str:
    info = repo.info
    is_official = repo.author == author and repo.repo_name == repo_name

    if is_official and info.tag:
        return info.tag

    ref = f"{info.branch}@{info.commit_short}" if info.branch else info.commit_short
    return ref if is_official else f"{repo.author}/{ref}"


def check_update(repo: LocalGitRepo) -> tuple[bool, str | None]:
    if repo.info.tag:
        return repo.has_updates(by="version"), repo.remote.info.latest_version
    return repo.has_updates(by="commit"), repo.remote.info.commit_short


def clone_repo(src_path: Path, author: str, repo_name: str) -> None:
    if src_path.exists():
        shutil.rmtree(src_path)
    src_path.parent.mkdir(parents=True, exist_ok=True)
    RemoteGitRepo(author, repo_name).clone(str(src_path))
    run(["git", "config", "--system", "--add", "safe.directory", str(src_path)], check=True)


def build_go_binary(src_path: Path, bin_path: Path, entry: str, timeout: int = 60) -> None:
    args = ["go", "build", "-o", str(bin_path), entry]
    run(args, cwd=str(src_path), check=True, timeout=timeout)


def chown_owner(path: Path, ref: Path) -> None:
    owner = f"{ref.owner()}:{ref.group()}"
    run(["chown", "-R", owner, str(path)], check=True)


def check_adnl_connection(
    host: str,
    port: int,
    pubkey: str,
    *,
    timeout: float = 2.5,
) -> bool:
    for checker in random.sample(list(ADNL_CHECKER_HOSTS), k=len(ADNL_CHECKER_HOSTS)):
        try:
            response = requests.post(
                f"http://{checker}/adnl_check",
                json={"host": host, "port": port, "pubkey": pubkey},
                timeout=timeout,
            )
            if response.json().get("ok"):
                return True
        except Exception:
            continue
    return False

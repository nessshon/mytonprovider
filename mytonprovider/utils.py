import random
from typing import Literal

import requests
from mypycli.console import colorize_text
from mypycli.types import Color
from mypycli.utils import LocalGitRepo, SystemdService, format_duration

from mytonprovider.locales import _


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


def check_repo_update(repo: LocalGitRepo) -> tuple[bool, str | None]:
    info = repo.info
    if info.tag:
        return repo.has_updates(by="version"), repo.remote.info.latest_version
    return repo.has_updates(by="commit"), repo.remote.info.commit_short


def check_adnl_connection(host: str, port: int, pubkey: str, *, timeout: float = 2.5) -> bool:
    adnl_checker_hosts = (
        "45.129.96.53",
        "5.154.181.153",
        "2.56.126.137",
    )
    for checker in random.sample(adnl_checker_hosts, k=len(adnl_checker_hosts)):
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

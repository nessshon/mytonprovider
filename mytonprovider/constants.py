from __future__ import annotations

import getpass
import os
import pwd
from pathlib import Path
from typing import Final


def _resolve_install_user() -> str:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        return sudo_user
    current = getpass.getuser()
    if current != "root":
        return current
    try:
        uid = GLOBAL_CONFIG_PATH.stat().st_uid
        return pwd.getpwuid(uid).pw_name
    except (FileNotFoundError, KeyError) as exc:
        raise RuntimeError("Cannot determine install user") from exc


APP_NAME: Final[str] = "mytonprovider"
APP_LABEL: Final[str] = "My TON Provider"

PACKAGE_DIR: Final[Path] = Path(__file__).resolve().parent
SRC_DIR: Final[Path] = Path("/usr/src")
BIN_DIR: Final[Path] = Path("/usr/local/bin")
GLOBAL_CONFIG_PATH: Final[Path] = Path("/var/ton/global.config.json")

# Shell helpers stay in the cloned repo tree (git clone preserves +x); the
# Python package never ships them, so PACKAGE_DIR is intentionally not used.
SCRIPTS_DIR: Final[Path] = SRC_DIR / APP_NAME / "scripts"

INSTALL_USER: Final[str] = _resolve_install_user()
USER_HOME: Final[Path] = Path(pwd.getpwnam(INSTALL_USER).pw_dir)

WORK_DIR: Final[Path] = USER_HOME / ".local" / "share" / APP_NAME
VENV_DIR: Final[Path] = USER_HOME / ".local" / "venv" / APP_NAME

TELEMETRY_URL: Final[str] = "https://mytonprovider.org/api/v1/providers"
BENCHMARK_URL: Final[str] = "https://mytonprovider.org/api/v1/benchmarks"

REGISTRATION_ADDRESS: Final[str] = "0:7777777777777777777777777777777777777777777777777777777777777777"
REGISTRATION_AMOUNT: Final[float] = 0.01
REGISTRATION_MIN_BALANCE: Final[float] = 0.03
REGISTRATION_COMMENT_PREFIX: Final[str] = "tsp-"

CHECKER_HOSTS: Final[tuple[str, ...]] = (
    "45.129.96.53",
    "5.154.181.153",
    "2.56.126.137",
    "91.194.11.68",
    "45.12.134.214",
    "138.124.184.27",
    "103.106.3.171",
)

TONUTILS_STORAGE_AUTHOR: Final[str] = "xssnick"
TONUTILS_STORAGE_REPO: Final[str] = "tonutils-storage"
TONUTILS_STORAGE_REF: Final[str] = "v1.4.1"
TONUTILS_STORAGE_ENTRY: Final[str] = "cli/main.go"

TONUTILS_STORAGE_PROVIDER_AUTHOR: Final[str] = "xssnick"
TONUTILS_STORAGE_PROVIDER_REPO: Final[str] = "tonutils-storage-provider"
TONUTILS_STORAGE_PROVIDER_REF: Final[str] = "v0.4.0"
TONUTILS_STORAGE_PROVIDER_ENTRY: Final[str] = "cmd/main.go"

from pathlib import Path
from typing import Final

# Application identity
APP_NAME: Final[str] = "mytonprovider"

# Package layout
PACKAGE_DIR: Final[Path] = Path(__file__).resolve().parent
SCRIPTS_DIR: Final[Path] = PACKAGE_DIR / "scripts"
TRANSLATIONS_PATH: Final[Path] = PACKAGE_DIR / "translations.json"

# Local mytonprovider data (relative to user home)
WORK_DIR: Final[Path] = Path(".local/share") / APP_NAME
CONFIG_PATH: Final[Path] = WORK_DIR / f"{APP_NAME}.db"

# Local Python virtual environment (relative to user home)
VENV_DIR: Final[Path] = Path(".local/venv")
VENV_PATH: Final[Path] = VENV_DIR / APP_NAME

# Sudoers fragment for Go-module auto-update from user-mode daemon
SUDOERS_PATH: Final[Path] = Path("/etc/sudoers.d") / APP_NAME

# Global TON config
GLOBAL_CONFIG_PATH: Final[Path] = Path("/var/ton/global.config.json")
GLOBAL_CONFIG_URL: Final[str] = "https://igroman787.github.io/global.config.json"

# TON storage provider registration
REGISTRATION_ADDRESS: Final[str] = "0:7777777777777777777777777777777777777777777777777777777777777777"
REGISTRATION_AMOUNT: Final[float] = 0.01
REGISTRATION_MIN_BALANCE: Final[float] = 0.03
REGISTRATION_COMMENT_PREFIX: Final[str] = "tsp-"

# Random port range used at install time for ADNL UDP / local HTTP APIs
PORT_RANGE_MIN: Final[int] = 1024
PORT_RANGE_MAX: Final[int] = 65000

# Telemetry endpoints
TELEMETRY_URL: Final[str] = "https://mytonprovider.org/api/v1/providers"
BENCHMARK_URL: Final[str] = "https://mytonprovider.org/api/v1/benchmarks"

# mytonprovider (python) package
MYTONPROVIDER_AUTHOR: Final[str] = "nessshon"
MYTONPROVIDER_REPO: Final[str] = "mytonprovider"
MYTONPROVIDER_VERSION: Final[str] = "v1.0.0"

# tonutils-storage (go) package
TON_STORAGE_AUTHOR: Final[str] = "xssnick"
TON_STORAGE_REPO: Final[str] = "tonutils-storage"
TON_STORAGE_VERSION: Final[str] = "v1.4.1"

# tonutils-storage-provider (go) package
TON_STORAGE_PROVIDER_AUTHOR: Final[str] = "xssnick"
TON_STORAGE_PROVIDER_REPO: Final[str] = "tonutils-storage-provider"
TON_STORAGE_PROVIDER_VERSION: Final[str] = "v0.4.0"

# ADNL health check hosts (used for port checks and ping telemetry)
ADNL_CHECKER_HOSTS: Final[tuple[str, ...]] = (
    "45.129.96.53",
    "5.154.181.153",
    "2.56.126.137",
    "91.194.11.68",
    "45.12.134.214",
    "138.124.184.27",
    "103.106.3.171",
)

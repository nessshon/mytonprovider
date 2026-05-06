from pathlib import Path
from typing import Final

APP_NAME: Final[str] = "mytonprovider"
APP_LABEL: Final[str] = "My TON Provider"

STATUS_PANEL_WIDTH: Final[int] = 88

LIB_DIR: Final[Path] = Path("/var/lib")
SRC_DIR: Final[Path] = Path("/usr/src")
BIN_DIR: Final[Path] = Path("/usr/local/bin")
WORK_DIR: Final[Path] = LIB_DIR / APP_NAME
VENV_DIR: Final[Path] = WORK_DIR / "venv"

TON_CONFIG_PATH: Final[Path] = Path("/var/ton/global.config.json")
TELEMETRY_URL: Final[str] = "https://mytonprovider.org/api/v1/providers"
BENCHMARK_URL: Final[str] = "https://mytonprovider.org/api/v1/benchmarks"

TON_STORAGE_PROVIDER_DEFAULT_COST: Final[int] = 10
TON_STORAGE_PROVIDER_DEFAULT_MAX_BAG_SIZE: Final[int] = 50
TON_STORAGE_DEFAULT_STORAGE_PATH: Final[str] = "/var/storage"

REGISTRATION_AMOUNT: Final[float] = 0.01
REGISTRATION_MIN_BALANCE: Final[float] = 0.03
REGISTRATION_COMMENT_PREFIX: Final[str] = "tsp-"
REGISTRATION_ADDRESS: Final[str] = "0:7777777777777777777777777777777777777777777777777777777777777775"

WALLET_MIN_BALANCE: Final[float] = 0.2
WALLET_GAS_RESERVE: Final[float] = 0.0005

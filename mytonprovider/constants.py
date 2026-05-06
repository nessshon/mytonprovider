from pathlib import Path
from typing import Final

APP_NAME: Final[str] = "mytonprovider"
APP_LABEL: Final[str] = "My TON Provider"
APP_PROMPT: Final[str] = "MyTonProvider"

LIB_DIR: Final[Path] = Path("/var/lib")
SRC_DIR: Final[Path] = Path("/usr/src")
BIN_DIR: Final[Path] = Path("/usr/local/bin")
WORK_DIR: Final[Path] = LIB_DIR / APP_NAME
VENV_DIR: Final[Path] = WORK_DIR / "venv"

TELEMETRY_URL: Final[str] = "https://mytonprovider.org/api/v1/providers"
BENCHMARK_URL: Final[str] = "https://mytonprovider.org/api/v1/benchmarks"

TON_CONFIG_PATH: Final[Path] = Path("/var/ton/global.config.json")

TON_STORAGE_PROVIDER_DEFAULT_COST: Final[int] = 10
TON_STORAGE_PROVIDER_DEFAULT_MAX_BAG_SIZE: Final[int] = 60
TON_STORAGE_DEFAULT_STORAGE_PATH: Final[str] = "/var/storage"

REGISTRATION_DESTINATION: Final[str] = "0:7777777777777777777777777777777777777777777777777777777777777777"
REGISTRATION_AMOUNT: Final[float] = 0.01
REGISTRATION_MIN_BALANCE: Final[float] = 0.03
REGISTRATION_COMMENT_PREFIX: Final[str] = "tsp-"

import shutil
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timezone


def get_disk_free_space() -> int:
    total, used, free = shutil.disk_usage("/")
    return free // 2 ** 30


@lru_cache
def get_head_path(file):
    cwd = str(Path(file).resolve())
    return cwd.split("mytonprovider")[0] + "mytonprovider"


def get_cur_dt() -> str:
    return str(datetime.now(timezone.utc))


def generate_login() -> str:
    pass


def generate_password() -> str:
    pass


def start_service():
    pass


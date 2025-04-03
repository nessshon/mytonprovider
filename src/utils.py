import shutil
import random
from string import digits, ascii_letters
from functools import lru_cache
from pathlib import Path


def get_disk_free_space() -> int:
    total, used, free = shutil.disk_usage("/")
    return free // 2 ** 30


@lru_cache
def get_package_path():
    cwd = str(Path(__file__).resolve())
    return cwd.split("mytonprovider")[0] + "mytonprovider"


def generate_login() -> str:
    return r''.join(random.choices(population=ascii_letters, k=10))


def generate_password() -> str:
    # punctuation = r"""!#$%&()*+,-./:;<=>?@[\]^_{|}~"""
    symbols = ascii_letters + digits #+ punctuation
    return r''.join(random.choices(population=symbols, k=10))



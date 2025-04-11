import shutil
import random
from string import digits, ascii_letters
from functools import lru_cache
from pathlib import Path


def get_disk_free_space(disk_path) -> int:
	total, used, free = shutil.disk_usage(disk_path)
	free_megabytes = int(free /1024 /1024)
	return free_megabytes
#end define

@lru_cache
def get_package_path():
	cwd = str(Path(__file__).resolve())
	return cwd.split("mytonprovider")[0] + "mytonprovider"
#end define

def generate_login() -> str:
	return r''.join(random.choices(population=ascii_letters, k=10))
#end define

def generate_password() -> str:
	# punctuation = r"""!#$%&()*+,-./:;<=>?@[\]^_{|}~"""
	symbols = ascii_letters + digits #+ punctuation
	return r''.join(random.choices(population=symbols, k=10))
#end define

import shutil


def get_disk_free_space() -> int:
    total, used, free = shutil.disk_usage("/")
    return free // 2 ** 30


def ton_storage_installed() -> bool:
    return False


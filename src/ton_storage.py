from .utils import generate_login, generate_password, get_package_path

from random import randint
from mypylib import add2systemd, Dict, MyPyClass
from mypylib import write_config_to_file, read_config_from_file
import subprocess
import os


def install(
        user,
        src_dir,
        bin_dir,
        venvs_dir,
        venv_path,
        src_path,
        util: str = None,
        storage_path: str = None,
        **kwargs
            ):
    name = util.lower()
    host = "localhost"
    port = randint(1024, 49151)
    login = generate_login()
    password = generate_password()
    path = storage_path

    subprocess.run(["bash", get_package_path() + "/src/scripts/ton_storage_install.sh", path])

    cmd = f"{bin_dir}/tonutils-storage --api {host}:{port} --api-login {login} --api-password {password}"

    os.makedirs(storage_path, exist_ok=True)
    add2systemd(
        name=name,
        start=cmd,
        workdir=storage_path,
    )

    local = MyPyClass("./tonstorage-control.py")
    local.start_service(name)
    local.stop_service(name)

    mconfig_path = f"/home/{user}/.local/share/mytonprovider/mytonprovider.db"
    os.makedirs(f'/home/{user}/.local/share/mytonprovider/',exist_ok=True)
    ton_storage = Dict()

    ton_storage.api = Dict()
    ton_storage.api.port = port
    ton_storage.api.host = host
    ton_storage.api.login = login
    ton_storage.api.password = password

    ton_storage.storage_path = path
    ton_storage.user = user
    ton_storage.src_dir = src_dir
    ton_storage.bin_dir = bin_dir
    ton_storage.venvs_dir = venvs_dir
    ton_storage.venv_path = venv_path
    ton_storage.src_path = src_path

    write_config_to_file(config_path=mconfig_path, data=ton_storage)








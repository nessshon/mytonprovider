from utils import generate_login, generate_password, get_package_path

from random import randint
from mypylib import add2systemd, Dict, MyPyClass
from mypylib import write_config_to_file
import subprocess
import os


def install(
        args: dict,
        author="xssnick",
        repo="tonutils-storage-provider",
        branch="master",
        entry_point="cmd/main.go",
        storage_path: str = None,
        storage_disk_space: int = None,
        **kwargs
            ):
    name = "tonstorageprovider"
    host = "localhost"
    port = randint(1024, 49151)
    login = generate_login()
    password = generate_password()

    subprocess.run([
        "bash",
        get_package_path() + "/installers/install_go_package.sh",
        "-a", author, "-r", repo, "-b", branch, "-e", entry_point
    ])

    cmd = f"{args['bin_dir']}/tonutils-storage --api {host}:{port} --api-login {login} --api-password {password}"

    os.makedirs(storage_path, exist_ok=True)
    add2systemd(
        name=name,
        start=cmd,
        workdir=storage_path,
    )

    local = MyPyClass("./tonstorage-control.py")
    local.start_service(name)
    local.stop_service(name)

    os.makedirs(storage_path, exist_ok=True)
    add2systemd(
        name=name,
        start=cmd,
        workdir=storage_path,
    )

    local = MyPyClass("./tonstorage-control.py")
    local.start_service(name)
    local.stop_service(name)

    mconfig_path = f"/home/{args['user']}/.local/share/mytonprovider/mytonprovider.db"
    os.makedirs(f"/home/{args['user']}/.local/share/mytonprovider/", exist_ok=True)
    ton_storage = Dict()

    ton_storage.api = Dict()
    ton_storage.api.port = port
    ton_storage.api.host = host
    ton_storage.api.login = login
    ton_storage.api.password = password

    ton_storage.storage_path = storage_path
    ton_storage.user = args['user']
    ton_storage.src_dir = args['src_dir']
    ton_storage.bin_dir = args['bin_dir']
    ton_storage.venvs_dir = args['venvs_dir']
    ton_storage.venv_path = args['venv_path']
    ton_storage.src_path = args['src_path']

    write_config_to_file(config_path=mconfig_path, data=ton_storage)








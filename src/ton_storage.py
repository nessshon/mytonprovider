from src.schemas import Storage
from src.utils import generate_login, generate_password, get_package_path

from random import randint
from mypylib import add2systemd
import json
import subprocess


def install(storage_path: str = None, storage_disk_space: int = None, **kwargs):
    st = Storage(
        host="localhost",
        port=randint(1024, 49151),
        login=generate_login(),
        password=generate_password(),
        path=storage_path,
        space=storage_disk_space
    )
    with open(get_package_path() + "/config.json", "w") as f:
        json.dump({"login": st.login, "config": st.password}, f, indent=4)

    cmd = f"{st.cmd} --api {st.host}:{st.port} --api-login {st.login} --api-port {st.port}"
    add2systemd(
        name=st.name,
        start=cmd,
        workdir=get_package_path(),
    )

    subprocess.run(["bash", get_package_path() + "scripts/ton_storage_install.sh", "--path", st.path, "--space", st.space])

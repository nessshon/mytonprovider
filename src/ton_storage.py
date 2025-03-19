from src.schemas import StorageScheme
from src.utils import generate_login, generate_password, get_head_path

from random import randint
from mypylib import add2systemd
import json
import subprocess


def install(storage_path: str = None, storage_disk_space: int = None, **kwargs):
    st = StorageScheme(
        host="localhost",
        port=randint(1024, 49151),
        login=generate_login(),
        password=generate_password(),
        path=storage_path,
        space=storage_disk_space
    )
    with open(get_head_path(__file__) + "/credentials.json") as f:
        json.dump({"login": st.login, "password": st.password}, f, indent=4)

    cmd = f"{st.cmd} --api {st.host}:{st.port} --api-login {st.login} --api-port {st.port}"

    add2systemd(
        name=st.name,
        start=cmd,
        pre=...,
        workdir=get_head_path(__file__),
    )

    # запускаем инстал сш скрипт # start_service()  # взять из мтк ? дефолтные переменные из файла


    # storage_path и storage_disk_space - прописывается в конфиг ton-storage



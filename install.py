from src.utils import get_disk_free_space
from src import ton_storage, ton_storage_provider, ton_tunnel_provider

from inquirer import Text, List, Path
from typing import Any
import inquirer
from mypylib import Dict
import sys


def ask() -> dict[str, Any]:
    util = inquirer.prompt([
        List(
            name="util",
            message="Выберете утилиту",
            choices=["TonStorage", "TonStorageProvider", "TonTunnelProvider"]
        )
    ])
    answers = [util]
    if  util["util"] == "TonStorage":

        answers.append(inquirer.prompt([
            Path(
                name="storage_path",
                message=f"Ввод места хранения файлов ton_storage (по умолчанию: /var/tonstorage/)",
                default="/var/tonstorage",
            )
        ]))

    elif util["util"] == "TonStorageProvider":
        answers.append(inquirer.prompt([
            Text(
                name="storage_cost",
                message="Сколько будет стоить хранения 1 Гб/мес ?"
            ),
            Path(
                name="storage_path",
                message=f"Ввод места хранения файлов ton_storage (по умолчанию: /var/tonstorage/)",
                default="/var/tonstorage",
            ),
            Text(
                name="storage_disk_space",
                message="Какой размер от свободного размера диска может занять ton_storage в ГБ? (по умолчанию 90% от диска)",
                default=get_disk_free_space() * 0.9
            )
        ]))

    elif util["util"] == "TonTunnelProvider":
        answers.append(inquirer.prompt([
            Text(
                name="traffic_cost",
                message="Сколько будет стоить 1 Гб трафика сети?"
            )
        ]))

    return Dict(*answers)


def main():
    args = sys.argv
    answers: dict = ask()
    if answers.get("util") == "TonStorage":
        return ton_storage.install(*args, **answers)
    elif answers.get("util") == "TonStorageProvider":
        return ton_storage_provider.install(*args, **answers)
    elif answers.get("util") == "TonTunnelProvider":
        return ton_tunnel_provider.install(*args, **answers)


if __name__ == "__main__":
    main()


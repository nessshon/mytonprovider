from src.utils import get_disk_free_space
from src import ton_storage, ton_storage_provider, ton_tunnel_provider

from inquirer import Text, List, Path, Checkbox
from typing import Any
import inquirer
from mypylib import Dict
import sys


def ask() -> dict[str, Any]:
    util = inquirer.prompt([
        Checkbox(
            name="util",
            message="Выберете утилиты",
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
    print(answers)
    if "TonStorage" in answers.get("util"):
        ton_storage.install(*args, **answers)
    if "TonStorageProvider" in answers.get("util"):
        ton_storage_provider.install(*args, **answers)
    if "TonTunnelProvider" in answers.get("util"):
        ton_tunnel_provider.install(*args, **answers)


if __name__ == "__main__":
    main()


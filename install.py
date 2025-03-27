from src.utils import get_disk_free_space
from src import ton_storage, ton_storage_provider, ton_tunnel_provider

from inquirer import Text, List, Path
from typing import Any
import inquirer
from mypylib import Dict


def ask() -> dict[str, Any]:
    util = inquirer.prompt([
        List(
            name="util",
            message="Выберете утилиту",
            choices=["TonStorage", "TonStorageProvider", "TonTunnelProvider"]
        )
    ])
    answers = [util]
    match util["util"]:

        case "TonStorage":
            answers.append(inquirer.prompt([
                Path(
                    name="storage_path",
                    message=f"Ввод места хранения файлов ton_storage (по умолчанию: /var/tonstorage/)",
                    default="/var/tonstorage",
                )
            ]))

        case "TonStorageProvider":
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

        case "TonTunnelProvider":
            answers.append(inquirer.prompt([
                Text(
                    name="traffic_cost",
                    message="Сколько будет стоить 1 Гб трафика сети?"
                )
            ]))

    return Dict(*answers)


def main():
    answers: dict = ask()
    match answers.get("util"):
        case "TonStorage": return ton_storage.install(**answers)
        case "TonStorageProvider": return ton_storage_provider.install(**answers)
        case "TonTunnelProvider": return ton_tunnel_provider.install(**answers)


if __name__ == "__main__":
    main()


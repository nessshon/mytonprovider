from src.utils import get_disk_free_space
from src import ton_storage, ton_storage_provider, ton_tunnel_provider

from inquirer import Text, List, Path, Checkbox
from typing import Any
import inquirer
from mypylib import Dict
import sys


def ask() -> dict[str, Any]:
    utils_q = []
    storage_ans = []
    provider_ans = []
    tunnel_ans = []
    utils_q.append(inquirer.prompt([
        Checkbox(
            name="utils",
            message="Выберете утилиты",
            choices=["TonStorage", "TonStorageProvider", "TonTunnelProvider"]
        )
    ]))
    if  "TonStorage" in utils_q[0]["utils"]:

        storage_ans.append(inquirer.prompt([
            Path(
                name="storage_path",
                message=f"Ввод места хранения файлов ton_storage (по умолчанию: /var/tonstorage/)",
                default="/var/tonstorage",
            )
        ]))

    if "TonStorageProvider" in utils_q[0]["utils"]:
        provider_ans.append(inquirer.prompt([
            Text(
                name="storage_cost",
                message="Сколько будет стоить хранения 1 Гб/мес ?"
            ),
            Text(
                name="storage_disk_space",
                message="Какой размер от свободного размера диска может занять ton_storage в ГБ? (по умолчанию 90% от диска)",
                default=get_disk_free_space() * 0.9
            )
        ]))

    if "TonTunnelProvider" in utils_q[0]["utils"]:
        tunnel_ans.append(inquirer.prompt([
            Text(
                name="traffic_cost",
                message="Сколько будет стоить 1 Гб трафика сети?"
            )
        ]))

    return Dict(*utils_q, *storage_ans, *provider_ans, *tunnel_ans)


def main():
    args: list = sys.argv[1:]
    answers: dict = ask()
    utils = answers.pop("utils")

    if "TonStorage" in utils:
        ton_storage.install(*args, **answers)

    if "TonStorageProvider" in utils:
        ton_storage_provider.install(*args, **answers)

    if "TonTunnelProvider" in utils:
        ton_tunnel_provider.install(*args, **answers)


if __name__ == "__main__":
    main()


from src.questions import utils_selection, storage_cost, storage_path, storage_disk_space, install_ton_storage, traffic_cost
from src import ton_storage, ton_storage_provider, ton_tunnel_provider

from typing import Any
import inquirer
from mypylib.mypylib import Dict


def ask() -> dict[str, Any]:
    answers = []
    util = inquirer.prompt([utils_selection])
    answers.append(util)
    match util["utils_selection"]:

        case "ton_storage":

            answers.append(inquirer.prompt([storage_path]))
            answers.append(inquirer.prompt([storage_disk_space]))

        case "ton_storage_provider":

            answers.append(inquirer.prompt([storage_cost]))
            answers.append(inquirer.prompt([storage_path]))
            answers.append(inquirer.prompt([storage_disk_space]))

        case "ton_tunnel_provider":
            answers.append(inquirer.prompt([traffic_cost]))

    return Dict(*answers)


def main():
    answers: dict = ask()

    match answers["utils_selection"]:
        case "ton_storage":
            return ton_storage.install(**answers)
        case "ton_storage_provider":
            return ton_storage_provider.install(**answers)
        case "ton_tunnel_provider":
            return ton_tunnel_provider.install(**answers)


if __name__ == "__main__":
    main()


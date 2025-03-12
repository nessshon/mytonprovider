from src.schemas import TonStorageScheme
from src.dialog import utils_selection, storage_cost, storage_path, storage_disk_space, install_ton_storage, traffic_cost
from src.utils import ton_storage_installed

import inquirer


def main():
    answers = []
    util = inquirer.prompt([utils_selection])
    answers.append(util)
    match util["utils_selection"]:
        case "ton_storage":

            answers.append(inquirer.prompt([storage_path]))
            answers.append(inquirer.prompt([storage_disk_space]))

        case "ton_storage_provider":

            answers.append(inquirer.prompt([storage_cost]))

            storage_installed_flag = True
            if not ton_storage_installed():
                answers.append(storage_installed_flag := inquirer.prompt([install_ton_storage]))

            if storage_installed_flag:
                answers.append(inquirer.prompt([storage_path]))
                answers.append(inquirer.prompt([storage_disk_space]))

        case "ton_tunnel_provider":
            answers.append(inquirer.prompt([traffic_cost]))

    print(answers)


if __name__ == "__main__":
    main()


from utils import get_disk_free_space
from modules import (
	main,
	ton_storage,
	ton_storage_provider,
	ton_tunnel_provider
)

#from inquirer import Text, Path, Checkbox
from typing import Any
import inquirer
from mypylib import Dict
import sys
import os


default_storage_path = "/var/storage"
default_storage_cost = 10
default_traffic_cost = 1



def parse_input_args():
	input_args: list = sys.argv[1:]
	args = Dict()
	for i in range(0, len(input_args), 2):
		if input_args[i].startswith("--"):
			key = input_args[i].lstrip("--")
			args[key] = input_args[i+1]
		else:
			print("Unknown schema of args")
			sys.exit(1)
	return args
#end define

def ignore_storage(answers):
	if "TonStorage" in answers["utils"]:
		return False
	return True
#end define

def ignore_provider(answers):
	if "TonStorageProvider" in answers["utils"]:
		return False
	return True
#end define

def ignore_tunnel(answers):
	if "TonTunnelProvider" in answers["utils"]:
		return False
	return True
#end define

def calculate_space_to_provide(answers):
	storage_path = answers.get("storage_path")
	os.makedirs(storage_path, exist_ok=True)
	free_space = get_disk_free_space(storage_path)
	available_space = int(free_space * 0.9)
	return str(available_space)
#end define


questions = [
	inquirer.Checkbox(
		name="utils",
		message="Выберете утилиты",
		choices=["TonStorage", "TonStorageProvider", "TonTunnelProvider"]
	),
	inquirer.Path(
		name="storage_path",
		message=f"Ввод места хранения файлов провайдера",
		default=default_storage_path,
		ignore=ignore_storage
	),
	inquirer.Text(
		name="storage_cost",
		message=f"Сколько TON будет стоить хранение 200 GB/month",
		default=default_storage_cost,
		ignore=ignore_provider
	),
	inquirer.Text(
		name="space_to_provide_megabytes",
		message=f"Какой размер от свободного размера диска может занять ton-storage в MB",
		default=calculate_space_to_provide,
		ignore=ignore_provider
	),
	inquirer.Text(
		name="traffic_cost",
		message=f"Сколько будет стоить 10 GB трафика сети",
		default=default_traffic_cost,
		ignore=ignore_tunnel
	)
]


args = parse_input_args()
answers = inquirer.prompt(questions)
utils = answers.pop("utils")
main.install(args, **answers)
if "TonStorage" in utils:
	ton_storage.install(args, **answers)
if "TonStorageProvider" in utils:
	ton_storage_provider.install(args, **answers)
if "TonTunnelProvider" in utils:
	ton_tunnel_provider.install(args, **answers)
#end if

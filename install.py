#!/usr/bin/env python3
# -*- coding: utf_8 -*-

from typing import Any
import inquirer
import sys
import os
#from sys import path as system_path
from mypylib import Dict, MyPyClass
from modules import main as main_module
from utils import (
	import_modules,
	get_modules_names,
	get_module_by_name,
	get_disk_free_space
)


local = MyPyClass(__file__)
local.db.config.logLevel = "debug"


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







def create_questions():
	questions = [
		inquirer.Checkbox(
			name="utils",
			message="Выберете утилиты",
			choices=get_modules_names(local)
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
	return questions
#end define

def main():
	# install_args: user, src_dir, bin_dir, venvs_dir, venv_path, src_path
	install_args = parse_input_args()
	questions = create_questions()
	answers = inquirer.prompt(questions)
	need_modules_names = answers.pop("utils")

	main_module.install(install_args, **answers)
	for need_module_name in need_modules_names:
		need_module = get_module_by_name(local, need_module_name)
		need_module.install(install_args, **answers)
#end define


# args = parse_input_args()
# answers = inquirer.prompt(questions)
# utils = answers.pop("utils")
# main.install(args, **answers)
# if "TonStorage" in utils:
# 	ton_storage.install(args, **answers)
# if "TonStorageProvider" in utils:
# 	ton_storage_provider.install(args, **answers)
# if "TonTunnelProvider" in utils:
# 	ton_tunnel_provider.install(args, **answers)
# #end if

if __name__ == "__main__":
	import_modules(local)
	main()
#end if

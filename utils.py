#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import shutil
import random
from string import digits, ascii_letters
from functools import lru_cache
from pathlib import Path
import importlib
from os import listdir
import sys
from mypylib import Dict
import subprocess


def get_disk_space(disk_path, decimal_size=3) -> int:
	# decimal_size: bytes=0, kilobytes=1, megabytes=2, gigabytes=3, terabytes=4
	total, used, free = shutil.disk_usage(disk_path)
	total_space = convert_to_required_decimal(total, decimal_size)
	used_space = convert_to_required_decimal(used, decimal_size)
	free_space = convert_to_required_decimal(free, decimal_size)
	return total_space, used_space, free_space
#end define

def convert_to_required_decimal(input_int, decimal_size=3, round_size=0):
	result_int = input_int /1024**decimal_size
	result = round(result_int, round_size)
	return result
#end define

def fix_git_config(git_path: str):
	args = ["git", "status"]
	try:
		process = subprocess.run(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=git_path, timeout=3)
		err = process.stderr.decode("utf-8")
	except Exception as e:
		err = str(e)
	if err:
		if 'git config --global --add safe.directory' in err:
			args = ["git", "config", "--global", "--add", "safe.directory", git_path]
			subprocess.run(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
		else:
			raise Exception(f'Failed to check git status: {err}')
# end define

@lru_cache
def get_package_path():
	cwd = str(Path(__file__).resolve())
	return cwd.split("mytonprovider")[0] + "mytonprovider"
#end define

def generate_login() -> str:
	return r''.join(random.choices(population=ascii_letters, k=10))
#end define

def generate_password() -> str:
	# punctuation = r"""!#$%&()*+,-./:;<=>?@[\]^_{|}~"""
	symbols = ascii_letters + digits #+ punctuation
	return r''.join(random.choices(population=symbols, k=10))
#end define

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

def reduct(text):
	if text is None:
		return
	if len(text) < 16:
		return text
	end = len(text)
	result = text[0:6] + "..." + text[end - 6:end]
	return result
#end define


###
### Для работы с модулями
###
def import_commands(local, console):
	for module in local.buffer.modules:
		method = getattr(module, "get_console_commands", None)
		if method == None:
			continue
		commands = module.get_console_commands()
		do_import_commands(console, commands)
#end define

def do_import_commands(console, commands):
	for command in commands:
		console.AddItem(command.cmd, command.func, command.desc)
#end define

def import_modules(local, check_is_enabled=False):
	local.buffer.modules = list()
	modules_dir = f"{local.buffer.my_dir}/modules"
	sys.path.append(modules_dir)
	modules_names = get_modules_names_from_dir(modules_dir)
	for module_name in modules_names:
		file_module = importlib.import_module(module_name)
		if "Module" not in file_module.__dict__:
			continue
		module = file_module.Module(local)
		if check_is_enabled and module.is_module_enabled() == False:
			continue
		local.buffer.modules.append(module)
#end define

def get_modules_names_from_dir(search_dir):
	modules_names = list()
	for item in listdir(search_dir):
		if not item.endswith(".py"):
			continue
		module_name, file_type = item.split('.')
		modules_names.append(module_name)
	modules_names.sort()
	return modules_names
#end define

def get_modules_names(local):
	result = list()
	for module in local.buffer.modules:
		module_name = getattr(module, "name", None)
		if module_name != None:
			result.append(module_name)
	return result
#end define

def get_module_by_name(local, input_module_name):
	for module in local.buffer.modules:
		module_name = getattr(module, "name", None)
		if module_name == input_module_name:
			return module
	raise Exception("get_module_by_name error: module not found")
#end define

def run_module_method_if_exist(local, module, method_name, *args, **kwargs):
	method = getattr(module, method_name, None)
	if method == None:
		return
	return method(*args, **kwargs)
#end define

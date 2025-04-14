import shutil
import random
from string import digits, ascii_letters
from functools import lru_cache
from pathlib import Path
import importlib
from os import listdir
import sys
from mypylib import Dict


def get_disk_free_space(disk_path) -> int:
	total, used, free = shutil.disk_usage(disk_path)
	free_megabytes = int(free /1024 /1024)
	return free_megabytes
#end define

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

def import_modules(local):
	local.buffer.modules = list()
	modules_dir = f"{local.buffer.my_dir}/modules"
	sys.path.append(modules_dir)
	modules_names = get_modules_names_from_dir(modules_dir)
	for module_name in modules_names:
		file_module = importlib.import_module(module_name)
		if "Module" not in file_module.__dict__:
			continue
		module = file_module.Module(local)
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

def run_module_method_if_exist(local, module_name, method_name, *args, **kwargs):
	module = get_module_by_name(local, module_name)
	method = getattr(module, method_name, None)
	if method == None:
		return
	return method(*args, **kwargs)
#end define

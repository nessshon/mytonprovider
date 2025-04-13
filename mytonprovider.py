# добавить alias в bashrc

import types

import importlib
from sys import path
from os import listdir
from mypylib import MyPyClass, Dict
from mypyconsole.mypyconsole import MyPyConsole


local = MyPyClass(__file__)
console = MyPyConsole()



def init():
	console.name = "MyTonProvider"
	#console.startFunction = None
	console.debug = True
	console.local = local

	import_console_modules()
	import_commands()
#end define

def import_commands():
	for console_module in local.buffer.console_modules:
		method = getattr(console_module, "get_console_commands", None)
		if type(method) != types.MethodType:
			continue
		commands = console_module.get_console_commands()
		do_import_commands(commands)
#end define

def do_import_commands(commands):
	for command in commands:
		console.AddItem(command.cmd, command.func, command.desc)
#end define

def import_console_modules():
	local.buffer.console_modules = list()
	modules_dir = f"{local.buffer.my_dir}/modules"
	path.append(modules_dir)
	modules_names = get_modules_names(modules_dir)
	for module_name in modules_names:
		module = importlib.import_module(module_name)
		if "ConsoleModule" not in module.__dict__:
			continue
		console_module = module.ConsoleModule(local)
		local.buffer.console_modules.append(console_module)
#end define

def get_modules_names(search_dir):
	modules_names = list()
	for item in listdir(search_dir):
		if not item.endswith(".py"):
			continue
		module_name, file_type = item.split('.')
		modules_names.append(module_name)
	return modules_names
#end define

def main():
	#console.AddItem("команда", func, "Название команды")
	console.AddItem("status", status, "Показать статус")
	console.Run()
#end define

def status(args):
	for console_module in local.buffer.console_modules:
		method = getattr(console_module, "status", None)
		#print(f"{console_module} --> {type(method)}")
		#if type(method) != types.MethodType:
		if method == None:
			continue
		console_module.status(args)
		print()
#end define



if __name__ == "__main__":
	init()
	main()
#end if

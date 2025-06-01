#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import sys
#import threading
from mypyconsole.mypyconsole import MyPyConsole
from mypylib import (
	MyPyClass,
	Dict,
	run_as_root,
	color_print,
	thr_sleep
)
from utils import (
	get_module_by_name,
	import_commands,
	import_modules,
	run_module_method_if_exist,
	init_localization
)


local = MyPyClass(__file__)
console = MyPyConsole()


def init():
	local.run()
	import_modules(local, check_is_enabled=True)
	init_localization(local)
	import_commands(local, console)
	
	if "--daemon" in sys.argv:
		init_daemon()
	else:
		init_console()
#end define

def init_daemon():
	#threading.current_thread().name = "daemon"
	for module in local.buffer.modules:
		method = getattr(module, "daemon", None)
		if method == None:
			continue
		cycle_name = f"{module.name}-daemon"
		local.start_cycle(module.daemon, name=cycle_name, sec=module.daemon_interval)
	thr_sleep()
#end define

def init_console():
	console.name = "MyTonProvider"
	console.start_function = pre_up
	#console.debug = True
	console.local = local

	console.add_item("status", status, local.translate("status_cmd"))
	console.add_item("update", update, local.translate("update_cmd"))
	console.add_item("upgrade", upgrade, local.translate("upgrade_cmd"))
	console.run()
#end define

def pre_up():
	for module in local.buffer.modules:
		run_module_method_if_exist(local, module, "check")
#end define

def status(args):
	count = 1
	for module in local.buffer.modules:
		method = getattr(module, "status", None)
		if method == None:
			continue
		module.status(args)
		if count < len(local.buffer.modules):
			count += 1
			print()
#end define

def update(args):
	user = os.getenv("USER")
	script_path = f"{local.buffer.my_dir}/scripts/update.sh"
	exit_code = run_as_root(["bash", script_path, "-d", local.buffer.venvs_dir])
	if exit_code == 0:
		text = "Update MyTonProvider - {green}OK{endc}"
	else:
		text = "Update MyTonProvider - {red}Error{endc}"
	color_print(text)
	local.exit()
#end define

def upgrade(args):
	try:
		module_name = args[0]
	except:
		color_print("{red}Bad args. Usage:{endc} upgrade <module-name>")
		return
	#end try

	module = get_module_by_name(local, module_name)
	upgrade_args = run_module_method_if_exist(local, module, "get_upgrade_args", src_path=local.buffer.my_dir)
	exit_code = run_as_root(upgrade_args)
	if exit_code == 0:
		text = f"Upgrade {module_name} - {{green}}OK{{endc}}"
	else:
		text = f"Upgrade {module_name} - {{red}}Error{{endc}}"
	color_print(text)
#end define



if __name__ == "__main__":
	init()
#end if

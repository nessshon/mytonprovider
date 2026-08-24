#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import sys
import json
import signal
import asyncio
from getpass import getuser
from itertools import islice
from contextlib import suppress

from ton_core import NetworkGlobalID, load_global_config
from tonutils.tools.status_monitor import DhtMonitor, LiteServerMonitor
from tonutils.types import DEFAULT_ADNL_RETRY_POLICY

from mypyconsole.mypyconsole import MyPyConsole
from mypylib import (
	MyPyClass,
	run_as_root,
	color_print,
	thr_sleep,
)
from utils import (
	get_modules,
	print_table,
	get_module_by_name,
	import_commands,
	import_modules,
	run_module_method_if_exist,
	init_localization,
	set_check_data,
	get_module_type,
	parse_github_url,
)


local = MyPyClass(__file__)
console = MyPyConsole()


def init():
	local.run()
	import_modules(local)
	init_localization(local)
	import_commands(local, console)
	
	if "--daemon" in sys.argv:
		init_daemon()
	else:
		init_console()
#end define

def init_daemon():
	main_module = get_module_by_name(local, "main")
	run_module_method_if_exist(local, main_module, "download_global_config")

	#threading.current_thread().name = "daemon"
	for module in get_modules(local):
		# Основной daemon
		method = getattr(module, "daemon", None)
		if method == None:
			continue
		cycle_name = f"{module.name}-daemon"
		local.start_cycle(module.daemon, name=cycle_name, sec=module.daemon_interval)

		# Дополнительные daemons
		extra_daemons = getattr(module, "extra_daemons", None)
		if extra_daemons == None:
			continue
		for extra_daemon in extra_daemons:
			local.start_cycle(extra_daemon.func, name=extra_daemon.name, sec=extra_daemon.interval)
	thr_sleep()
#end define

def init_console():
	console.name = "MyTonProvider"
	console.start_function = pre_up
	console.debug = local.db.debug or False
	console.local = local
	if console.debug == True:
		color_print("{red} Debug mode enabled {endc}")
	#end if

	console.add_item("status", status, local.translate("status_cmd"))
	console.add_item("update", update, local.translate("update_cmd"))
	console.add_item("get", get_settings, local.translate("get_cmd"))
	console.add_item("set", set_settings, local.translate("set_cmd"))
	console.add_item("modules_list", modules_list, local.translate("modules_list_cmd"))
	console.add_item("ls_status", ls_status, local.translate("ls_status_cmd"))
	console.add_item("dht_status", dht_status, local.translate("dht_status_cmd"))
	console.run()
#end define

def pre_up():
	modules = get_modules(local)
	for module in modules:
		run_module_method_if_exist(local, module, "pre_up")
#end define

def status(args):
	count = 1
	modules = get_modules(local)
	for module in modules:
		method = getattr(module, "status", None)
		if method == None:
			continue
		module.status(args)
		if count < len(modules):
			count += 1
			print()
#end define

def update(args):
	try:
		if len(args) < 1 or len(args) > 4:
			raise ValueError
		module_name = args[0]
		branch = next(islice(args, 1, None), None)
		author = next(islice(args, 2, None), None)
		repo = next(islice(args, 3, None), None)
	except:
		color_print("{red}Bad args. Usage:{endc} update <module-name> [<url>] | [<branch>] [<author>] [<repo>]")
		return
	# end try

	if branch is not None and "github.com" in branch:
		author, repo, branch = parse_github_url(branch)

	user = getuser()
	module = get_module_by_name(local, module_name)

	try:
		update_args = run_module_method_if_exist(
			local,
			module,
			"get_update_args",
			user=user,
			author=author,
			repo=repo,
			branch=branch,
			restart_service=True,
		)
	except Exception as e:
		color_print("{red}" + str(e) + "{endc}")
		return
	# end try

	# Запускаем команду обновления от root
	exit_code = run_as_root(update_args)
	if exit_code == 0:
		set_check_data(module, check_name="update", data=False)
		text = f"Update {module_name} - {{green}}OK{{endc}}"
	else:
		text = f"Update {module_name} - {{red}}Error{{endc}}"
	color_print(text)
	if module_name == "main":
		local.exit()
#end define

def get_settings(args):
	try:
		name = args[0]
	except:
		color_print("{red}Bad args. Usage:{endc} get <settings-name>")
		return
	result = local.db.get(name)
	print(json.dumps(result, indent=2))
#end defin

def set_settings(args):
	try:
		name = args[0]
		value = args[1]
	except:
		color_print("{red}Bad args. Usage:{endc} set <settings-name> <settings-value>")
		return
	data = json.loads(value)
	local.db[name] = data
	color_print("SetSettings - {green}OK{endc}")
#end define

def modules_list(args):
	table = [["Name", "Is enabled", "Mandatory", "Type"]]
	for module in get_modules(local, check_is_enabled=False):
		is_mandatory = getattr(module, "mandatory", False)
		if is_mandatory == True:
			is_enabled = ""
		else:
			is_enabled = run_module_method_if_exist(local, module, "is_enabled")
		module_type = get_module_type(module)
		table += [[module.name, is_enabled, is_mandatory, module_type]]
	print_table(table)
#end define

def ls_status(args):
	_run_status_monitor(LiteServerMonitor, network=NetworkGlobalID.MAINNET, retry_policy=DEFAULT_ADNL_RETRY_POLICY)
#end define

def dht_status(args):
	_run_status_monitor(DhtMonitor)
#end define

def _run_status_monitor(monitor_class, **kwargs):
	main_module = get_module_by_name(local, "main")
	config = load_global_config(main_module.global_config_path)
	monitor = monitor_class.from_config(config=config, **kwargs)

	async def _run():
		try:
			await monitor.run()
		finally:
			await monitor.stop()
	#end define

	old_handler = signal.signal(signal.SIGINT, signal.default_int_handler)
	try:
		with suppress(KeyboardInterrupt):
			asyncio.run(_run())
	finally:
		signal.signal(signal.SIGINT, old_handler)
#end define


if __name__ == "__main__":
	init()
#end if

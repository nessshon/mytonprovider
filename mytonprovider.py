# добавить alias в bashrc



from mypylib import MyPyClass, Dict, run_as_root, color_print
from mypyconsole.mypyconsole import MyPyConsole
from utils import (
	import_commands,
	import_modules,
	run_module_method_if_exist
)


local = MyPyClass(__file__)
console = MyPyConsole()



def init():
	console.name = "MyTonProvider"
	#console.startFunction = None
	#console.debug = True
	console.local = local

	import_modules(local)
	import_commands(local, console)
#end define



def main():
	#console.AddItem("команда", func, "Описание команды")
	console.AddItem("status", status, "Показать статус")
	console.AddItem("update", update, "Обновить MyTonProvider")
	console.AddItem("upgrade", upgrade, "Обновить модуль")
	console.Run()
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
	# https://github.com/ton-blockchain/mytonctrl/blob/e85a541b762f916a67c02ae83dbef6a2ce9121d7/mytonctrl/mytonctrl.py#L337
	script_path = f"{local.buffer.my_dir}/scripts/update.sh"
	exit_code = run_as_root(["bash", script_path])
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

	upgrade_args = run_module_method_if_exist(local, module_name, "get_upgrade_args", src_path=local.buffer.my_dir)
	exit_code = run_as_root(upgrade_args)
	if exit_code == 0:
		text = f"Upgrade {module_name} - {{green}}OK{{endc}}"
	else:
		text = f"Upgrade {module_name} - {{red}}Error{{endc}}"
	color_print(text)
#end define



if __name__ == "__main__":
	init()
	main()
#end if

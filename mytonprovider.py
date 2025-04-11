# добавить alias в bashrc

import requests
from mypylib import MyPyClass, Dict
from mypyconsole.mypyconsole import MyPyConsole

local = MyPyClass(__file__)
console = MyPyConsole()
console.name = "MyTonProvider"
#console.startFunction = None
#console.debug = None
console.local = local

def get_provider_api_data(port):
	local_api_url = f"http://127.0.0.1:{port}/api/v1/list"
	resp = requests.get(local_api_url, timeout=3)
	if resp.status_code != 200:
		raise Exception(f"Failed to get provider api data from {local_api_url}")
	return Dict(resp.json())
#end define

def status_cmd(args):
	# что то делаем
	data = get_provider_api_data(local.db.ton_storage.api.port)
	# print("какие то даные")
	print(data)
#end define

#console.AddItem("команда", func, "Название команды")
console.AddItem("status", status_cmd, "Показать статус")

console.Run()
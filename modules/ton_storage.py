#from utils import generate_login, generate_password, get_package_path

from random import randint
from mypylib import (
	Dict,
	MyPyClass,
	color_print,
	add2systemd,
	read_config_from_file,
	write_config_to_file,
	get_own_ip
)
import subprocess
import os
import requests


class ConsoleModule():
	def __init__(self, local):
		self.local = local
		self.local.add_log("ton_storage console module init done")
	#end define

	# def get_console_commands(self):
	# 	return list()
	# #end define

	def status(self, args):
		data = self.get_api_data()
		color_print("{cyan}===[ Local storage status ]==={endc}")
		print(f"Количество хранимых контейнеров: {data}")
		print(f"Пространство хранилища: занято/свободно")
	#end define

	def get_api_data(self):
		api = self.local.db.ton_storage.api
		api_url = f"http://{api.host}:{api.port}/api/v1/list"
		resp = requests.get(api_url, timeout=0.3)
		if resp.status_code != 200:
			raise Exception(f"Failed to get provider api data from {api_url}")
		return Dict(resp.json())
	#end define
#end class

def install(
		args: Dict,
		author="xssnick",
		repo="tonutils-storage",
		branch="master",
		entry_point="cli/main.go",
		storage_path: str = None,
		**kwargs
	):
	name = "ton-storage"
	host = "localhost"
	udp_port = randint(1024, 65000)
	api_port = randint(1024, 65000)
	#login = generate_login()
	#password = generate_password()

	mconfig_dir = f"/home/{args.user}/.local/share/mytonprovider"
	mconfig_path = f"{mconfig_dir}/mytonprovider.db"
	db_dir = f"{storage_path}/db"
	storage_config_path = f"{db_dir}/config.json"

	# Склонировать исходники и скомпилировать бинарники
	script_path = f"{args.src_path}/scripts/install_go_package.sh"
	subprocess.run([
		"bash",	script_path,
		"-a", author, "-r", repo, "-b", branch, "-e", entry_point
	])

	# Подготовить папку
	os.makedirs(storage_path, exist_ok=True)
	subprocess.run([
		"chown", "-R", 
		args.user + ':' + args.user, 
		storage_path
	])

	# Создать службу
	start_cmd = f"{args.bin_dir}/{repo} --daemon --db {db_dir} --api {host}:{api_port}" # --api-login {login} --api-password {password}
	add2systemd(name=name, user=args.user, start=start_cmd, workdir=storage_path, force=True)

	# Первый запуск - создание конфига
	local = MyPyClass(__file__)
	local.db.config.logLevel = "debug"
	local.start_service(name, sleep=10)
	local.stop_service(name)

	# read ton_storage config
	storage_config = read_config_from_file(storage_config_path)

	# prepare config
	storage_config.ListenAddr = f"0.0.0.0:{udp_port}"
	storage_config.ExternalIP = get_own_ip()

	# write ton_storage config
	write_config_to_file(config_path=storage_config_path, data=storage_config)

	# read mconfig
	mconfig = read_config_from_file(mconfig_path)

	# prepare config
	ton_storage = Dict()
	ton_storage.storage_path = storage_path
	#ton_storage.user = args.user
	#ton_storage.src_dir = args.src_dir
	#ton_storage.bin_dir = args.bin_dir
	#ton_storage.venvs_dir = args.venvs_dir
	#ton_storage.venv_path = args.venv_path
	#ton_storage.src_path = args.src_path

	api = Dict()
	api.host = host
	api.port = api_port
	#api.login = login
	#api.password = password
	
	ton_storage.api = api
	mconfig.ton_storage = ton_storage

	# Записать конфиг
	write_config_to_file(config_path=mconfig_path, data=mconfig)

	# start service
	local.start_service(name)
#end define

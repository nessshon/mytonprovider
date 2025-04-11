#from utils import generate_login, generate_password, get_package_path

from random import randint
from mypylib import (
	Dict,
	MyPyClass,
	add2systemd,
	read_config_from_file,
	write_config_to_file,
	get_own_ip
)
import subprocess
import os
import base64


def install(
		args: dict,
		author="xssnick",
		repo="tonutils-storage-provider",
		branch="master",
		entry_point="cmd/main.go",
		storage_path: str = None,
		storage_cost: int = None,
		space_to_provide_megabytes: int = None,
		**kwargs
	):
	name = "ton-storage-provider"
	host = "localhost"
	udp_port = randint(1024, 65000)
	#login = generate_login()
	#password = generate_password()

	mconfig_dir = f"/home/{args.user}/.local/share/mytonprovider"
	mconfig_path = f"{mconfig_dir}/mytonprovider.db"
	provider_path = f"{storage_path}/provider"
	db_dir = f"{provider_path}/db"
	config_path = f"{provider_path}/config.json"

	# Склонировать исходники и скомпилировать бинарники
	script_path = f"{args.src_path}/scripts/install_go_package.sh"
	subprocess.run([
		"bash", script_path,
		"-a", author, "-r", repo, "-b", branch, "-e", entry_point
	])

	# Подготовить папку
	os.makedirs(provider_path, exist_ok=True)
	subprocess.run([
		"chown", "-R", 
		args.user + ':' + args.user, 
		provider_path
	])

	# Создать службу
	start_cmd = f"{args.bin_dir}/{repo} --db {db_dir} --config {config_path}"
	add2systemd(name=name, user=args.user, start=start_cmd, workdir=provider_path, force=True)

	# Первый запуск - создание конфига
	local = MyPyClass(__file__)
	local.start_service(name, sleep=10)
	local.stop_service(name)

	# read mconfig
	mconfig = read_config_from_file(mconfig_path)

	# read ton-storage-provider config
	provider_config = read_config_from_file(config_path)

	# prepare config
	api = mconfig.ton_storage.api
	provider_config.ListenAddr = f"0.0.0.0:{udp_port}"
	provider_config.ExternalIP = get_own_ip()
	provider_config.MinRatePerMBDay = calulate_MinRatePerMBDay(storage_cost)
	provider_config.Storages[0].BaseURL = f"http://{api.host}:{api.port}"
	provider_config.Storages[0].SpaceToProvideMegabytes = int(space_to_provide_megabytes)
	provider_config.CRON.Enabled = True

	# write ton-storage-provider config
	write_config_to_file(config_path=config_path, data=provider_config)

	# get provider pubkey
	key_bytes = base64.b64decode(provider_config.ProviderKey)
	privkey_bytes = key_bytes[0:32]
	pubkey_bytes = key_bytes[32:64]

	# edit mytoncore config file
	provider = Dict()
	provider.udp_port = udp_port
	provider.config_path = config_path
	provider.privkey = base64.b64encode(privkey_bytes).decode("utf-8")
	provider.pubkey = pubkey_bytes.hex().upper()
	mconfig.ton_storage.provider = provider

	# write mconfig
	write_config_to_file(config_path=mconfig_path, data=mconfig)



	# Проверить что уже активировано (кошелек активен, зарегистрирован)



	# активировать кошелек



	# зарегаться в списке отправив транзакцию






	# start ton-storage-provider
	local.start_service(name)

#end define

def calulate_MinRatePerMBDay(storage_cost):
	data = int(storage_cost) /200 /1000 /30
	return f"{data:.9f}"
#end define

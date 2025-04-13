#from utils import generate_login, generate_password, get_package_path

import subprocess
import os
import base64
import tonutils
import tonutils.client
import tonutils.wallet
from random import randint
from asgiref.sync import async_to_sync

from mypylib import (
	Dict,
	MyPyClass,
	color_print,
	add2systemd,
	read_config_from_file,
	write_config_to_file,
	get_own_ip
)
from adnl_over_tcp import get_messages


#TonStorageProviderModule
class ConsoleModule():
	def __init__(self, local):
		self.local = local
		self.local.add_log("ton_storage_provider console module init done")
	#end define

	def get_console_commands(self):
		commands = list()
		register_item = Dict()
		register_item.cmd = "register"
		register_item.func = self.register
		register_item.desc = "Послать сообщение в список провайдеров"

		commands.append(register_item)
		return commands
	#end define

	@async_to_sync
	async def register(self, args):
		self.local.add_log("start register function")
		wallet = await self.get_provider_wallet()
		# print("wallet.addr:", wallet.addr)
		# print("wallet.status:", wallet.status)
		# print("wallet.balance:", wallet.balance)

		# Проверить что кошелек активен
		if (wallet.status == "uninit" and wallet.balance > 0.003):
			await self.do_deploy(wallet)
		#end if

		# Зарегистрироваться в списке отправив транзакцию
		destination = "0:7777777777777777777777777777777777777777777777777777777777777777"
		comment = f"tsp-{self.local.db.ton_storage.provider.pubkey.lower()}"
		messages = await get_messages(destination, 100)
		if self.is_already_registered(messages, wallet.addr, comment):
			color_print("{green}Provider wallet already registered{endc}")
		else:
			await self.do_register(wallet, destination, comment)
	#end define

	async def do_deploy(self, wallet):
		msg_hash = await wallet.obj.deploy()
		print("deploy msg_hash:", msg_hash)
	#end define

	async def do_register(self, wallet, destination, comment):
		self.local.add_log("start do_register function", "debug")
		msg_hash = await wallet.obj.transfer(
			destination = destination, 
			amount = 0.01, 
			body = comment
		)
		print("transfer msg_hash:", msg_hash)
		self.wait_complet(destination, msg_hash)
	#end define

	def wait_complet(addr, msg_hash):
		print("wait_complet TODO")
	#end define

	async def get_provider_wallet(self):
		provider = self.local.db.ton_storage.provider
		client = tonutils.client.LiteserverClient(is_testnet=True)
		private_key = base64.b64decode(provider.privkey)
		wallet = Dict()
		wallet.obj = tonutils.wallet.WalletV3R2.from_private_key(client, private_key)
		wallet.addr = wallet.obj.address.to_str()
		wallet.account = await client.get_raw_account(wallet.addr)
		wallet.status = wallet.account.status.value
		wallet.balance = wallet.account.balance /10**9
		return wallet
	#end define

	def is_already_registered(self, messages, src, comment):
		for message in messages:
			#print(f"{message.src} --> {message.comment}")
			if (message.src == src and message.comment == comment):
				return True
		return False
	#end define

	@async_to_sync
	async def status(self, args):
		provider = self.local.db.ton_storage.provider
		wallet = await self.get_provider_wallet()
		color_print("{cyan}===[ Local provider status ]==={endc}")
		print(f"Публичный ключ провайдера: {provider.pubkey}")
		print(f"Кошелек провайдера: {wallet.addr}")
		print(f"Баланс кошелька провайдера: {wallet.balance}")
		print(f"Пространство провайдера: занято/свободно")
	#end define
#end class



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

	# start ton-storage-provider
	local.start_service(name)

#end define

def calulate_MinRatePerMBDay(storage_cost):
	data = int(storage_cost) /200 /1000 /30
	return f"{data:.9f}"
#end define

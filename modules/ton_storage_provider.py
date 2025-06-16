#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import base64
import subprocess
import tonutils
import tonutils.client
import tonutils.wallet
from random import randint
from asgiref.sync import async_to_sync

from mypylib import (
	Dict,
	bcolors,
	MyPyClass,
	color_print,
	add2systemd,
	read_config_from_file,
	write_config_to_file,
	get_own_ip,
	get_git_hash,
	get_git_branch
)
from adnl_over_tcp import get_messages
from utils import (
	get_module_by_name,
	convert_to_required_decimal,
	fix_git_config
)
from decorators import publick
from adnl_over_udp_checker import check_adnl_connection
from addr_and_key import (
	addr_to_bytes,
	get_pubkey_from_privkey,
	split_provider_key
)


class Module():
	def __init__(self, local):
		self.name = "ton-storage-provider"
		self.local = local
		self.mandatory = False
		self.local.add_log(f"{self.name} module init done", "debug")

		self.go_package = Dict()
		self.go_package.author = "xssnick"
		self.go_package.repo = "tonutils-storage-provider"
		self.go_package.branch = "master"
		self.go_package.entry_point = "cmd/main.go"
	#end define

	@publick
	def is_enabled(self):
		if "ton_storage" in self.local.db:
			if "provider" in self.local.db.ton_storage:
				return True
		return False
	#end define

	@publick
	def get_console_commands(self):
		commands = list()

		register = Dict()
		register.cmd = "register"
		register.func = self.register
		register.desc = self.local.translate("register_cmd")
		commands.append(register)

		import_wallet = Dict()
		import_wallet.cmd = "import_wallet"
		import_wallet.func = self.import_wallet
		import_wallet.desc = self.local.translate("import_wallet_cmd")
		commands.append(import_wallet)

		export_wallet = Dict()
		export_wallet.cmd = "export_wallet"
		export_wallet.func = self.export_wallet
		export_wallet.desc = self.local.translate("export_wallet_cmd")
		commands.append(export_wallet)

		return commands
	#end define

	@publick
	def check(self):
		adnl_pubkey = self.get_adnl_pubkey()
		provider_config = self.get_provider_config()
		listen_ip, provider_port = provider_config.ListenAddr.split(':')
		
		own_ip = get_own_ip()
		if provider_config.ExternalIP != own_ip:
			raise Exception("provider_config.ExternalIP != own_ip")
		ok, error = check_adnl_connection(own_ip, provider_port, adnl_pubkey)
		if not ok:
			color_print(f"{{red}}{error}{{endc}}")
	#end define

	@publick
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
		provider_pubkey = self.get_provider_pubkey()
		comment = f"tsp-{provider_pubkey.lower()}"
		messages = await get_messages(destination, 100)
		if self.is_already_registered(messages, wallet.addr, comment):
			text = self.local.translate("provider_already_registered")
			text = bcolors.green_text(text)
			print(text)
		else:
			await self.do_register(wallet, destination, comment)
	#end define

	async def do_deploy(self, wallet):
		msg_hash = await wallet.obj.deploy()
		print("deploy msg_hash:", msg_hash)
		self.wait_complet(wallet.addr, msg_hash)
	#end define

	async def do_register(self, wallet, destination, comment):
		self.local.add_log("start do_register function", "debug")
		msg_hash = await wallet.obj.transfer(
			destination = destination, 
			amount = 0.01, 
			body = comment
		)
		print("transfer msg_hash:", msg_hash)
		self.wait_complet(wallet.addr, msg_hash)
	#end define

	def wait_complet(self, addr, msg_hash):
		print("wait_complet TODO")
	#end define

	async def get_provider_wallet(self):
		provider_config = self.get_provider_config()
		client = tonutils.client.LiteserverClient(is_testnet=False)
		private_key = base64.b64decode(provider_config.ProviderKey)
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

	def get_adnl_pubkey(self):
		provider_config = self.get_provider_config()
		adnl_bytes = base64.b64decode(provider_config.ADNLKey)
		adnl_pubkey_bytes = adnl_bytes[32:64]
		adnl_pubkey = adnl_pubkey_bytes.hex().upper()
		return adnl_pubkey
	#end define

	def get_provider_pubkey(self):
		provider_config = self.get_provider_config()
		provider_bytes = base64.b64decode(provider_config.ProviderKey)
		provider_pubkey_bytes = provider_bytes[32:64]
		provider_pubkey = provider_pubkey_bytes.hex().upper()
		return provider_pubkey
	#end define

	def get_provider_maxbagsize(self):
		provider_config = self.get_provider_config()
		return provider_config.MaxBagSizeBytes
	#end define

	@publick
	@async_to_sync
	async def import_wallet(self, args):
		try:
			key = args[0]
		except:
			color_print("{red}Bad args. Usage:{endc} import_wallet <wallet-private-key>")
			return
		self.do_import_wallet(key)
		color_print("import_wallet - {green}OK{endc}")
	#end define

	def do_import_wallet(self, privkey):
		privkey_bytes = base64.b64decode(privkey)
		pubkey_bytes = get_pubkey_from_privkey(privkey_bytes)
		provider_key_bytes = privkey_bytes + pubkey_bytes

		provider_config = self.get_provider_config()
		provider_config.ProviderKey = base64.b64encode(provider_key_bytes).decode("utf-8")
		self.set_provider_config(provider_config)

		#self.local.db.ton_storage.provider.pubkey = pubkey_bytes.hex().upper()
	#end define

	@publick
	@async_to_sync
	async def export_wallet(self, args):
		provider_config = self.get_provider_config()
		key_b64 = provider_config.ProviderKey
		privkey, pubkey = split_provider_key(key_b64)
		privkey_b64 = base64.b64encode(privkey).decode("utf-8")
		wallet = await self.get_provider_wallet()

		print("Address:", wallet.addr)
		print("Private key:", privkey_b64)
	#end define

	@publick
	@async_to_sync
	async def status(self, args):
		color_print("{cyan}===[ Local provider status ]==={endc}")
		self.print_module_name()
		self.print_provider_pubkey()
		await self.print_provider_wallet()
		self.print_storage_cost()
		self.print_profit()
		self.print_provider_space()
		self.print_git_hash()
	#end define

	def print_module_name(self):
		module_name = bcolors.yellow_text(self.name)
		text = self.local.translate("module_name").format(module_name)
		print(text)
	#end define

	def print_provider_pubkey(self):
		provider_pubkey = self.get_provider_pubkey()
		provider_pubkey_text = bcolors.yellow_text(provider_pubkey)
		text = self.local.translate("provider_pubkey").format(provider_pubkey_text)
		print(text)
	#end define

	async def print_provider_wallet(self):
		wallet = await self.get_provider_wallet()
		addr = bcolors.yellow_text(wallet.addr)
		balance = bcolors.green_text(wallet.balance)
		addr_text = self.local.translate("provider_wallet").format(addr)
		balance_text = self.local.translate("provider_balance").format(balance)
		print(addr_text)
		print(balance_text)
	#end define

	def print_storage_cost(self):
		storage_cost = self.get_storage_cost()
		storage_cost_text = bcolors.yellow_text(storage_cost)
		text = self.local.translate("storage_cost").format(storage_cost_text)
		print(text)
	#end define

	def print_profit(self):
		real_profit, maximum_profit = self.get_profit()
		real_profit_text = bcolors.green_text(real_profit)
		max_profit_text = bcolors.yellow_text(maximum_profit)
		text = self.local.translate("provider_profit").format(real_profit_text, max_profit_text)
		print(text)
	#end define

	def print_provider_space(self):
		used_provider_space = self.get_used_provider_space(decimal_size=3, round_size=2)
		total_provider_space = self.get_total_provider_space(decimal_size=3, round_size=2)
		used_provider_space_text = bcolors.green_text(used_provider_space) # TODO
		total_provider_space_text = bcolors.yellow_text(total_provider_space)
		text = self.local.translate("provider_space").format(used_provider_space_text, total_provider_space_text)
		print(text)
	#end define

	def print_git_hash(self):
		git_hash, git_branch = self.get_my_git_hash_and_branch()
		git_hash_text = bcolors.yellow_text(git_hash)
		git_branch_text = bcolors.yellow_text(git_branch)
		text = self.local.translate("git_hash").format(git_hash_text, git_branch_text)
		print(text)
	#end define

	def get_used_provider_space(self, decimal_size, round_size):
		ton_storage_module = get_module_by_name(self.local, "ton-storage")
		api_data = ton_storage_module.get_api_data()
		used_provider_space = ton_storage_module.get_bags_size(api_data, decimal_size, round_size)
		return used_provider_space
	#end define

	def get_total_provider_space(self, decimal_size, round_size):
		# decimal_size: bytes=0, kilobytes=1, megabytes=2, gigabytes=3, terabytes=4
		provider_config = self.get_provider_config()
		result_megabytes = provider_config.Storages[0].SpaceToProvideMegabytes
		result_int = result_megabytes *1024**2
		result = convert_to_required_decimal(result_int, decimal_size, round_size)
		return result
	#end define

	def get_provider_config(self):
		provider = self.local.db.ton_storage.provider
		return read_config_from_file(provider.config_path)
	#en define

	def set_provider_config(self, provider_config):
		provider = self.local.db.ton_storage.provider
		write_config_to_file(config_path=provider.config_path, data=provider_config)
	#en define

	@publick
	def get_my_git_hash_and_branch(self):
		provider = self.local.db.ton_storage.provider
		git_path = f"{provider.src_dir}/{self.go_package.repo}"
		fix_git_config(git_path)
		git_hash = get_git_hash(git_path, short=True)
		git_branch = get_git_branch(git_path)
		return git_hash, git_branch
	#end define

	def get_storage_cost(self):
		# 1_mb_per_day --> 200_gb_per_month
		provider_config = self.get_provider_config()
		min_rate_per_mb_day = float(provider_config.MinRatePerMBDay)
		storage_cost = min_rate_per_mb_day *200 *1024 *30
		return round(storage_cost, 2)
	#end define

	def get_profit(self):
		provider_config = self.get_provider_config()
		used_provider_space = self.get_used_provider_space(decimal_size=2, round_size=0)
		total_provider_space = self.get_total_provider_space(decimal_size=2, round_size=0)
		min_rate_per_mb_day = float(provider_config.MinRatePerMBDay)
		real_profit = round(used_provider_space * min_rate_per_mb_day *30, 2)
		maximum_profit = round(total_provider_space * min_rate_per_mb_day *30, 2)
		return real_profit, maximum_profit
	#end define

	@publick
	def get_upgrade_args(self, src_path):
		script_path = f"{src_path}/scripts/install_go_package.sh"
		upgrade_args = [
			"bash",	script_path, 
			"-a", self.go_package.author, 
			"-r", self.go_package.repo, 
			"-b", self.go_package.branch, 
			"-e", self.go_package.entry_point
		]
		return upgrade_args
	#end define

	def install(
			self,
			install_args: dict,
			storage_path: str = None,
			storage_cost: int = None,
			space_to_provide_gigabytes: int = None,
			**kwargs
		):
		# install_args: user, src_dir, bin_dir, venvs_dir, venv_path, src_path
		udp_port = randint(1024, 65000)

		mconfig_dir = f"/home/{install_args.user}/.local/share/mytonprovider"
		mconfig_path = f"{mconfig_dir}/mytonprovider.db"
		provider_path = f"{storage_path}/provider"
		db_dir = f"{provider_path}/db"
		provider_config_path = f"{provider_path}/config.json"
		provider_config_path

		# Склонировать исходники и скомпилировать бинарники
		upgrade_args = self.get_upgrade_args(install_args.src_path)
		subprocess.run(upgrade_args)

		# Подготовить папку
		os.makedirs(provider_path, exist_ok=True)
		subprocess.run([
			"chown", "-R", 
			install_args.user + ':' + install_args.user, 
			provider_path
		])

		# Создать службу
		start_cmd = f"{install_args.bin_dir}/{self.go_package.repo} --db {db_dir} --config {provider_config_path}"
		add2systemd(name=self.name, user=install_args.user, start=start_cmd, workdir=provider_path, force=True)

		# Первый запуск - создание конфига
		self.local.start_service(self.name, sleep=10)
		self.local.stop_service(self.name)

		# read mconfig
		mconfig = read_config_from_file(mconfig_path)

		# read provider config
		provider_config = read_config_from_file(provider_config_path)

		# edit provider config
		api = mconfig.ton_storage.api
		provider_config.ListenAddr = f"0.0.0.0:{udp_port}"
		provider_config.ExternalIP = get_own_ip()
		provider_config.MinSpan = 3600 *24 *7
		provider_config.MaxSpan = 3600 *24 *30
		provider_config.MinRatePerMBDay = self.calulate_MinRatePerMBDay(storage_cost)
		provider_config.MaxBagSizeBytes = provider_config.MaxBagSizeBytes *100
		provider_config.Storages[0].BaseURL = f"http://{api.host}:{api.port}"
		provider_config.Storages[0].SpaceToProvideMegabytes = self.calculate_space_to_provide(space_to_provide_gigabytes)
		provider_config.CRON.Enabled = True

		# write provider config
		write_config_to_file(config_path=provider_config_path, data=provider_config)

		# get provider pubkey
		#key_bytes = base64.b64decode(provider_config.ProviderKey)
		#privkey_bytes = key_bytes[0:32]
		#pubkey_bytes = key_bytes[32:64]

		# edit mytoncore config
		provider = Dict()
		provider.config_path = provider_config_path
		#provider.pubkey = pubkey_bytes.hex().upper()
		provider.src_dir = install_args.src_dir
		mconfig.ton_storage.provider = provider

		# write mconfig
		write_config_to_file(config_path=mconfig_path, data=mconfig)

		# start provider
		self.local.start_service(self.name)

	#end define

	def calculate_space_to_provide(self, input_space):
		# convert gigabytes to megabytes
		input_space_int = int(input_space)
		result_int = input_space_int*1024
		result = int(result_int)
		return result
	#end define

	def calulate_MinRatePerMBDay(self, storage_cost):
		# 200_gb_per_month --> 1_mb_per_day
		data = int(storage_cost) /200 /1024 /30
		return f"{data:.9f}"
	#end define
#end class

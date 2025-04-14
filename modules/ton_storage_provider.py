#!/usr/bin/env python3
# -*- coding: utf_8 -*-

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
	get_own_ip,
	get_git_hash,
	get_git_branch
)
from adnl_over_tcp import get_messages
from utils import get_module_by_name, convert_to_required_decimal, fix_git_config



class Module():
	def __init__(self, local):
		self.name = "ton-storage-provider"
		self.local = local
		self.local.add_log("ton_storage_provider console module init done")

		self.go_package = Dict()
		self.go_package.author = "xssnick"
		self.go_package.repo = "tonutils-storage-provider"
		self.go_package.branch = "master"
		self.go_package.entry_point = "cmd/main.go"
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

	def wait_complet(addr, msg_hash):
		print("wait_complet TODO")
	#end define

	async def get_provider_wallet(self):
		#provider = self.local.db.ton_storage.provider
		provider_config = self.get_provider_config()
		client = tonutils.client.LiteserverClient(is_testnet=True)
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

	@async_to_sync
	async def status(self, args):
		provider = self.local.db.ton_storage.provider
		wallet = await self.get_provider_wallet()
		storage_cost = self.get_storage_cost()
		maximum_profit = self.get_maximum_profit()
		ton_storage_module = get_module_by_name(self.local, "ton-storage")
		api_data = ton_storage_module.get_api_data()
		used_provider_space = ton_storage_module.get_bags_size(api_data)
		total_provider_space = self.get_total_provider_space()
		git_hash, git_branch = self.get_my_git_hash_and_branch()
		color_print("{cyan}===[ Local provider status ]==={endc}")
		print(f"Название модуля: {self.name}")
		print(f"Публичный ключ провайдера: {provider.pubkey}")
		print(f"Адрес кошелька провайдера: {wallet.addr}")
		print(f"Баланс кошелька провайдера: {wallet.balance}")
		print(f"Цена хранения за 200 GB в месяц: {storage_cost} TON")
		print(f"Максимальный профит в месяц: {maximum_profit} TON")
		
		print(f"Пространство провайдера: {used_provider_space} /{total_provider_space} GB")
		print(f"Версия провайдера: {git_hash} ({git_branch})")
	#end define

	def get_total_provider_space(self, decimal_size=3):
		# decimal_size: bytes=0, kilobytes=1, megabytes=2, gigabytes=3, terabytes=4
		provider_config = self.get_provider_config()
		result_megabytes = provider_config.Storages[0].SpaceToProvideMegabytes
		result_int = result_megabytes *1024**2
		result = convert_to_required_decimal(result_int, decimal_size)
		return result
	#end define

	def get_provider_config(self):
		provider = self.local.db.ton_storage.provider
		return read_config_from_file(provider.config_path)
	#en define

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

	def get_maximum_profit(self):
		provider_config = self.get_provider_config()
		total_provider_space = self.get_total_provider_space(decimal_size=2)
		min_rate_per_mb_day = float(provider_config.MinRatePerMBDay)
		maximum_profit = round(total_provider_space * min_rate_per_mb_day, 2)
		return maximum_profit
	#end define

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
		config_path = f"{provider_path}/config.json"

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
		start_cmd = f"{install_args.bin_dir}/{self.go_package.repo} --db {db_dir} --config {config_path}"
		add2systemd(name=self.name, user=install_args.user, start=start_cmd, workdir=provider_path, force=True)

		# Первый запуск - создание конфига
		self.local.start_service(self.name, sleep=10)
		self.local.stop_service(self.name)

		# read mconfig
		mconfig = read_config_from_file(mconfig_path)

		# read ton-storage-provider config
		provider_config = read_config_from_file(config_path)

		# prepare config
		api = mconfig.ton_storage.api
		provider_config.ListenAddr = f"0.0.0.0:{udp_port}"
		provider_config.ExternalIP = get_own_ip()
		provider_config.MinRatePerMBDay = self.calulate_MinRatePerMBDay(storage_cost)
		provider_config.Storages[0].BaseURL = f"http://{api.host}:{api.port}"
		provider_config.Storages[0].SpaceToProvideMegabytes = self.calculate_space_to_provide(space_to_provide_gigabytes)
		provider_config.CRON.Enabled = True

		# write ton-storage-provider config
		write_config_to_file(config_path=config_path, data=provider_config)

		# get provider pubkey
		key_bytes = base64.b64decode(provider_config.ProviderKey)
		#privkey_bytes = key_bytes[0:32]
		pubkey_bytes = key_bytes[32:64]

		# edit mytoncore config file
		provider = Dict()
		provider.udp_port = udp_port
		provider.config_path = config_path
		#provider.privkey = base64.b64encode(privkey_bytes).decode("utf-8")
		provider.pubkey = pubkey_bytes.hex().upper()
		provider.src_dir = install_args.src_dir
		mconfig.ton_storage.provider = provider

		# write mconfig
		write_config_to_file(config_path=mconfig_path, data=mconfig)

		# start ton-storage-provider
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

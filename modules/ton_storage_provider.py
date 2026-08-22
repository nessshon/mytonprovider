#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import base64

import inquirer
from random import randint
from asgiref.sync import async_to_sync

from rich.text import Text
from ton_core import PrivateKey, to_nano, to_amount
from tonutils.contracts import WalletV3R2

from mypylib import (
	Dict,
	color_print,
	add2systemd,
	read_config_from_file,
	write_config_to_file,
	get_own_ip,
	get_git_hash,
	get_git_branch,
	get_service_status,
	get_service_uptime,
	time2human,
	check_git_update,
	get_git_author_and_repo,
)
from adnl_over_tcp import (
	get_lite_balancer,
	wait_message,
	resolve_address,
)
from utils import (
	get_module_by_name,
	convert_to_required_decimal,
	format_bytes_pair,
	fix_git_config,
	get_service_status_color,
	get_check_port_status,
	set_check_data,
	get_check_update_status,
	run_subprocess,
	validate_github_repo,
	print_panel,
)
from decorators import publick
from adnl_over_udp_checker import check_adnl_connection


class Module():
	def __init__(self, local):
		self.name = "ton-storage-provider"
		self.service_name = self.name
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
		git_path = self.get_my_git_path()
		try:
			get_git_branch(git_path)
			return True
		except:
			return False
	#end define
	
	def is_enabled_old(self):
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

		wallet_transfer = Dict()
		wallet_transfer.cmd = "wallet_transfer"
		wallet_transfer.func = self.wallet_transfer
		wallet_transfer.desc = self.local.translate("wallet_transfer_cmd")
		commands.append(wallet_transfer)

		return commands
	#end define

	@publick
	def pre_up(self):
		self.local.start_thread(self.check_update)
		self.local.start_thread(self.check_port)
	#end define

	def check_update(self):
		git_path = self.get_my_git_path()
		is_update_available = check_git_update(git_path)
		set_check_data(module=self, check_name="update", data=is_update_available)
	#end define

	def check_port(self):
		adnl_pubkey = self.get_adnl_pubkey()
		provider_config = self.get_provider_config()
		listen_ip, provider_port = provider_config.ListenAddr.split(':')
		
		own_ip = get_own_ip()
		if provider_config.ExternalIP != own_ip:
			raise Exception("provider_config.ExternalIP != own_ip")
		result, status = check_adnl_connection(own_ip, provider_port, adnl_pubkey)
		set_check_data(module=self, check_name="port", data=result)
	#end define

	@publick
	@async_to_sync
	async def register(self, args):
		self.local.add_log("start register function")
		if self.local.db.ton_storage.provider.is_already_registered and "--force" not in args:
			text = self.local.translate("provider_already_registered")
			color_print(f"{{green}}{text}{{endc}}")
			return
		#end define
		async with get_lite_balancer(self.local) as client:
			wallet = await self.get_provider_wallet(client)
			if wallet.balance < to_nano(0.03):
				text = self.local.translate("low_provider_balance")
				color_print(f"{{red}}{text}{{endc}}")
				return
			#end if
			await self.do_register(client, wallet)
		color_print("{green}provider regiser - OK{endc}")
	#end define

	async def do_register(self, client, wallet):
		self.local.add_log("start do_register function", "debug")
		provider_pubkey = self.get_provider_pubkey()
		end_hash = wallet.last_transaction_hash
		end_lt = wallet.last_transaction_lt
		msg = await wallet.transfer(
			destination="0:7777777777777777777777777777777777777777777777777777777777777777",
			body=f"tsp-{provider_pubkey.lower()}",
			amount=to_nano(0.01),
		)
		await wait_message(client, wallet, msg.normalized_hash, end_lt, end_hash)
		self.local.db.ton_storage.provider.is_already_registered = True
	#end define

	async def get_provider_wallet(self, client):
		private_key = PrivateKey(self.get_provider_config().ProviderKey)
		wallet = WalletV3R2.from_private_key(client, private_key)
		await wallet.refresh()
		return wallet
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
		private_key = PrivateKey(privkey)
		provider_config = self.get_provider_config()
		provider_config.ProviderKey = private_key.keypair.as_b64
		self.set_provider_config(provider_config)
	#end define

	@publick
	@async_to_sync
	async def export_wallet(self, args):
		async with get_lite_balancer(self.local) as client:
			wallet = await self.get_provider_wallet(client)
		print("Address:", wallet.address.to_str(is_bounceable=False))
		print("Private key (hex):", wallet.private_key.as_hex)
		print("Private key (b64):", wallet.private_key.as_b64)
	#end define

	@publick
	@async_to_sync
	async def wallet_transfer(self, args):
		try:
			destination = args[0]
			amount = to_nano(float(args[1]))
			body = " ".join(args[2:]) if len(args) > 2 else None
		except:
			color_print("{red}Bad args. Usage:{endc} wallet_transfer <address/domain> <amount> [<comment>]")
			return
		#end try

		async with get_lite_balancer(self.local) as client:
			destination = await resolve_address(client, destination)
			wallet = await self.get_provider_wallet(client)
			need_amount = amount + to_nano(0.005)  # gas fee
			if wallet.balance < need_amount:
				text = self.local.translate("not_enough_balance").format(to_amount(wallet.balance), to_amount(need_amount))
				raise Exception(text)
			if wallet.balance - need_amount < to_nano(0.2):
				text = self.local.translate("low_balance_warning")
				color_print(f"{{yellow}}{text}{{endc}}")
			#end if

			question = self.local.translate("confirm_transfer").format(to_amount(amount), destination.to_str(is_bounceable=False))
			if not inquirer.confirm(question, default=False):
				color_print("wallet_transfer - {yellow}Canceled{endc}")
				return
			#end if

			end_lt = wallet.last_transaction_lt
			end_hash = wallet.last_transaction_hash
			msg = await wallet.transfer(destination, amount, body)
			await wait_message(client, wallet, msg.normalized_hash, end_lt, end_hash)
		color_print("wallet_transfer - {green}OK{endc}")
	#end define

	@publick
	@async_to_sync
	async def status(self, args):
		async with get_lite_balancer(self.local) as client:
			wallet = await self.get_provider_wallet(client)
		body = [
			self.print_provider_pubkey(),
			self.print_provider_wallet(wallet),
			self.print_provider_balance(wallet),
			self.print_storage_cost(),
			self.print_profit(),
			self.print_provider_space(),
			self.print_port_status(),
			self.print_git_hash(),
		]
		header = self.print_module_name()
		footer = self.print_service_status()
		print_panel(body, header, footer)
	#end define

	def print_module_name(self):
		return Text(self.name, style="cyan")
	#end define

	def print_provider_pubkey(self):
		provider_pubkey = self.get_provider_pubkey()
		field = self.local.translate("provider_pubkey")
		value = Text(provider_pubkey, style="yellow")
		return field, value
	#end define

	def print_provider_wallet(self, wallet):
		field = self.local.translate("provider_wallet")
		value = Text(wallet.address.to_str(is_bounceable=False), style="cyan")
		return field, value
	#end define

	def print_provider_balance(self, wallet):
		field = self.local.translate("provider_balance")
		value = Text(f"{to_amount(wallet.balance)} GRAM", style="green")
		return field, value
	#end define

	def print_storage_cost(self):
		storage_cost = self.get_storage_cost()
		field = self.local.translate("storage_cost")
		value = Text(f"{storage_cost} GRAM", style="yellow")
		return field, value
	#end define

	def print_profit(self):
		real_profit, maximum_profit = self.get_profit()
		real_profit_text = Text(str(real_profit), style="green")
		max_profit_text = Text(f"{maximum_profit} GRAM", style="yellow")
		field = self.local.translate("provider_profit")
		value = Text.assemble(real_profit_text, " / ", max_profit_text)
		return field, value
	#end define

	def print_provider_space(self):
		used_provider_space = self.get_used_provider_space(decimal_size=0, round_size=0)
		total_provider_space = self.get_total_provider_space(decimal_size=0, round_size=0)
		used_provider_space, total_provider_space = format_bytes_pair(used_provider_space, total_provider_space)
		used_provider_space_text = Text(used_provider_space, style="green")
		total_provider_space_text = Text(total_provider_space, style="yellow")
		field = self.local.translate("provider_space")
		value = Text.assemble(used_provider_space_text, " / ", total_provider_space_text)
		return field, value
	#end define

	def print_port_status(self):
		provider_config = self.get_provider_config()
		listen_ip, provider_port = provider_config.ListenAddr.split(':')
		port_color = Text(f"{provider_port} udp", style="yellow")
		status = get_check_port_status(module=self)
		field = self.local.translate("port_status")
		value = Text.assemble(port_color, ", ", status)
		return field, value
	#end define

	def print_service_status(self):
		service_status = get_service_status(self.service_name)
		service_uptime = get_service_uptime(self.service_name)
		service_status_color = get_service_status_color(service_status)
		service_uptime_color = Text(time2human(service_uptime), style="green")
		return Text.assemble(service_status_color, ", ", service_uptime_color)
	#end define

	def print_git_hash(self):
		git_hash, git_branch = self.get_my_git_hash_and_branch()
		git_hash_text = Text(git_hash, style="yellow")
		git_branch_text = Text(f"({git_branch})", style="yellow")
		update_status = get_check_update_status(module=self)
		field = self.local.translate("git_hash")
		parts = [git_hash_text, " ", git_branch_text]
		if update_status:
			parts.append(", ")
			parts.append(update_status)
		value = Text.assemble(*parts)
		return field, value
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

	def get_my_git_hash_and_branch(self):
		git_path = self.get_my_git_path()
		git_hash = get_git_hash(git_path, short=True)
		git_branch = get_git_branch(git_path)
		return git_hash, git_branch
	#end define

	def get_my_git_path(self):
		#provider = self.local.db.ton_storage.provider
		#git_path = f"{provider.src_dir}/{self.go_package.repo}"
		git_path = f"/usr/src/{self.go_package.repo}"
		fix_git_config(git_path)
		return git_path
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
	def get_update_args(self, user=None, author=None, repo=None,  branch=None, restart_service=False, **kwargs):
		# Temporarily. Delete in TODO
		if self.local.db.ton_storage != None:
			provider_config = self.get_provider_config()
			provider_config.MaxSpan = self.calculate_MaxSpan(self.get_storage_cost())
			self.set_provider_config(provider_config)
		#end if

		try:
			git_path = self.get_my_git_path()
			curr_branch = get_git_branch(git_path)
			curr_author, curr_repo = get_git_author_and_repo(git_path)
		except Exception:
			curr_author = curr_repo = curr_branch = None
		#end try

		author = author or curr_author or self.go_package.author
		repo = repo or curr_repo or self.go_package.repo
		branch = branch or curr_branch or self.go_package.branch
		validate_github_repo(author, repo, branch)

		script_path = f"{self.local.buffer.my_dir}/scripts/install_go_package.sh"
		update_args = ["bash",	script_path, "-a", author, "-r", repo, "-b", branch, "-e", self.go_package.entry_point]
		if restart_service == True:
			update_args += ["-s", self.service_name]
		return update_args
	#end define

	def install(self, install_args, install_answers):
		# install_args: user, src_dir, bin_dir, venvs_dir, venv_path, src_path
		udp_port = randint(1024, 65000)

		mconfig_dir = f"/home/{install_args.user}/.local/share/mytonprovider"
		mconfig_path = f"{mconfig_dir}/mytonprovider.db"
		provider_path = f"{install_answers.storage_path}/provider"
		db_dir = f"{provider_path}/db"
		provider_config_path = f"{provider_path}/config.json"

		# Склонировать исходники и скомпилировать бинарники
		upgrade_args = self.get_update_args(install_args.src_path)
		run_subprocess(upgrade_args, timeout=60)

		# Подготовить папку
		os.makedirs(provider_path, exist_ok=True)
		chown_args = [
			"chown", 
			install_args.user + ':' + install_args.user, 
			provider_path
		]
		run_subprocess(chown_args, timeout=3)

		# Создать службу
		main_module = get_module_by_name(self.local, "main")
		start_cmd = f"{install_args.bin_dir}/{self.go_package.repo} --db {db_dir} --config {provider_config_path} -network-config {main_module.global_config_path}"
		add2systemd(name=self.service_name, user=install_args.user, start=start_cmd, workdir=provider_path, force=True)

		# Первый запуск - создание конфига
		self.local.start_service(self.service_name, sleep=10)
		self.local.stop_service(self.service_name)

		# read mconfig
		mconfig = read_config_from_file(mconfig_path)

		# read provider config
		provider_config = read_config_from_file(provider_config_path)

		# edit provider config
		api = mconfig.ton_storage.api
		provider_config.ListenAddr = f"0.0.0.0:{udp_port}"
		provider_config.ExternalIP = get_own_ip()
		provider_config.MinSpan = 3600 *24 *7
		provider_config.MaxSpan = self.calculate_MaxSpan(install_answers.storage_cost)
		provider_config.MinRatePerMBDay = self.calculate_MinRatePerMBDay(install_answers.storage_cost)
		provider_config.MaxBagSizeBytes = 40 * 1024**3 # 40GB
		provider_config.Storages[0].BaseURL = f"http://{api.host}:{api.port}"
		provider_config.Storages[0].SpaceToProvideMegabytes = self.calculate_space_to_provide(install_answers.space_to_provide_gigabytes)
		provider_config.CRON.Enabled = True

		# write provider config
		write_config_to_file(config_path=provider_config_path, data=provider_config)

		# edit mytoncore config
		provider = Dict()
		provider.config_path = provider_config_path
		provider.src_dir = install_args.src_dir
		mconfig.ton_storage.provider = provider

		# write mconfig
		write_config_to_file(config_path=mconfig_path, data=mconfig)

		# start provider
		self.local.start_service(self.service_name)
	#end define

	def calculate_space_to_provide(self, input_space):
		# convert gigabytes to megabytes
		input_space_int = int(input_space)
		result = input_space_int *1024
		return result
	#end define

	def calculate_MaxSpan(self, storage_cost):
		min_proof_cost = 0.05
		min_span = 3600 *24 *30
		min_bag_size = 400
		# 200_gb_per_month --> 1_mb_per_sec
		data = float(storage_cost) /200 /1024 /30 /24 /3600
		max_span = int(min_proof_cost /(data *min_bag_size))
		if max_span < min_span:
			return min_span
		if max_span > 4294967290:
			max_span = 4294967290
		return max_span
	#end define

	def calculate_MinRatePerMBDay(self, storage_cost):
		# 200_gb_per_month --> 1_mb_per_day
		data = float(storage_cost) /200 /1024 /30
		return f"{data:.9f}"
	#end define
#end class

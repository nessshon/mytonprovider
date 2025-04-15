#!/usr/bin/env python3
# -*- coding: utf_8 -*-


import os
import base64
import requests
import subprocess
from random import randint
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

from utils import (
	get_module_by_name,
	get_disk_space,
	convert_to_required_decimal,
	fix_git_config
)
from decorators import publick
from adnl_over_udp_checker import check_adnl_connection


class Module():
	def __init__(self, local):
		# publick functions: get_console_commands, status, get_upgrade_args, check, bags_list
		self.name = "ton-storage"
		self.local = local
		self.local.add_log("ton_storage console module init done")

		self.go_package = Dict()
		self.go_package.author = "xssnick"
		self.go_package.repo = "tonutils-storage"
		self.go_package.branch = "master"
		self.go_package.entry_point = "cli/main.go"
	#end define

	@publick
	def get_console_commands(self):
		commands = list()
		bags_list_item = Dict()
		bags_list_item.cmd = "bags_list"
		bags_list_item.func = self.bags_list
		bags_list_item.desc = "Показать список хранимых контейнеров"

		commands.append(bags_list_item)
		return commands
	#end define

	@publick
	def check(self):
		print("check storage udp port")
		ton_storage = self.local.db.ton_storage
		storage_config = self.get_storage_config()
		
		own_ip = get_own_ip()
		if storage_config.ExternalIP != own_ip:
			raise Exception("storage_config.ExternalIP != own_ip")
		ok, error = check_adnl_connection(own_ip, ton_storage.port, ton_storage.pubkey)
		if not ok:
			color_print(f"{{red}}{error}{{endc}}")
	#end define

	def get_storage_config(self):
		ton_storage = self.local.db.ton_storage
		storage_config = read_config_from_file(ton_storage.config_path)
		return storage_config
	#end define

	@publick
	def status(self, args):
		api_data = self.get_api_data()
		bags_num = self.get_bags_num(api_data)
		ton_storage = self.local.db.ton_storage
		total_disk_space, used_disk_space, free_disk_space = get_disk_space(ton_storage.storage_path)
		used_provider_space = self.get_bags_size(api_data)
		git_hash, git_branch = self.get_my_git_hash_and_branch()
		color_print("{cyan}===[ Local storage status ]==={endc}")
		print(f"Название модуля: {self.name}")
		print(f"Количество хранимых контейнеров, размер: {bags_num} -> {used_provider_space} GB")
		print(f"Дисковое пространство: {used_disk_space} /{total_disk_space}")
		print(f"Версия хранилища: {git_hash} ({git_branch})")
	#end define

	def get_api_data(self):
		api = self.local.db.ton_storage.api
		api_url = f"http://{api.host}:{api.port}/api/v1/list"
		resp = requests.get(api_url, timeout=0.3)
		if resp.status_code != 200:
			raise Exception(f"Failed to get provider api data from {api_url}")
		return Dict(resp.json())
	#end define

	def get_bags_num(self, api_data):
		if api_data.bags == None:
			return 0
		return len(api_data.bags)
	#end define

	def get_bags_size(self, api_data, decimal_size=3):
		if api_data.bags == None:
			return 0
		used = 0
		for bag in api_data.bags:
			used += bag.size
		used_space = convert_to_required_decimal(used, decimal_size)
		return 
	#end define

	def get_my_git_hash_and_branch(self):
		ton_storage = self.local.db.ton_storage
		git_path = f"{ton_storage.src_dir}/{self.go_package.repo}"
		fix_git_config(git_path)
		git_hash = get_git_hash(git_path, short=True)
		git_branch = get_git_branch(git_path)
		return git_hash, git_branch
	#end define

	@publick
	def bags_list(self, args):
		api_data = self.get_api_data()
		print(f"TODO: api_data: {api_data}")
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
			install_args: Dict, 
			storage_path: str = None, 
			**kwargs
		):
		# install_args: user, src_dir, bin_dir, venvs_dir, venv_path, src_path
		host = "localhost"
		udp_port = randint(1024, 65000)
		api_port = randint(1024, 65000)
		#login = generate_login()
		#password = generate_password()

		mconfig_dir = f"/home/{install_args.user}/.local/share/mytonprovider"
		mconfig_path = f"{mconfig_dir}/mytonprovider.db"
		db_dir = f"{storage_path}/db"
		storage_config_path = f"{db_dir}/config.json"

		# Склонировать исходники и скомпилировать бинарники
		upgrade_args = self.get_upgrade_args(install_args.src_path)
		subprocess.run(upgrade_args)

		# Подготовить папку
		os.makedirs(storage_path, exist_ok=True)
		subprocess.run([
			"chown", "-R", 
			install_args.user + ':' + install_args.user, 
			storage_path
		])

		# Создать службу
		start_cmd = f"{install_args.bin_dir}/{self.go_package.repo} --daemon --db {db_dir} --api {host}:{api_port}" # --api-login {login} --api-password {password}
		add2systemd(name=self.name, user=install_args.user, start=start_cmd, workdir=storage_path, force=True)

		# Первый запуск - создание конфига
		self.local.start_service(self.name, sleep=10)
		self.local.stop_service(self.name)

		# read storage config
		storage_config = read_config_from_file(storage_config_path)

		# edit storage config
		storage_config.ListenAddr = f"0.0.0.0:{udp_port}"
		storage_config.ExternalIP = get_own_ip()

		# write storage config
		write_config_to_file(config_path=storage_config_path, data=storage_config)

		# get storage pubkey
		key_bytes = base64.b64decode(storage_config.Key)
		pubkey_bytes = key_bytes[32:64]
		pubkey = pubkey_bytes.hex().upper()

		# read mconfig
		mconfig = read_config_from_file(mconfig_path)

		# edit mconfig config
		ton_storage = Dict()
		ton_storage.storage_path = storage_path
		ton_storage.port = udp_port
		ton_storage.src_dir = install_args.src_dir
		ton_storage.pubkey = pubkey
		ton_storage.config_path = storage_config_path

		api = Dict()
		api.host = host
		api.port = api_port
		#api.login = login
		#api.password = password
		
		ton_storage.api = api
		mconfig.ton_storage = ton_storage

		# write mconfig
		write_config_to_file(config_path=mconfig_path, data=mconfig)

		# start service
		self.local.start_service(self.name)
	#end define
#end class

#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import base64
import requests
import subprocess
from random import randint
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
	get_git_branch,
	print_table
)

from utils import (
	get_module_by_name,
	get_disk_space,
	convert_to_required_decimal,
	fix_git_config,
	reduct
)
from decorators import publick
from adnl_over_udp_checker import check_adnl_connection


class Module():
	def __init__(self, local):
		self.name = "ton-storage"
		self.local = local
		self.mandatory = False
		self.local.add_log(f"{self.name} module init done", "debug")

		self.go_package = Dict()
		self.go_package.author = "xssnick"
		self.go_package.repo = "tonutils-storage"
		self.go_package.branch = "master"
		self.go_package.entry_point = "cli/main.go"
	#end define

	@publick
	def is_enabled(self):
		if "ton_storage" in self.local.db:
			return True
		return False
	#end define

	@publick
	def get_console_commands(self):
		commands = list()
		bags_list = Dict()
		bags_list.cmd = "bags_list"
		bags_list.func = self.bags_list
		bags_list.desc = self.local.translate("bags_list_cmd")

		commands.append(bags_list)
		return commands
	#end define

	@publick
	def check(self):
		ton_storage = self.local.db.ton_storage
		storage_config = self.get_storage_config()
		storage_pubkey = self.get_storage_pubkey()
		listen_ip, storage_port = storage_config.ListenAddr.split(':')
		
		own_ip = get_own_ip()
		if storage_config.ExternalIP != own_ip:
			raise Exception("storage_config.ExternalIP != own_ip")
		ok, error = check_adnl_connection(own_ip, storage_port, storage_pubkey)
		if not ok:
			color_print(f"{{red}}{error}{{endc}}")
	#end define

	def get_storage_config(self):
		ton_storage = self.local.db.ton_storage
		storage_config = read_config_from_file(ton_storage.config_path)
		return storage_config
	#end define

	def get_storage_pubkey(self):
		storage_config = self.get_storage_config()
		storage_bytes = base64.b64decode(storage_config.Key)
		storage_pubkey_bytes = storage_bytes[32:64]
		storage_pubkey = storage_pubkey_bytes.hex().upper()
		return storage_pubkey
	#end define

	@publick
	def status(self, args):
		color_print("{cyan}===[ Local storage status ]==={endc}")
		self.print_module_name()
		self.print_bags_num()
		self.print_disk_space()
		self.print_git_hash()
	#end define

	def print_module_name(self):
		module_name = bcolors.yellow_text(self.name)
		text = self.local.translate("module_name").format(module_name)
		print(text)
	#end define

	def print_bags_num(self):
		api_data = self.get_api_data()
		bags_num = self.get_bags_num(api_data)
		used_provider_space = self.get_bags_size(api_data, decimal_size=3, round_size=2)
		bags_num_text = bcolors.green_text(bags_num)
		used_provider_space_text = bcolors.green_text(used_provider_space) # TODO
		text = self.local.translate("bags_num").format(bags_num_text, used_provider_space_text)
		print(text)
	#end define

	def print_disk_space(self):
		ton_storage = self.local.db.ton_storage
		total_disk_space, used_disk_space, free_disk_space = get_disk_space(ton_storage.storage_path, decimal_size=3, round_size=2)
		used_disk_space_text = bcolors.green_text(used_disk_space) # TODO
		total_disk_space_text = bcolors.yellow_text(total_disk_space)
		text = self.local.translate("disk_space").format(used_disk_space_text, total_disk_space_text)
		print(text)
	#end define

	def print_git_hash(self):
		git_hash, git_branch = self.get_my_git_hash_and_branch()
		git_hash_text = bcolors.yellow_text(git_hash)
		git_branch_text = bcolors.yellow_text(git_branch)
		text = self.local.translate("git_hash").format(git_hash_text, git_branch_text)
		print(text)
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

	def get_bags_size(self, api_data, decimal_size, round_size):
		if api_data.bags == None:
			return 0
		used = 0
		for bag in api_data.bags:
			used += bag.size
		used_space = convert_to_required_decimal(used, decimal_size, round_size)
		return used_space
	#end define

	@publick
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
		if api_data.bags == None:
			print("no data")
			return
		table = [["Bag id", "Progress", "Size", "Files", "Peers", "Download speed", "Upload speed"]]
		for bag in api_data.bags:
			bag_id = reduct(bag.bag_id)
			progress = self.get_progress(bag)
			size = convert_to_required_decimal(bag.size, decimal_size=3, round_size=2)
			download_speed = convert_to_required_decimal(bag.download_speed, decimal_size=2, round_size=2)
			upload_speed = convert_to_required_decimal(bag.upload_speed, decimal_size=2, round_size=2)
			progress_text = f"{progress}%"
			size_text = f"{size} GB"
			download_speed_text = f"{download_speed} MB/s"
			upload_speed_text = f"{upload_speed} MB/s"
			table += [[bag_id, progress_text, size_text, bag.files_count, bag.peers, download_speed_text, upload_speed_text]]
		print_table(table)
	#end define

	def get_progress(self, bag):
		if bag.size == 0:
			return 0
		progress = round(bag.downloaded /bag.size *100, 2)
		return progress
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
		#key_bytes = base64.b64decode(storage_config.Key)
		#pubkey_bytes = key_bytes[32:64]
		#pubkey = pubkey_bytes.hex().upper()

		# read mconfig
		mconfig = read_config_from_file(mconfig_path)

		# edit mconfig config
		ton_storage = Dict()
		ton_storage.storage_path = storage_path
		#ton_storage.port = udp_port
		ton_storage.src_dir = install_args.src_dir
		#ton_storage.pubkey = pubkey
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

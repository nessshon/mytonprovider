#!/usr/bin/env python3
# -*- coding: utf_8 -*-

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


class Module():
	def __init__(self, local):
		self.name = "ton-storage"
		self.local = local
		self.local.add_log("ton_storage console module init done")

		self.go_package = Dict()
		self.go_package.author = "xssnick"
		self.go_package.repo = "tonutils-storage"
		self.go_package.branch = "master"
		self.go_package.entry_point = "cli/main.go"
	#end define

	# def get_console_commands(self):
	# 	return list()
	# #end define

	def status(self, args):
		data = self.get_api_data()
		color_print("{cyan}===[ Local storage status ]==={endc}")
		print(f"Название модуля: {self.name}")
		print(f"Количество хранимых контейнеров: {data}")
		print(f"Пространство хранилища: занято/свободно")
		print(f"Версия хранилища: git_version (git_branch)")
	#end define

	def get_api_data(self):
		api = self.local.db.ton_storage.api
		api_url = f"http://{api.host}:{api.port}/api/v1/list"
		resp = requests.get(api_url, timeout=0.3)
		if resp.status_code != 200:
			raise Exception(f"Failed to get provider api data from {api_url}")
		return Dict(resp.json())
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
		ton_storage.port = udp_port
		#ton_storage.user = install_args.user
		#ton_storage.src_dir = install_args.src_dir
		#ton_storage.bin_dir = install_args.bin_dir
		#ton_storage.venvs_dir = install_args.venvs_dir
		#ton_storage.venv_path = install_args.venv_path
		#ton_storage.src_path = install_args.src_path

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
		self.local.start_service(self.name)
	#end define
#end class

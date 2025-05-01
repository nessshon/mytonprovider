#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import subprocess
from random import randint
from mypylib import (
	Dict,
	MyPyClass,
	add2systemd,
	write_config_to_file
)
from utils import (
	generate_login,
	generate_password,
	get_package_path
)



def install(local, install_args, **kwargs):
	# install_args: user, src_dir, bin_dir, venvs_dir, venv_path, src_path

	# Проверить конфигурацию
	mconfig_dir = f"/home/{install_args.user}/.local/share/mytonprovider"
	mconfig_path = f"{mconfig_dir}/mytonprovider.db"
	# if os.path.isfile(mconfig_path):
	# 	print(f"{mconfig_path} already exist. Break mytonprovider install")
	# 	return
	# #end if

	# Подготовить папку
	os.makedirs(mconfig_dir, exist_ok=True)

	# Создать конфиг
	mconfig = Dict()
	mconfig.config = Dict()
	mconfig.config.logLevel = "debug"
	mconfig.config.isLocaldbSaving = True
	mconfig.config.isStartOnlyOneProcess = False
	#mconfig.send_telemetry = local.buffer.telemetry

	# Записать конфиг
	write_config_to_file(config_path=mconfig_path, data=mconfig)

	# Поменять права с root на user
	subprocess.run([
		"chown",
		install_args.user + ':' + install_args.user,
		mconfig_dir,
		mconfig_path
	])

	# Создать службу
	daemon_name = "mytonproviderd"
	start_cmd = f"{install_args.venv_path}/bin/python3 {install_args.src_path}/mytonprovider.py"
	start_daemon_cmd = f"{start_cmd} --daemon"
	add2systemd(name=daemon_name, user=install_args.user, start=start_daemon_cmd, force=True)

	# Запустить службу
	local.start_service(daemon_name)

	# Создать ссылки
	file_path = "/usr/bin/mytonprovider"
	file_text = f"{start_cmd} $@"
	with open(file_path, 'wt') as file:
		file.write(file_text)
	#end with

	# Дать права на запуск
	args = ["chmod", "+x", file_path]
	subprocess.run(args)
#end define

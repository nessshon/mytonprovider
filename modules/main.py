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



def install(args: Dict, **kwargs):
	# Проверить конфигурацию
	mconfig_dir = f"/home/{args.user}/.local/share/mytonprovider"
	mconfig_path = f"{mconfig_dir}/mytonprovider.db"
	if os.path.isfile(mconfig_path):
		print(f"{mconfig_path} already exist. Break mytonprovider install")
		return
	#end if

	# Подготовить папку
	os.makedirs(mconfig_dir, exist_ok=True)

	# Создать конфиг
	mconfig = Dict()
	mconfig.config = Dict()
	mconfig.config.logLevel = "debug"
	mconfig.config.isLocaldbSaving = True
	#mconfig.send_telemetry = local.buffer.telemetry

	# Записать конфиг
	write_config_to_file(config_path=mconfig_path, data=mconfig)

	# Поменять права с root на user
	subprocess.run([
		"chown",
		args.user + ':' + args.user,
		mconfig_dir,
		mconfig_path
	])
#end define

#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import psutil
import subprocess
from mypylib import (
	Dict,
	get_load_avg,
	read_config_from_file,
	write_config_to_file
)
from decorators import publick
from utils import get_module_by_name, get_disk_space


class Module():
	def __init__(self, local):
		self.name = "telemetry"
		self.local = local
		self.default_url = "https://telemetry.mytonprovider.org/report_status"
		self.local.add_log(f"{self.name} module init done", "debug")
	#end define

	@publick
	def daemon(self):
		send_telemetry = self.local.db.get("send_telemetry")
		if send_telemetry != True:
			return
		# end if

		data = self.collect_telemetry_data()
		print("telemetry_data:", data)
		#self.send_telemetry(data)
	#end define

	def collect_telemetry_data(self):
		ton_storage_module = get_module_by_name(self.local, "ton-storage")
		ton_storage_provider_module = get_module_by_name(self.local, "ton-storage-provider")
		total_disk_space, used_disk_space, free_disk_space = get_disk_space(self.local.db.ton_storage.storage_path, decimal_size=3, round_size=2)

		data = Dict()
		data.storage = Dict()
		data.storage.pubkey = "TODO"
		data.storage.disk_name = self.local.try_function(get_storage_disk_name)
		data.storage.total_disk_space = total_disk_space
		data.storage.used_disk_space = used_disk_space
		data.storage.free_disk_space = free_disk_space

		
		data.storage.provider = Dict()
		data.storage.provider.pubkey = self.local.db.ton_storage.provider.pubkey
		data.storage.provider.used_provider_space = ton_storage_provider_module.get_used_provider_space(decimal_size=3, round_size=2)
		data.storage.provider.total_provider_space = ton_storage_provider_module.get_total_provider_space(decimal_size=3, round_size=2)

		data.git_hashes = Dict()
		data.git_hashes = self.get_all_git_hashes()

		data.net_load = GetStatistics("net_load_avg")
		data.disks_load = GetStatistics("disks_load_avg")
		data.disks_load_percent = GetStatistics("disks_load_percent_avg")
		data.iops = GetStatistics("iops_avg")
		data.pps = GetStatistics("pps_avg")
		data.memory = get_memory_info()
		data.swap = get_swap_info()
		data.uname = get_uname()

		data.cpu_info = Dict()
		data.cpu_info.number = psutil.cpu_count()
		data.cpu_info.cpu_load = get_load_avg()
		data.cpu_info.cpu_name = self.local.try_function(get_cpu_name)
		data.cpu_info.product_name = self.local.try_function(get_product_name)
		data.cpu_info.is_virtual = self.local.try_function(is_product_virtual)
		data.pings = self.local.try_function(get_pings_values)
		data.benchmark = self.local.db.benchmark

		return data
	#end define

	def get_all_git_hashes(self):
		result = Dict()
		for module in self.local.buffer.modules:
			method = getattr(module, "get_my_git_hash_and_branch", None)
			if method == None:
				continue
			git_hash, git_branch = module.get_my_git_hash_and_branch()
			result[module.name] = git_hash
		return result
	#end define

	def send_telemetry(self, data):
		url = self.local.db.get("telemetry_url", self.default_url)
		output = json.dumps(data)
		resp = requests.post(url, data=output, timeout=3)
	#end define

	def install(self, install_args, **kwargs):
		# install_args: user, src_dir, bin_dir, venvs_dir, venv_path, src_path
		mconfig_dir = f"/home/{install_args.user}/.local/share/mytonprovider"
		mconfig_path = f"{mconfig_dir}/mytonprovider.db"

		# read mconfig
		mconfig = read_config_from_file(mconfig_path)

		# edit mytoncore config
		mconfig.send_telemetry = True

		# write mconfig
		write_config_to_file(config_path=mconfig_path, data=mconfig)
	#end define
#end class

def GetStatistics(*args, **kwargs):
	return "TODO"
#end define

def get_cpu_name():
	with open("/proc/cpuinfo") as file:
		for line in file:
			if line.strip():
				if line.rstrip('\n').startswith("model name"):
					return line.rstrip('\n').split(':')[1].strip()
	return None
#end define

def get_product_name():
	try:
		with open("/sys/class/dmi/id/product_name") as file:
			product_name = file.read().strip().lower()
	except FileNotFoundError:
		product_name = None
	return product_name
#end define

def is_product_virtual():
	virtual_names = ["virtual", "kvm", "qemu", "vmware"]
	product_name = get_product_name()
	if product_name == None:
		return
	#end if

	result = False
	for name in virtual_names:
		if name in product_name:
			result = True
			break
	return result
#end define

def do_beacon_ping(host, count=3, timeout=5):
	args = ['ping', '-c', str(count), '-W', str(timeout), host]
	process = subprocess.run(
		args,
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		timeout=timeout
	)
	stdout = process.stdout.decode("utf-8")
	stderr = process.stderr.decode("utf-8")
	if process.returncode != 0:
		raise Exception(f"do_beacon_ping error: {stderr}")
	avg = stdout.split('\n')[-2].split('=')[1].split('/')[1]
	return float(avg)
#end define

def get_pings_values():
	checker_hosts = [
		'45.129.96.53',
		'5.154.181.153',
		'2.56.126.137',
		'91.194.11.68',
		'45.12.134.214',
		'138.124.184.27',
		'103.106.3.171'
	]

	result = dict()
	for host in checker_hosts:
		result[host] = do_beacon_ping(host)
	return result
#end define

def get_storage_disk_name(storage_dir="/var/storage"):
	process = subprocess.run(
		f"df -h {storage_dir} | sed -n '2 p' | awk '{{print $1}}'", 
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		timeout=3,
		shell=True
	)
	output = process.stdout.decode("utf-8")
	return output.strip()
#end define

def get_uname():
	data = os.uname()
	result = dict(
		zip('sysname nodename release version machine'.split(), data))
	result.pop("nodename")
	return result
#end define

def get_memory_info():
	result = Dict()
	data = psutil.virtual_memory()
	result.total = round(data.total / 10**9, 2)
	result.usage = round(data.used / 10**9, 2)
	result.usage_percent = data.percent
	return result
#end define

def get_swap_info():
	result = Dict()
	data = psutil.swap_memory()
	result.total = round(data.total / 10**9, 2)
	result.usage = round(data.used / 10**9, 2)
	result.usage_percent = data.percent
	return result
#end define
#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import psutil
import subprocess
from mypylib import Dict


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

def get_ram_info():
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
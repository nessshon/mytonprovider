#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import os
import json
import psutil
from mypylib import (
	Dict,
	bcolors,
	color_print,
	print_table,
	get_timestamp,
	get_internet_interface_name,
	get_load_avg
)
from decorators import publick
from asgiref.sync import async_to_sync
from utils import (
	convert_to_required_decimal,
	get_color_int
)
from server_info import (
	get_cpu_name,
	get_product_name,
	is_product_virtual,
	do_beacon_ping,
	get_pings_values,
	get_storage_disk_name,
	get_uname,
	get_ram_info,
	get_swap_info
)


class Module():
	def __init__(self, local):
		self.name = "statistics"
		self.local = local
		self.mandatory = True
		self.daemon_interval = 10
		self.init_data()
		self.local.add_log(f"{self.name} module init done", "debug")
	#end define

	def init_data(self):
		self.local.buffer.network = [None]*15*6
		self.local.buffer.diskio = [None]*15*6
	#end define

	@publick
	def status(self, args):
		color_print("{cyan}===[ Statistics status ]==={endc}")
		self.print_module_name()
		self.print_cpu_load()
		self.print_network_load()
		self.print_disks_load()
		self.print_memory_load()
	#end define

	def print_module_name(self):
		module_name = bcolors.yellow_text(self.name)
		text = self.local.translate("module_name").format(module_name)
		print(text)
	#end define

	def print_cpu_load(self):
		cpu_count = psutil.cpu_count()
		cpu_load1, cpu_load5, cpu_load15 = get_load_avg()
		cpu_count_text = bcolors.yellow_text(cpu_count)
		cpu_load1_text = get_color_int(cpu_load1, cpu_count, logic="less")
		cpu_load5_text = get_color_int(cpu_load5, cpu_count, logic="less")
		cpu_load15_text = get_color_int(cpu_load15, cpu_count, logic="less")
		text = self.local.translate("cpu_load").format(cpu_count_text, cpu_load1_text, cpu_load5_text, cpu_load15_text)
		print(text)
	#end define

	def print_memory_load(self):
		ram = get_ram_info()
		swap = get_swap_info()
		ram_usage_text = get_color_int(ram.usage, 100, logic="less", ending=" Gb")
		ram_usage_percent_text = get_color_int(ram.usage_percent, 90, logic="less", ending="%")
		swap_usage_text = get_color_int(swap.usage, 100, logic="less", ending=" Gb")
		swap_usage_percent_text = get_color_int(swap.usage_percent, 90, logic="less", ending="%")
		ram_load_text = f"{bcolors.cyan}ram:[{bcolors.default}{ram_usage_text}, {ram_usage_percent_text}{bcolors.cyan}]{bcolors.endc}"
		swap_load_text = f"{bcolors.cyan}swap:[{bcolors.default}{swap_usage_text}, {swap_usage_percent_text}{bcolors.cyan}]{bcolors.endc}"
		text = self.local.translate("memory_load").format(ram_load_text, swap_load_text)
		print(text)
	#end define

	def print_network_load(self):
		borderline_value = 300 # 300 Mbit/s
		net_load1, net_load5, net_load15 = self.get_statistics_data("net_load_avg")
		net_load1_text = get_color_int(net_load1, borderline_value, logic="less")
		net_load5_text = get_color_int(net_load5, borderline_value, logic="less")
		net_load15_text = get_color_int(net_load15, borderline_value, logic="less")
		text = self.local.translate("net_load").format(net_load1_text, net_load5_text, net_load15_text)
		print(text)
	#end define

	def print_disks_load(self):
		borderline_value = 80 # 80%
		disks_load_avg = self.get_statistics_data("disks_load_avg")
		disks_load_percent_avg = self.get_statistics_data("disks_load_percent_avg")

		# Disks status
		disks_load_list = list()
		for name, data in disks_load_avg.items():
			disk_load_text = bcolors.green_text(data[2]) # data = 1 minute, 5 minute, 15 minute
			disk_load_percent_text = get_color_int(disks_load_percent_avg[name][2], borderline_value, logic="less", ending="%")
			buff = "{}, {}"
			buff = "{}{}:[{}{}{}]{}".format(bcolors.cyan, name, bcolors.default, buff, bcolors.cyan, bcolors.endc)
			disks_load_buff = buff.format(disk_load_text, disk_load_percent_text)
			disks_load_list.append(disks_load_buff)
		disks_load_data = ", ".join(disks_load_list)
		text = self.local.translate("disks_load").format(disks_load_data)
		print(text)
	#end define

	def get_statistics_data(self, name):
		life_time = 120 # seconds
		if self.local.db.statistics == None:
			raise Exception("get_statistics_data error: local.db.statistics is None")
		if self.local.db.statistics.timestamp + life_time < get_timestamp():
			raise Exception("get_statistics_data error: local.db.statistics is old")
		#end if

		data = self.local.db.statistics.get(name)
		return data
	#end define

	@publick
	def daemon(self):
		self.read_network_data()
		self.save_network_statistics()
		self.read_disk_data()
		self.save_disk_statistics()
	#end define

	def read_disk_data(self):
		timestamp = get_timestamp()
		disks = self.get_disks_list()
		buff = psutil.disk_io_counters(perdisk=True)
		data = dict()
		for name in disks:
			data[name] = Dict()
			data[name].timestamp = timestamp
			data[name].busy_time = buff[name].busy_time
			data[name].read_bytes = buff[name].read_bytes
			data[name].write_bytes = buff[name].write_bytes
			data[name].read_count = buff[name].read_count
			data[name].write_count = buff[name].write_count
		#end for

		self.local.buffer.diskio.pop(0)
		self.local.buffer.diskio.append(data)
		#print("read_disk_data:", data)
	#end define


	def save_disk_statistics(self):
		data = self.local.buffer.diskio
		data = data[::-1]
		zerodata = data[0]
		buff1 = data[1*6-1]
		buff5 = data[5*6-1]
		buff15 = data[15*6-1]
		if buff5 is None:
			buff5 = buff1
		if buff15 is None:
			buff15 = buff5
		#end if

		disks_load_avg = dict()
		disks_load_percent_avg = dict()
		iops_avg = dict()
		disks = self.get_disks_list()
		for name in disks:
			if zerodata[name].busy_time == 0:
				continue
			disk_load1, disk_load_percent1, iops1 = self.calculate_disk_statistics(zerodata, buff1, name)
			disk_load5, diskLoadPercent5, iops5 = self.calculate_disk_statistics(zerodata, buff5, name)
			disk_load15, diskLoadPercent15, iops15 = self.calculate_disk_statistics(zerodata, buff15, name)
			disks_load_avg[name] = [disk_load1, disk_load5, disk_load15]
			disks_load_percent_avg[name] = [disk_load_percent1, diskLoadPercent5, diskLoadPercent15]
			iops_avg[name] = [iops1, iops5, iops15]
			#print(name, "disks_load_avg:", disks_load_avg)
			#print(name, "disks_load_percent_avg:", disks_load_percent_avg)
			#print(name, "iops_avg:", iops_avg)
		#end fore

		# save statistics
		statistics = self.local.db.get("statistics", Dict())
		statistics.timestamp = get_timestamp()
		statistics.disks_load_avg = disks_load_avg
		statistics.disks_load_percent_avg = disks_load_percent_avg
		statistics.iops_avg = iops_avg
		self.local.db.statistics = statistics
	#end define

	def calculate_disk_statistics(self, zerodata, data, name):
		if data is None:
			return None, None, None
		data = data[name]
		zerodata = zerodata[name]
		time_diff = zerodata.timestamp - data.timestamp
		busy_time_diff = zerodata.busy_time - data.busy_time
		disk_read_diff = zerodata.read_bytes - data.read_bytes
		disk_write_diff = zerodata.write_bytes - data.write_bytes
		disk_read_count_diff = zerodata.read_count - data.read_count
		disk_write_count_diff = zerodata.write_count - data.write_count
		disk_load_percent = busy_time_diff /1000 /time_diff *100  # /1000 - to second, *100 - to percent
		disk_load_percent = round(disk_load_percent, 2)
		disk_read = disk_read_diff /time_diff
		disk_write = disk_write_diff /time_diff
		disk_read_count = disk_read_count_diff /time_diff
		disk_write_count = disk_write_count_diff /time_diff
		disk_load = convert_to_required_decimal(disk_read + disk_write, decimal_size=3, round_size=0)
		iops = round(disk_read_count + disk_write_count, 2)
		return disk_load, disk_load_percent, iops
	#end define

	def get_disks_list(self):
		data = list()
		buff = os.listdir("/sys/block/")
		for item in buff:
			if "loop" in item:
				continue
			data.append(item)
		#end for
		data.sort()
		return data
	#end define

	def read_network_data(self):
		timestamp = get_timestamp()
		interface_name = get_internet_interface_name()
		buff = psutil.net_io_counters(pernic=True)
		buff = buff[interface_name]
		data = Dict()
		data.timestamp = timestamp
		data.bytes_recv = buff.bytes_recv
		data.bytes_sent = buff.bytes_sent
		data.packets_sent = buff.packets_sent
		data.packets_recv = buff.packets_recv

		self.local.buffer.network.pop(0)
		self.local.buffer.network.append(data)
		#print("read_network_data:", data)
	#end define

	def save_network_statistics(self):
		data = self.local.buffer.network
		data = data[::-1]
		zerodata = data[0]
		buff1 = data[1*6-1]
		buff5 = data[5*6-1]
		buff15 = data[15*6-1]
		if buff5 is None:
			buff5 = buff1
		if buff15 is None:
			buff15 = buff5
		#end if

		networkLoadAvg1, ppsAvg1 = self.calculate_network_statistics(zerodata, buff1)
		networkLoadAvg5, ppsAvg5 = self.calculate_network_statistics(zerodata, buff5)
		networkLoadAvg15, ppsAvg15 = self.calculate_network_statistics(zerodata, buff15)
		net_load_avg = [networkLoadAvg1, networkLoadAvg5, networkLoadAvg15]
		pps_avg = [ppsAvg1, ppsAvg5, ppsAvg15]
		#print("net_load_avg:", net_load_avg)
		#print("pps_avg:", pps_avg)

		# save statistics
		statistics = self.local.db.get("statistics", Dict())
		statistics.timestamp = get_timestamp()
		statistics.net_load_avg = net_load_avg
		statistics.pps_avg = pps_avg
		self.local.db.statistics = statistics
	#end define

	def calculate_network_statistics(self, zerodata, data):
		if data is None:
			return None, None
		time_diff = zerodata.timestamp - data.timestamp
		bytes_recv_diff = zerodata.bytes_recv - data.bytes_recv
		bytes_sent_diff = zerodata.bytes_sent - data.bytes_sent
		packets_recv_diff = zerodata.packets_recv - data.packets_recv
		packets_sent_diff = zerodata.packets_sent - data.packets_sent
		bites_recv_avg = bytes_recv_diff /time_diff *8
		bites_sent_avg = bytes_sent_diff /time_diff *8
		packets_recv_avg = packets_recv_diff /time_diff
		packets_sent_avg = packets_sent_diff /time_diff
		net_load_avg = convert_to_required_decimal(bites_recv_avg + bites_sent_avg, decimal_size=3, round_size=0)
		pps_avg = round(packets_recv_avg + packets_sent_avg, 2)
		return net_load_avg, pps_avg
	#end define
#end class

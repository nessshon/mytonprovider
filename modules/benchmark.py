#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import json
import subprocess
from mypylib import (
	MyPyClass,
	Dict,
	bcolors,
	run_as_root,
	color_print,
	print_table,
	get_timestamp
)
from decorators import publick
from asgiref.sync import async_to_sync


class Module():
	def __init__(self, local):
		self.name = "benchmark"
		self.local = local
		self.mandatory = True
		self.local.add_log(f"{self.name} console module init done", "debug")
	#end define

	@publick
	def get_console_commands(self):
		commands = list()

		benchmark = Dict()
		benchmark.cmd = "benchmark"
		benchmark.func = self.run_benchmark
		benchmark.desc = self.local.translate("benchmark_cmd")
		commands.append(benchmark)

		return commands
	#end define

	@publick
	def run_benchmark(self, args):
		data = self.do_benchmark()
		table = list()
		table += [["Test type", "Read speed", "Write speed", "Read iops", "Write iops", "Random ops"]]
		table += [["Fio lite", data.lite.read_speed, data.lite.write_speed, data.lite.read_iops, data.lite.write_iops, None]] # RND-4K-QD64
		table += [["Fio hard", data.hard.read_speed, data.hard.write_speed, data.hard.read_iops, data.hard.write_iops, None]] # RND-4K-QD1
		table += [["RocksDB", None, None, None, None, data.full.random_ops]]
		print_table(table)
	#end define

	@publick
	def status_disable(self, args):
		color_print("{cyan}===[ Benchmark status ]==={endc}")
		self.print_module_name()
		self.print_last_banchmark_time()
		self.print_banchmark_data()
	#end define

	def print_module_name(self):
		module_name = bcolors.yellow_text(self.name)
		text = self.local.translate("module_name").format(module_name)
		print(text)
	#end define

	def print_last_banchmark_time(self):
		if self.is_benchmark_done():
			last_banchmark_time = self.local.db.benchmark.time
		else:
			last_banchmark_time = None
		#end if

		last_banchmark_time_text = self.local.translate("last_banchmark_time").format(last_banchmark_time)
		print(last_banchmark_time_text)
	#end define

	def print_banchmark_data(self):
		data = self.local.db.benchmark
		if self.is_benchmark_done() == False:
			return
		#end if

		lite_banchmark_speed_text = self.local.translate("lite_banchmark_speed").format(data.lite.read_speed, data.lite.write_speed)
		hard_banchmark_speed_text = self.local.translate("hard_banchmark_speed").format(data.hard.read_speed, data.hard.write_speed)
		full_banchmark_text = self.local.translate("full_banchmark").format(data.full.random_ops)
		print(lite_banchmark_speed_text)
		print(hard_banchmark_speed_text)
		print(full_banchmark_text)
	#end define

	def is_benchmark_done(self):
		if self.local.db.benchmark == None:
			return False
		time_now = get_timestamp()
		life_time = 3600 *24 *7
		if self.local.db.benchmark.time + life_time < time_now:
			return False
		return True
	#end define

	@publick
	def daemon(self):
		if self.is_benchmark_done():
			return
		self.do_benchmark()
	#end define

	def save_benchmark(self, data):
		self.local.add_log("start save_benchmark function", "debug")
		self.local.db.benchmark = data
		self.local.db.benchmark.time = get_timestamp()
	#end define

	def do_benchmark(self):
		self.local.add_log("start run_benchmark function", "debug")
		timeout = 200
		src_path = self.local.buffer.my_dir
		benchmark_script_path = f"{src_path}/scripts/benchmark.sh"
		benchmark_path = self.local.db.ton_storage.storage_path
		process = subprocess.run(
			["bash", benchmark_script_path, benchmark_path], 
			stdin=subprocess.PIPE, 
			stdout=subprocess.PIPE, 
			stderr=subprocess.PIPE, 
			timeout=timeout)
		stdout = process.stdout.decode("utf-8")
		stderr = process.stderr.decode("utf-8")
		if process.returncode != 0:
			raise Exception(f"run_benchmark error: {stderr}")
		#end if

		result = Dict(json.loads(stdout))
		self.save_benchmark(result)
		return result
	#end define
#end class

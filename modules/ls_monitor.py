#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import time
import asyncio
from asgiref.sync import async_to_sync

from modules.adnl_over_tcp import get_lite_balancer
from mypylib import (
	Dict,
	print_table,
)
from decorators import publick


class Module():
	def __init__(self, local):
		self.name = "ls_monitor"
		self.local = local
		self.mandatory = True
		self.daemon_interval = 60
		self.local.add_log(f"{self.name} module init done", "debug")
	# end define

	@publick
	def get_console_commands(self):
		commands = list()

		cmd = Dict()
		cmd.cmd = "check_ls"
		cmd.func = self.run_check_ls
		cmd.desc = self.local.translate("check_ls_cmd")
		commands.append(cmd)

		return commands
	# end define

	@publick
	@async_to_sync
	async def run_check_ls(self, args):
		results = await self.do_ls_check()

		table = []
		table += [["LS", "IP", "PORT", "Connected", "Connect time", "Request time", "Ping", "Version", "Time", "Last block seqno"]]
		for r in results:
			table += [[
				r.get("ls"),
				r.get("ip"),
				r.get("port"),
				f"true" if r.get("connected", False) else "false",
				r.get("connect_time", "-"),
				r.get("request_time", "-"),
				r.get("get_ping", "-"),
				r.get("get_version", "-"),
				r.get("get_time", "-"),
				r.get("get_last_block_seqno", "-"),
			]]
		print_table(table)
	# end define

	async def do_ls_check(self):
		self.local.add_log("LS check is running, it may take about a few seconds.", "debug")
		servers = await self.get_public_ls_list()
		results = await self._check_all_ls(servers)
		return results
	# end define

	async def _check_all_ls(self, servers):
		if not servers:
			return []

		sem = asyncio.Semaphore(10)
		async def run_one(index, lite_server):
			async with sem:
				return await self.probe_lite_server(index, lite_server)

		tasks = [run_one(index, lite_server) for index, lite_server in servers]
		return await asyncio.gather(*tasks, return_exceptions=False)
	# end define

	async def get_public_ls_list(self):
		client = get_lite_balancer(self.local)
		ls_list = []
		for index, lite_client in enumerate(client._peers):
			ls_list.append((index, lite_client))
		return ls_list
	# end define

	async def probe_lite_server(self, index, lite_client):
		data = {
			"ls": index,
			"ip": lite_client.server.host,
			"port": lite_client.server.port,
		}
		connected = False
		try:
			connected, connected_timing = await self.connect(lite_client)
			connected = bool(connected)
			data["connected"] = connected
			if connected_timing is not None:
				data["connect_time"] = f"{int(connected_timing)} ms"

			if not connected:
				return data

			ls_ping_timing = await self.get_ping(lite_client)
			if ls_ping_timing is not None:
				data["get_ping"] = f"{int(ls_ping_timing)} ms"

			ls_time = await self.get_time(lite_client)
			if ls_time is not None:
				data["get_time"] = ls_time

			ls_version = await self.get_version(lite_client)
			if ls_version is not None:
				data["get_version"] = ls_version

			ls_last_block_seqno, request_timing = await self.get_last_block_seqno(lite_client)
			if ls_last_block_seqno is not None:
				data["get_last_block_seqno"] = ls_last_block_seqno
			if request_timing is not None:
				data["request_time"] = f"{int(request_timing)} ms"

			return data
		except (Exception,):
			data["connected"] = False
			return data
		finally:
			if connected:
				try:
					await lite_client.close()
				except (Exception,):
					pass
	# end define

	async def connect(self, lite_client):
		start = time.perf_counter()
		try:
			await asyncio.wait_for(lite_client.connect(), 1)
			end = int((time.perf_counter() - start) * 1000.0)
			return True, end
		except (Exception,):
			return False, None

	async def get_version(self, lite_client):
		try:
			result = await lite_client.get_version()
			return result.get("version")
		except (Exception,):
			return None
	# end define

	async def get_time(self, lite_client):
		try:
			result = await lite_client.get_time()
			return result.get("now")
		except (Exception,):
			return None
	# end define

	async def get_last_block_seqno(self, lite_client):
		start = time.perf_counter()
		try:
			await lite_client.update_last_blocks()
			end = int((time.perf_counter() - start) * 1000.0)
			return lite_client.last_mc_block.seqno, end
		except (Exception,):
			return None, None
	# end define

	async def get_ping(self, lite_client):
		try:
			ping_query, qid = lite_client.get_ping_query()
			start = time.perf_counter()
			pong = await lite_client.send(ping_query, qid)
			await pong
			end = (time.perf_counter() - start) * 1000.0
			return end
		except (Exception,):
			return None
	# end define

	@publick
	def daemon(self):
		pass
	# end define
# end class

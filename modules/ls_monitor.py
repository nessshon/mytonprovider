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
		cmd.cmd = "ls_status"
		cmd.func = self.run_ls_status
		cmd.desc = self.local.translate("ls_status_cmd")
		commands.append(cmd)

		return commands
	# end define

	@publick
	@async_to_sync
	async def run_ls_status(self, args):
		results = await self.do_ls_status()

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
				r.get("last_block_seqno", "-"),
			]]
		print_table(table)
	# end define

	async def do_ls_status(self):
		servers = await self.get_public_ls_list()
		results = await self._check_all_ls(servers)

		# находим максимальный seqno мастерчейна среди всех ls
		max_last_block_seqno = 0
		for r in results:
			last_block_seqno = r.get("last_block_seqno_raw")
			if isinstance(last_block_seqno, int) and last_block_seqno > max_last_block_seqno:
				max_last_block_seqno = last_block_seqno

		# собираем максимальные seqno по каждому шарду среди всех ls
		max_shards = Dict()
		for r in results:
			shards = r.get("shards") or {}
			for shard_id, shard_seqno in shards.items():
				cur_shard = max_shards.get(shard_id, 0)
				if isinstance(shard_seqno, int) and shard_seqno > cur_shard:
					max_shards[shard_id] = shard_seqno

		# для каждого ls определяем отставание мастерчейна и/или шардов
		for r in results:
			last_block_seqno = r.get("last_block_seqno_raw")
			if not isinstance(last_block_seqno, int):
				continue

			label = str(last_block_seqno)

			# проверяем, отстаёт ли мастерчейн
			if last_block_seqno < max_last_block_seqno:
				# если мастерчейн отстал - ставим (!)
				label += " (!)"
			else:
				# если мастерчейн не отстает - проверяем шарды
				shards = r.get("shards") or {}
				for shard_id, shard_seqno in shards.items():
					max_shard_seqno = max_shards.get(shard_id)
					# если хоть один шард отстаёт - ставим (!!)
					if isinstance(shard_seqno, int) and isinstance(max_shard_seqno, int) and shard_seqno < max_shard_seqno:
						label += " (!!)"
						break

			r["last_block_seqno"] = label
		return results
	# end define

	async def get_public_ls_list(self):
		client = get_lite_balancer(self.local)
		ls_list = []
		for index, lite_client in enumerate(client._peers):  # noqa
			ls_list.append((index, lite_client))
		return ls_list
	# end define

	async def _check_all_ls(self, servers):
		if not servers:
			return []

		tasks = [self.probe_lite_server(index, lite_server) for index, lite_server in servers]
		return await asyncio.gather(*tasks, return_exceptions=False)
	# end define

	async def probe_lite_server(self, index, lite_client):
		data = {
			"ls": index,
			"ip": lite_client.server.host,
			"port": lite_client.server.port,
		}
		connected = False
		try:
			# подключаемся к ls и измеряем время соединения
			connected, connected_timing = await self.connect(lite_client)
			connected = bool(connected)
			data["connected"] = connected
			if connected_timing is not None:
				data["connect_time"] = f"{int(connected_timing)} ms"

			# если подключение не удалось - выходим
			if not connected:
				return data

			# измеряем пинг
			ls_ping_timing = await self.get_ping(lite_client)
			if ls_ping_timing is not None:
				data["get_ping"] = f"{int(ls_ping_timing)} ms"

			# получаем текущее время ls
			ls_time = await self.get_time(lite_client)
			if ls_time is not None:
				data["get_time"] = ls_time

			# получаем версию ls
			ls_version = await self.get_version(lite_client)
			if ls_version is not None:
				data["get_version"] = ls_version

			# проверяем скорость запроса update_last_blocks()
			request_time = await self.check_request_time(lite_client)
			if request_time is not None:
				data["request_time"] = f"{int(request_time)} ms"

			# получаем последний блок мастерчейна и список шардов
			try:
				last_mc_block = lite_client.last_mc_block
				if last_mc_block is not None:
					# сохраняем seqno мастерчейна
					data["last_block_seqno_raw"] = last_mc_block.seqno
					# собираем информацию по всем шардам
					shards = await lite_client.get_all_shards_info(last_mc_block)
					shard_map = {}
					for shard in shards:
						shard_id = shard.shard.to_bytes(8, "big", signed=True).hex()
						shard_map[shard_id] = shard.seqno
					data["shards"] = shard_map
			except Exception:
				pass

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

	async def check_request_time(self, lite_client):
		start = time.perf_counter()
		try:
			await lite_client.update_last_blocks()
			end = int((time.perf_counter() - start) * 1000.0)
			return end
		except (Exception,):
			return None, None
	# end define

	@publick
	def daemon(self):
		pass
	# end define
# end class

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
	#end define

	@publick
	def get_console_commands(self):
		commands = list()

		cmd = Dict()
		cmd.cmd = "ls_status"
		cmd.func = self.run_ls_status
		cmd.desc = self.local.translate("ls_status_cmd")
		commands.append(cmd)

		return commands
	#end define

	@publick
	@async_to_sync
	async def run_ls_status(self, args):
		use_exact = "--exact" in args

		self.local.add_log("LS status running, this may take a few minutes")

		start_time = time.perf_counter()
		results = await self.do_ls_status(use_exact)
		end_time = time.perf_counter()

		table = []
		table += [["LS", "IP", "PORT", "Connected", "Connect time", "Request time", "Ping", "Version", "Time", "Last block seqno", "Archive depth"]]
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
				r.get("archive_depth", "-")
			]]
		print_table(table)

		elapsed = end_time - start_time
		if elapsed < 1:
			ms = int(elapsed * 1000)
			self.local.add_log(f"LS status completed in {ms}ms")
			return

		sec = int(elapsed)
		h = sec // 3600
		sec %= 3600
		m = sec // 60
		sec %= 60
		if h > 0:
			formatted = f"{h}h {m}m {sec}s"
		elif m > 0:
			formatted = f"{m}m {sec}s"
		else:
			formatted = f"{sec}s"
		self.local.add_log(f"LS status completed in {formatted}")
	#end define

	async def do_ls_status(self, use_exact):
		servers = await self.get_public_ls_list()
		results = await self._check_all_ls(servers, use_exact=use_exact)

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
	#end define

	async def get_public_ls_list(self):
		client = get_lite_balancer(self.local)
		ls_list = []
		for index, lite_client in enumerate(client._peers):  # noqa
			ls_list.append((index, lite_client))
		return ls_list
	#end define

	async def _check_all_ls(self, servers, use_exact):
		if not servers:
			return []

		tasks = [self.probe_lite_server(index, lite_server, use_exact) for index, lite_server in servers]
		return await asyncio.gather(*tasks, return_exceptions=False)
	#end define

	async def probe_lite_server(self, index, lite_client, use_exact):
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
			#end try
			try:
				now = int(time.time())
				if use_exact:
					archive_depth = await self.check_archive_depth(lite_client, now)
				else:
					archive_depth = await self.check_archive_depth_quick(lite_client, now)
				if archive_depth is not None:
					data["archive_depth"] = archive_depth
			except Exception:
				pass
			#end try
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
				#end
		#end try
	#end define

	async def connect(self, lite_client):
		start = time.perf_counter()
		try:
			await asyncio.wait_for(lite_client.connect(), 1)
			end = int((time.perf_counter() - start) * 1000.0)
			return True, end
		except (Exception,):
			return False, None
		#end try
	#end define

	async def get_version(self, lite_client):
		try:
			result = await lite_client.get_version()
			return result.get("version")
		except (Exception,):
			return None
		#end try
	#end define

	async def get_time(self, lite_client):
		try:
			result = await lite_client.get_time()
			return result.get("now")
		except (Exception,):
			return None
		#end try
	#end define

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
		#end try
	#end define

	async def check_request_time(self, lite_client):
		start = time.perf_counter()
		try:
			await lite_client.update_last_blocks()
			end = int((time.perf_counter() - start) * 1000.0)
			return end
		except (Exception,):
			return None
		#end try
	#end define

	async def check_archive_depth(self, lite_client, now):
		day = 86400
		first_block_utime = 1573822385
		seconds_diff = now - first_block_utime
		max_days = seconds_diff // day

		async def _probe(_days):
			utime = now - _days * day
			try:
				await lite_client.lookup_block(
					wc=-1,
					shard=-(2 ** 63),
					utime=utime,
				)
				return True
			except Exception:
				return False
			#end try
		#end define

		left = 0
		right = max_days
		best_days = 0

		while left <= right:
			mid = (left + right) // 2
			if await _probe(mid):
				best_days = mid
				left = mid + 1
			else:
				right = mid - 1

		years = best_days // 365
		rem = best_days % 365
		months = rem // 30
		days = rem % 30

		parts = []
		if years > 0:
			parts.append(f"{years}y")
		if months > 0:
			parts.append(f"{months}m")
		if days > 0:
			parts.append(f"{days}d")
		if not parts:
			parts.append("-")

		return " ".join(parts)
	#end define

	async def check_archive_depth_quick(self, lite_client, now):
		day = 86400
		time_offsets = [
			("≈ 1d", 1 * day),
			("≈ 3d", 3 * day),
			("≈ 7d", 7 * day),
			("≈ 14d", 14 * day),
			("≈ 1m", 30 * day),
			("≈ 3m", 3 * 30 * day),
			("≈ 6m", 6 * 30 * day),
			("≈ 9m", 9 * 30 * day),
			("≈ 1y", 365 * day),
		]

		async def _probe_utime(utime):
			try:
				await lite_client.lookup_block(
					wc=-1,
					shard=-(2 ** 63),
					utime=utime,
				)
				return True
			except Exception:
				return False
			#end try
		#end define

		tasks = [
			asyncio.create_task(_probe_utime(now - delta))
			for _, delta in time_offsets
		]
		results = await asyncio.gather(*tasks, return_exceptions=False)

		depth_label = None
		for (label, _), is_available in zip(time_offsets, results):
			if is_available:
				depth_label = label
		return depth_label
	#end define

	@publick
	def daemon(self):
		pass
	#end define
#end class

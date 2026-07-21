#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import asyncio
import json
import time
from ton_core import NetworkGlobalID, normalize_hash
from tonutils.clients import LiteBalancer
from tonutils.types import DEFAULT_ADNL_RETRY_POLICY
from utils import get_module_by_name


def get_lite_balancer(local):
	main_module = get_module_by_name(local, "main")
	with open(main_module.global_config_path, "r") as f:
		config = json.load(f)
	return LiteBalancer.from_config(
		NetworkGlobalID.MAINNET,
		config=config,
		connect_timeout=1.2,
		client_connect_timeout=1,
		retry_policy=DEFAULT_ADNL_RETRY_POLICY,
	)
#end define

async def wait_message(client, wallet, msg_hash, end_lt, end_hash, timeout=15):
	start_time = int(time.time())
	while start_time + timeout > int(time.time()):
		await wallet.refresh()
		if wallet.last_transaction_lt == end_lt and wallet.last_transaction_hash == end_hash:
			await asyncio.sleep(1)
			continue
		for transaction in await client.get_transactions(address=wallet.address, limit=10):
			if transaction.lt == end_lt and transaction.cell.hash.hex() == end_hash:
				continue
			if transaction.in_msg and normalize_hash(transaction.in_msg) == msg_hash:
				return True
			for out_msg in transaction.out_msgs:
				if normalize_hash(out_msg) == msg_hash:
					return True
		await asyncio.sleep(1)
	raise Exception("wait_msg error: timeout")
#end define

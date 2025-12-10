#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import asyncio
import json
import time
import types
import pytoniq
from mypylib import Dict
from utils import get_module_by_name

COMMENT_OP = bytes.fromhex("00000000")


def get_lite_balancer(local):
	main_module = get_module_by_name(local, "main")
	with open(main_module.global_config_path, "r") as f:
		config = json.load(f)
	client = pytoniq.LiteBalancer.from_config(config, trust_level=2)
	return client
#end define

def normalize_msg_hash(message):
	if not message.is_external:
		return message.serialize().hash
	cell = (
		pytoniq.begin_cell()
		.store_uint(2, 2)
		.store_address(None)
		.store_address(message.info.dest)
		.store_coins(0)
		.store_bool(False)
		.store_bool(True)
		.store_ref(message.body)
		.end_cell()
	)
	return cell.hash.hex()
#end define

async def wallet_transfer_return_hash(local, wallet, destination, amount, body=None):
	client = get_lite_balancer(local)
	await client.start_up()

	wallet_obj = await pytoniq.WalletV3R2.from_private_key(
		provider=client,
		private_key=wallet.obj.private_key,
	)

	if wallet_obj.account.is_uninitialized():
		seqno = 0
		state_init = wallet_obj.state_init
	else:
		seqno = await wallet_obj.get_seqno()
		state_init = None
	if isinstance(destination, str):
		destination = pytoniq.Address(destination)

	msg = wallet_obj.create_wallet_internal_message(
		destination=pytoniq.Address(destination),
		value=int(amount * 1e9),
		body=body
	)
	body = wallet_obj.raw_create_transfer_msg(
		private_key=wallet_obj.private_key,
		seqno=seqno,
		wallet_id=wallet_obj.wallet_id,
		messages=[msg]
	)
	message = wallet_obj.create_external_msg(
		src=None,
		dest=wallet.obj.address,
		import_fee=0,
		body=body,
		state_init=state_init,
	)
	msg_boc = message.serialize().to_boc()
	msg_hash = normalize_msg_hash(message)

	await client.raw_send_message(msg_boc)
	await client.close_all()
	return msg_hash
#end define

async def get_account(local, *args, **kwargs):
	client = get_lite_balancer(local)
	retries = kwargs.pop("retries", 3)
	async with client:
		for attempt in range(retries):
			try:
				account, shard_account = await client.raw_get_account_state(*args, **kwargs)
				return account, shard_account
			except pytoniq.LiteServerError:
				if attempt == retries - 1:
					raise
				await asyncio.sleep(1)
			#end try
		#end for
#end define

async def wait_message(local, addr, msg_hash, end_lt, end_hash, timeoute=30):
	start_time = int(time.time())

	while True:
		time_now = int(time.time())
		if time_now > start_time + timeoute:
			return Exception("wait_msg error: timeout")
		account, shard_account = await get_account(local, address=addr)
		last_trans_hash = shard_account.last_trans_hash.hex()
		if shard_account.last_trans_lt == end_lt and last_trans_hash == end_hash:
			await asyncio.sleep(3)
			continue

		client = get_lite_balancer(local)
		async with client:
			transactions = await client.get_transactions(address=addr, count=10)

		for transaction in transactions:
			messages = parse_transaction(transaction)
			tr_hash = transaction.cell.hash.hex()
			if transaction.lt == end_lt and tr_hash == end_hash:
				continue
			for message in messages:
				if message.hash == msg_hash:
					return
			#end for
		#end for
		await asyncio.sleep(1)
#end define

async def get_messages(local, addr, count):
	client = get_lite_balancer(local)
	#client = get_lite_balancer(local)
	await client.start_up()
	transactions = await client.get_transactions(address=addr, count=count, only_archive=True)
	await client.close_all()

	messages = list()
	for transaction in transactions:
		messages += parse_transaction(transaction)
	return messages
#end define

def parse_transaction(transaction):
	messages = list()
	message = parse_message(transaction.in_msg, transaction.now)
	messages.append(message)

	for out_msg in transaction.out_msgs:
		message = parse_message(out_msg, transaction.now)
		messages.append(message)
	return messages
#end define

def parse_message(msg, transaction_time):
	message = Dict()
	message.time = transaction_time
	if type(getattr(msg.info, "value_coins", None)) != types.NoneType:
		message.value = msg.info.value_coins
	if type(getattr(msg.info, "src", None)) != types.NoneType:
		message.src = msg.info.src.to_str()
	if type(getattr(msg.info, "dest", None)) != types.NoneType:
		message.dest = msg.info.dest.to_str()
	#message.body = msg.body
	message.comment = parse_comment(msg.body)
	message.hash = msg.serialize().hash.hex()
	return message
#end define

def parse_comment(body):
	if not body.data.startswith(COMMENT_OP):
		return
	#end if

	buffer = body.data[4:]
	for ref in body.refs:
		buffer += parse_comment_ref(ref)
	#end for

	comment = buffer.decode("utf-8")
	return comment
#end define

def parse_comment_ref(ref):
	data = ref.data
	for ref in ref.refs:
		data += parse_comment_ref(ref)
	return data
#end define

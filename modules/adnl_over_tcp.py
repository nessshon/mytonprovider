#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import asyncio
import pytoniq
from mypylib import Dict


COMMENT_OP = bytes.fromhex("00000000")

async def get_messages(addr, count):
	#client = pytoniq.LiteBalancer.from_mainnet_config(trust_level=1)
	client = pytoniq.LiteBalancer.from_testnet_config(trust_level=1)
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
	message = parse_message(transaction.in_msg)
	messages.append(message)

	for out_msg in transaction.out_msgs:
		message = parse_message(out_msg)
		messages.append(message)
	return messages
#end define

def parse_message(msg):
	message = Dict()
	message.time = msg.info.created_at
	message.value = msg.info.value_coins
	message.src = msg.info.src.to_str()
	message.dest = msg.info.dest.to_str()
	#message.body = msg.body
	message.comment = parse_comment(msg.body)
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

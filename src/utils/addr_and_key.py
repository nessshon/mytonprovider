#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import base64
import fastcrc
from nacl.signing import SigningKey


def parse_addr(addr):
	result = parse_addr_b64(addr) or parse_addr_full(addr)
	if result == None:
		raise Exception("parse_addr error: addr not base64 or full address")
	return result
#end define

def parse_addr_b64(addr):
	try:
		workchain, addr_hex, bounceable = do_parse_addr_b64(addr)
		return workchain, addr_hex
	except: pass
#end define

def parse_addr_full(addr):
	try:
		workchain, addr_hex = do_parse_addr_full(addr)
		return workchain, addr_hex
	except: pass
#end define

def do_parse_addr_full(addr_full):
	workchain, addr_hex = addr_full.split(':')
	addr_bytes = parse_hex(addr_hex)
	if addr_bytes == None:
		raise Exception("parse_addr_full error: addr_bytes is none.")
	if len(addr_bytes) != 32:
		raise Exception("parse_addr_full error: addr_bytes is not 32 bytes")
	return workchain, addr_hex
#end define

def do_parse_addr_b64(addr_b64):
	addr_b64 = addr_b64.replace('-', '+')
	addr_b64 = addr_b64.replace('_', '/')
	addr_b64_bytes = addr_b64.encode()
	b64_bytes = base64.b64decode(addr_b64_bytes)
	testnet_int = (b64_bytes[0] & 0x80)
	if testnet_int == 0:
		testnet = False
	else:
		testnet = True
	bounceable_int = (b64_bytes[0] & 0x40)
	if bounceable_int != 0:
		bounceable = False
	else:
		bounceable = True
	#end if

	# get wc and addr
	workchain_bytes = b64_bytes[1:2]
	addr_bytes = b64_bytes[2:34]
	crc_bytes = b64_bytes[34:36]
	crc_data = bytes(b64_bytes[:34])
	crc = int.from_bytes(crc_bytes, "big")
	check_crc = fastcrc.crc16.xmodem(crc_data)
	if crc != check_crc:
		raise Exception("parse_addr_b64 error: crc do not match")
	#end if

	workchain = int.from_bytes(workchain_bytes, "big", signed=True)
	addr_hex = addr_bytes.hex()
	
	return workchain, addr_hex, bounceable
#end define

def parse_key(key):
	result = parse_hex(key) or parse_b64(key)
	if result == None:
		raise Exception("parse_key error: key not base64 or HEX")
	return result
#end define

def parse_hex(hex_str):
	try:
		return bytes.fromhex(hex_str)
	except: pass
#end define

def parse_b64(b64_str):
	try:
		return base64.b64decode(b64_str)
	except: pass
#end define

def addr_to_bytes(addr):
	workchain, addr_hex = parse_addr(addr)
	workchain_bytes = int.to_bytes(workchain, 4, "big", signed=True)
	addr_bytes = bytes.fromhex(addr_hex)
	result = addr_bytes + workchain_bytes
	return result
#end define

def get_pubkey_from_privkey(private_key):
	signing_key = SigningKey(private_key)
	public_key = signing_key.verify_key.encode()
	return public_key
#end define

def split_provider_key(provider_key_b64):
	provider_key = parse_b64(provider_key_b64)
	if provider_key == None:
		raise Exception("split_provider_key error: provider_key not base64")
	if len(provider_key) != 64:
		raise Exception("split_provider_key error: length of provider_key_b64 must be 64 bytes")
	privkey = provider_key[0:32]
	pubkey = provider_key[32:64]
	return privkey, pubkey
#end define

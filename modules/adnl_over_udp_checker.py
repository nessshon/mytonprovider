#!/usr/bin/env python3
# -*- coding: utf_8 -*-

import random
import requests
import base64
from mypylib import Dict

def check_adnl_connection(host, port, pubkey):
	checker_hosts = [
		'45.129.96.53',
		'5.154.181.153',
		'2.56.126.137']
	# 	'91.194.11.68',
	# 	'45.12.134.214',
	# 	'138.124.184.27',
	# 	'103.106.3.171'
	# ]

	random_checker_hosts = random.sample(checker_hosts, k=3)
	for checker_host in random_checker_hosts:
		checker_url = f'http://{checker_host}/adnl_check'
		result, error = do_check_adnl_connection(checker_url, host, port, pubkey)
		if result == True:
			break
	return result, error
#end define

def do_check_adnl_connection(checker_url, host, port, pubkey):
	data = Dict()
	data.host = host
	data.port = port
	data.pubkey = pubkey
	result = None
	error = None
	try:
		timeout = 0.9 *2 + 0.3
		response = requests.post(checker_url, json=data, timeout=timeout)
		response_data = Dict(response.json())
		if response_data.ok:
			result = True
		else:
			result = False
			error = f"Failed to check ADNL connection to local node: host: {host}, port: {port}, pubkey: {pubkey}, error: {response_data.message}"
	except Exception as ex:
		result = False
		error = f'Failed to check ADNL connection to local node: host: {host}, port: {port}, pubkey: {pubkey}, error: {type(ex)}: {ex}'
	return result, error
#end define

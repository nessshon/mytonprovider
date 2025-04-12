import base64
import tonutils
import tonutils.client
import tonutils.wallet
from asgiref.sync import async_to_sync


@async_to_sync
async def async_get_account(client, address):
	return await client.get_raw_account(address)
#end define

@async_to_sync
async def async_deploy(wallet):
	return await wallet.deploy()
#end define

@async_to_sync
async def async_transfer(wallet, destination, amount, body):
	return await wallet.transfer(
		destination=destination,
		amount=amount,
		body=body,
	)
#end define



async def async_main():
	client = tonutils.client.LiteserverClient(is_testnet=True)
	ProviderKey = "/E5o2UZNVbD/4ZoBqA7Qyw4uwIdZz2b4/oKlykzKsDkCcXY4D/Gx1PAv+rhjqgYztJfo8DfceJLFNGveNT0mww=="
	ProviderKey_bytes = base64.b64decode(ProviderKey)
	wallet = tonutils.wallet.WalletV3R2.from_private_key(client, ProviderKey_bytes)

	wallet_addr = wallet.address.to_str()
	wallet_account = await client.get_raw_account(wallet_addr)
	wallet_status = wallet_account.status.value
	wallet_balance = wallet_account.balance /10**9

	print("wallet_addr:", wallet_addr)
	print("wallet_status:", wallet_status)
	print("wallet_balance:", wallet_balance)

	if (wallet_status == "uninit" and wallet_balance > 0.003):
		msg_hash = await wallet.deploy()
		print("deploy msg_hash:", msg_hash)
	#end if

	msg_hash = await wallet.transfer(destination=wallet_addr, amount=0.001, body="my comment")
	print("transfer msg_hash:", msg_hash)
#end define

def main():
	client = tonutils.client.LiteserverClient(is_testnet=True)
	ProviderKey = "/E5o2UZNVbD/4ZoBqA7Qyw4uwIdZz2b4/oKlykzKsDkCcXY4D/Gx1PAv+rhjqgYztJfo8DfceJLFNGveNT0mww=="
	ProviderKey_bytes = base64.b64decode(ProviderKey)
	wallet = tonutils.wallet.WalletV3R2.from_private_key(client, ProviderKey_bytes)

	wallet_addr = wallet.address.to_str()
	wallet_account = async_get_account(client, wallet_addr)
	wallet_status = wallet_account.status.value
	wallet_balance = wallet_account.balance /10**9

	print("wallet_addr:", wallet_addr)
	print("wallet_status:", wallet_status)
	print("wallet_balance:", wallet_balance)


	if (wallet_status == "uninit" and wallet_balance > 0.003):
		msg_hash = async_deploy(wallet)
		print("deploy msg_hash:", msg_hash)
	#end if


	msg_hash = async_transfer(wallet, destination=wallet_addr, amount=0.001, body="my comment")
	print("transfer msg_hash:", msg_hash)
#end define


if __name__ == "__main__":
	#import asyncio
	#asyncio.run(async_main())
	main()
#end if
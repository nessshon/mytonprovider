from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from ton_core import normalize_hash
from tonutils.contracts import WalletV3R2

if TYPE_CHECKING:
    from ton_core import Address, ContractState, PrivateKey
    from tonutils.clients import LiteBalancer


class Wallet:
    def __init__(self, ton_client: LiteBalancer, wallet: WalletV3R2) -> None:
        self._ton_client = ton_client
        self._wallet = wallet

    @property
    def state(self) -> ContractState:
        return self._wallet.state

    @property
    def address(self) -> Address:
        return self._wallet.address

    @property
    def balance(self) -> int:
        return self._wallet.balance

    @classmethod
    async def from_private_key(cls, ton_client: LiteBalancer, private_key: PrivateKey) -> Wallet:
        wallet = WalletV3R2.from_private_key(ton_client, private_key)
        await wallet.refresh()
        return cls(ton_client, wallet)

    @classmethod
    async def from_mnemonic(
        cls,
        ton_client: LiteBalancer,
        words: list[str],
    ) -> tuple[Wallet, PrivateKey]:
        wallet, _pub, private_key, _mnemo = WalletV3R2.from_mnemonic(ton_client, words)
        await wallet.refresh()
        return cls(ton_client, wallet), private_key

    async def refresh(self) -> None:
        await self._wallet.refresh()

    async def send(
        self,
        destination: Address,
        amount: int,
        body: str | None = None,
        timeout: float = 30.0,
    ) -> str:
        end_lt = self._wallet.last_transaction_lt or 0
        message = await self._wallet.transfer(destination=destination, amount=amount, body=body)
        await self._wait_for_confirmation(message.normalized_hash, end_lt, timeout)
        return message.normalized_hash

    async def _wait_for_confirmation(self, target_hash: str, end_lt: int, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            transactions = await self._ton_client.get_transactions(self._wallet.address, limit=10)
            for tx in transactions:
                if tx.lt <= end_lt:
                    continue
                if tx.in_msg is not None and normalize_hash(tx.in_msg) == target_hash:
                    return
                for out_msg in tx.out_msgs:
                    if normalize_hash(out_msg) == target_hash:
                        return
            await asyncio.sleep(1.0)
        raise TimeoutError(f"transaction {target_hash} not confirmed within {timeout}s")

from __future__ import annotations

from mypycli import Startable
from ton_core import NetworkGlobalID
from tonutils.clients import LiteBalancer
from tonutils.types import DEFAULT_ADNL_RETRY_POLICY

from mytonprovider import constants
from mytonprovider.utils import cache_update_available

from ._updatable import SRC_PATH


class StartableMixin(Startable):
    __abstract__ = True

    ton_client: LiteBalancer

    def on_start(self) -> None:
        async def connect_ton_client() -> None:
            self.ton_client = LiteBalancer.from_config(
                config=str(constants.GLOBAL_CONFIG_PATH),
                network=NetworkGlobalID.MAINNET,
                rps_limit=50,
                connect_timeout=1.25,
                client_connect_timeout=1,
                retry_policy=DEFAULT_ADNL_RETRY_POLICY,
            )
            await self.ton_client.connect()

        self.open_async_loop()
        self.run_async(connect_ton_client())
        self.run_task(lambda: cache_update_available(self.name, SRC_PATH))

    def on_stop(self) -> None:
        client = getattr(self, "ton_client", None)
        if client is None:
            self.close_async_loop()
            return

        async def close_ton_client() -> None:
            await client.close()

        self.run_async(close_ton_client())
        self.close_async_loop()

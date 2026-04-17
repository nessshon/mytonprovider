from __future__ import annotations

from mypycli import Startable

from mytonprovider.utils import cache_update_available

from ._updatable import SRC_PATH


class StartableMixin(Startable):
    __abstract__ = True

    def on_start(self) -> None:
        self.run_task(lambda: cache_update_available(self.name, SRC_PATH))

    def on_stop(self) -> None:
        pass

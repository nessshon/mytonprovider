from __future__ import annotations

import time

from mypycli import Daemonic

from .runner import run_benchmark

_CACHE_LIFETIME_SEC = 7 * 24 * 3600


class DaemonicMixin(Daemonic):
    __abstract__ = True

    def on_daemon(self) -> None:
        if self._cache_is_fresh():
            return
        self.run_task(self.refresh_cache)

    def refresh_cache(self) -> None:
        ts = self.app.modules.get("ton-storage")
        storage_path = ts.db.storage_path
        if not storage_path:
            self.logger.warning("benchmark: ton-storage path unavailable; skipping")
            return
        try:
            self.db.last = run_benchmark(storage_path)
        except Exception:
            self.logger.exception("benchmark: run failed")

    def _cache_is_fresh(self) -> bool:
        last = self.db.last
        if last is None:
            return False
        return bool((int(time.time()) - last.timestamp) < _CACHE_LIFETIME_SEC)

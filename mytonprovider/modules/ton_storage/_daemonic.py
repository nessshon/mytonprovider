from __future__ import annotations

import base64
import shutil
import time
from pathlib import Path

from mypycli import Daemonic

from mytonprovider.utils import check_adnl_port, read_config

from .api.client import StorageApi
from .config import StorageConfig

_BAG_GC_INTERVAL_SEC = 24 * 3600
_CHECK_PORT_INTERVAL_SEC = 300
_BAG_ID_HEX_LEN = 64


class DaemonicMixin(Daemonic):
    __abstract__ = True

    def on_daemon(self) -> None:
        self.run_cycle(self.bag_gc, seconds=_BAG_GC_INTERVAL_SEC)
        self.run_cycle(self.check_port, seconds=_CHECK_PORT_INTERVAL_SEC)

    def bag_gc(self) -> None:
        if not self.db.storage_path:
            return
        provider_dir = Path(self.db.storage_path) / "provider"
        if not provider_dir.is_dir():
            return
        try:
            bags = StorageApi(self.db.api_host, self.db.api_port).list_bags()
        except Exception:
            self.logger.warning("bag_gc: failed to fetch bag list", exc_info=True)
            return
        known = {b.bag_id.lower() for b in bags.bags}
        for entry in provider_dir.iterdir():
            if len(entry.name) != _BAG_ID_HEX_LEN:
                continue
            if entry.name.lower() in known:
                continue
            self.logger.warning("bag_gc: removing orphan bag dir %s", entry)
            shutil.rmtree(entry, ignore_errors=True)

    def check_port(self) -> None:
        if not self.db.config_path or not Path(self.db.config_path).exists():
            return
        ok = False
        try:
            cfg = read_config(self.db.config_path, StorageConfig)
            pubkey_hex = _extract_pubkey_hex(cfg.key)
            port = int(cfg.listen_addr.rsplit(":", 1)[-1])
            ok, err = check_adnl_port(cfg.external_ip, port, pubkey_hex)
            if err:
                self.logger.debug("check_port: %s", err)
        except Exception:
            self.logger.warning("check_port failed", exc_info=True)
        self.db.port_reachable = ok
        self.db.port_checked_at = int(time.time())


def _extract_pubkey_hex(key_b64: str) -> str:
    # Daemon stores "base64(private_key || public_key)"; public half is bytes 32-63.
    raw = base64.b64decode(key_b64)
    return raw[32:64].hex().upper()

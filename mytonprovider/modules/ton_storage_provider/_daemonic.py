from __future__ import annotations

import time
from pathlib import Path

from mypycli import Daemonic

from mytonprovider.utils import check_adnl_port, read_config

from .config import ProviderConfig

_CHECK_PORT_INTERVAL_SEC = 300


class DaemonicMixin(Daemonic):
    __abstract__ = True

    def on_daemon(self) -> None:
        self.run_cycle(self.check_port, seconds=_CHECK_PORT_INTERVAL_SEC)

    def check_port(self) -> None:
        if not self.db.config_path or not Path(self.db.config_path).exists():
            return
        ok = False
        try:
            cfg = read_config(self.db.config_path, ProviderConfig)
            pubkey_hex = cfg.adnl_key.public_key.as_hex.upper()
            port = int(cfg.listen_addr.rsplit(":", 1)[-1])
            ok, err = check_adnl_port(cfg.external_ip, port, pubkey_hex)
            if err:
                self.logger.debug("check_port: %s", err)
        except Exception:
            self.logger.warning("check_port failed", exc_info=True)
        self.db.port_reachable = ok
        self.db.port_checked_at = int(time.time())

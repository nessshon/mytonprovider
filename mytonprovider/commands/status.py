from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mytonprovider import constants

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from mytonprovider.modules import ModuleRegistry


def cmd_status(
    app: MyPyClass,
    registry: ModuleRegistry,
    kind: str | None = None,
) -> None:
    """Print module status, or delegate to tonutils monitor.

    :param kind: ``None`` for module statuses, ``"ls"`` for lite-server
        monitor, ``"dht"`` for DHT monitor.
    """
    if kind is not None:
        _run_tonutils_status(kind)
        return
    for module in registry.statusables():
        module.show_status()


def _run_tonutils_status(kind: str) -> None:
    """Delegate to ``tonutils status <kind>`` with the local global config."""
    tonutils_bin = Path(sys.executable).parent / "tonutils"
    if not tonutils_bin.exists():
        raise RuntimeError(
            f"tonutils CLI not found at {tonutils_bin}. "
            "Reinstall mytonprovider to restore the dependency."
        )
    subprocess.run(
        [str(tonutils_bin), "status", kind, "--config", str(constants.GLOBAL_CONFIG_PATH)],
        check=False,
    )

from __future__ import annotations

from typing import TYPE_CHECKING

from mypylib import thr_sleep

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from mytonprovider.modules import ModuleRegistry


def cmd_daemon(app: MyPyClass, registry: ModuleRegistry) -> None:
    """Run as background daemon: start cycles, block main thread.

    :param app: The MyPyClass application instance.
    :param registry: Module registry.
    """
    for startable in registry.startables():
        startable.pre_up()
    for daemonic in registry.daemons():
        app.start_cycle(
            daemonic.daemon,
            name=f"{daemonic.name}-daemon",
            sec=daemonic.daemon_interval,
        )
    thr_sleep()

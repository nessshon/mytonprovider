from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from mypylib import DEBUG

from .interfaces import (
    Commandable,
    Daemonic,
    Installable,
    Startable,
    Statusable,
    Updatable,
)
from .module import BaseModule

if TYPE_CHECKING:
    from mypylib import MyPyClass

T = TypeVar("T", bound=BaseModule)


class ModuleRegistry:
    """Holds module instances and exposes typed capability-based lookup."""

    def __init__(self, modules: list[BaseModule]) -> None:
        self._modules: dict[str, BaseModule] = {m.name: m for m in modules}

    def get(self, name: str) -> BaseModule:
        """Return module by name; raise KeyError if not found."""
        if name not in self._modules:
            raise KeyError(f"Module not found: {name}")
        return self._modules[name]

    def get_by_class(self, cls: type[T]) -> T:
        """Return the first module matching *cls*."""
        for module in self._modules.values():
            if isinstance(module, cls):
                return module
        raise KeyError(f"No module of type {cls.__name__} in registry")

    def all(self, enabled_only: bool = True) -> list[BaseModule]:
        """Return all modules, optionally filtered by ``is_enabled``."""
        if enabled_only:
            return [m for m in self._modules.values() if m.is_enabled]
        return list(self._modules.values())

    def startables(self) -> list[Startable]:
        return [m for m in self.all() if isinstance(m, Startable)]

    def statusables(self) -> list[Statusable]:
        return [m for m in self.all() if isinstance(m, Statusable)]

    def daemons(self) -> list[Daemonic]:
        return [m for m in self.all() if isinstance(m, Daemonic)]

    def installables(self) -> list[Installable]:
        return [m for m in self.all() if isinstance(m, Installable)]

    def updatables(self) -> list[Updatable]:
        return [m for m in self.all() if isinstance(m, Updatable)]

    def commandables(self) -> list[Commandable]:
        return [m for m in self.all() if isinstance(m, Commandable)]


def build_registry(
    app: MyPyClass,
    module_classes: list[type[BaseModule]],
) -> ModuleRegistry:
    """Instantiate modules, bind registry to each, log each init."""
    modules: list[BaseModule] = []
    for cls in module_classes:
        module = cls(app)
        app.add_log(f"Initialized {module.name} module", DEBUG)
        modules.append(module)
    registry = ModuleRegistry(modules)
    for module in modules:
        module.bind_registry(registry)
    return registry

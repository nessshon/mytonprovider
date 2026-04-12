from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from .registry import ModuleRegistry


class BaseModule(ABC):
    """Base class for all mytonprovider modules."""

    name: ClassVar[str]
    mandatory: ClassVar[bool] = False
    service_name: ClassVar[str | None] = None

    def __init__(self, app: MyPyClass) -> None:
        self.app = app
        self._registry: ModuleRegistry | None = None

    def bind_registry(self, registry: ModuleRegistry) -> None:
        """Attach the module registry; called after all modules are created."""
        self._registry = registry

    @property
    def registry(self) -> ModuleRegistry:
        """Return the module registry for cross-module lookups."""
        if self._registry is None:
            raise RuntimeError(f"{self.name}: registry is not bound yet (cannot be used during __init__)")
        return self._registry

    @property
    def is_enabled(self) -> bool:
        """Return True if the module is active."""
        return self.mandatory

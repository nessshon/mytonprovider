from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from .registry import ModuleRegistry


class BaseModule(ABC):
    """Base class for all mytonprovider modules.

    Every concrete module must declare ``name``. Optional metadata
    attributes: ``mandatory``, ``service_name``. Capability methods
    are added by inheriting from interface mixins in
    :mod:`mytonprovider.modules.base.interfaces`.

    After instantiation, ``build_registry`` calls :meth:`bind_registry`
    on each module so cross-module lookups via :attr:`registry` work.
    """

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
        """Return the module registry for cross-module lookups.

        :raises RuntimeError: If called before the registry is bound
            (typically when invoked from ``__init__``).
        """
        if self._registry is None:
            raise RuntimeError(f"{self.name}: registry is not bound yet (cannot be used during __init__)")
        return self._registry

    @property
    def is_enabled(self) -> bool:
        """Return True if the module is active.

        Mandatory modules are always enabled. Optional modules should
        override this property to add runtime checks.
        """
        return self.mandatory

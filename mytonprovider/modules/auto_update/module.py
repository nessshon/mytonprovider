from __future__ import annotations

from typing import ClassVar

from ._installable import InstallableMixin


class AutoUpdateModule(InstallableMixin):
    name: ClassVar[str] = "auto-update"
    label: ClassVar[str] = "Auto Update"
    mandatory: ClassVar[bool] = False

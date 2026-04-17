from __future__ import annotations

from typing import Annotated

from mypycli import DatabaseSchema
from mypycli.types import Color, ColorText, Input
from pydantic import BaseModel

_DEFAULT_STORAGE_PATH = "/var/ton-storage"


class TonStorageInstallParams(BaseModel):
    """User-supplied parameters collected at install time."""

    storage_path: Annotated[
        str,
        Input(prompt="Storage path", default=ColorText(_DEFAULT_STORAGE_PATH, Color.YELLOW)),
    ] = _DEFAULT_STORAGE_PATH


class TonStorageDBSchema(DatabaseSchema):
    """Persistent state for the ton_storage module."""

    storage_path: str = ""
    config_path: str = ""
    api_host: str = "localhost"
    api_port: int = 0
    port_reachable: bool = False
    port_checked_at: int = 0

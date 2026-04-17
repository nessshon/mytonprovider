from __future__ import annotations

from typing import Annotated

from mypycli import DatabaseSchema
from mypycli.types import Color, ColorText, Input
from pydantic import BaseModel

_DEFAULT_STORAGE_COST = 10
_DEFAULT_MAX_BAG_GIGABYTES = 40


class TonStorageProviderInstallParams(BaseModel):
    """User-supplied parameters collected at install time."""

    storage_cost: Annotated[
        int,
        Input(
            prompt="Storage cost (TON per 200GB/month)",
            default=ColorText(str(_DEFAULT_STORAGE_COST), Color.YELLOW),
        ),
    ] = _DEFAULT_STORAGE_COST
    space_to_provide_gigabytes: Annotated[int, Input(prompt="Space to provide (GB)")]
    max_bag_size_gigabytes: Annotated[
        int,
        Input(
            prompt="Max BAG size (GB)",
            default=ColorText(str(_DEFAULT_MAX_BAG_GIGABYTES), Color.YELLOW),
        ),
    ] = _DEFAULT_MAX_BAG_GIGABYTES


class TonStorageProviderDBSchema(DatabaseSchema):
    """Persistent state for the ton_storage_provider module."""

    config_path: str = ""
    is_already_registered: bool = False
    port_reachable: bool = False
    port_checked_at: int = 0

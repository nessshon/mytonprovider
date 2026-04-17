from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Peer(_BaseModel):
    addr: str = ""
    id: str = ""
    upload_speed: int = 0
    download_speed: int = 0


class File(_BaseModel):
    index: int = 0
    name: str = ""
    size: int = 0


class _BagCommon(_BaseModel):
    bag_id: str
    description: str = ""
    downloaded: int = 0
    size: int = 0
    header_size: int = 0
    download_speed: int = 0
    upload_speed: int = 0
    files_count: int = 0
    dir_name: str = ""
    completed: bool = False
    header_loaded: bool = False
    info_loaded: bool = False
    active: bool = False
    seeding: bool = False
    download_all: bool = False


class BagInfo(_BagCommon):
    peers: int = 0


class BagDetails(_BagCommon):
    peers: list[Peer] = Field(default_factory=list)
    bag_pieces_num: int = 0
    has_pieces_mask: str = ""
    files: list[File] = Field(default_factory=list)
    piece_size: int = 0
    bag_size: int = 0
    merkle_hash: str = ""
    path: str = ""


class BagsListResponse(_BaseModel):
    bags: list[BagInfo] = Field(default_factory=list)

    @field_validator("bags", mode="before")
    @classmethod
    def _coerce_null_bags(cls, value: Any) -> Any:
        return value if value is not None else []


class OkResponse(_BaseModel):
    ok: bool

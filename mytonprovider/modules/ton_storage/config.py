from __future__ import annotations

import base64

from pydantic import BaseModel, ConfigDict, Field


class _BaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class StorageConfig(_BaseModel):
    listen_addr: str = Field(alias="ListenAddr")
    external_ip: str = Field(alias="ExternalIP")
    key: str = Field(alias="Key")

    @property
    def pubkey_hex(self) -> str:
        # ``key`` is base64(private_key || public_key); public half is bytes 32-63.
        raw = base64.b64decode(self.key)
        return raw[32:64].hex().upper()

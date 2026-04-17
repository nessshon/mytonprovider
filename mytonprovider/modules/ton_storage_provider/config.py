from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from ton_core import PrivateKey


class _BaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class StorageBackend(_BaseModel):
    base_url: str = Field(alias="BaseURL")
    space_to_provide_megabytes: int = Field(alias="SpaceToProvideMegabytes")


class CronConfig(_BaseModel):
    enabled: bool = Field(alias="Enabled")


class ProviderConfig(_BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    listen_addr: str = Field(alias="ListenAddr")
    external_ip: str = Field(alias="ExternalIP")
    provider_key: PrivateKey = Field(alias="ProviderKey")
    adnl_key: PrivateKey = Field(alias="ADNLKey")
    min_rate_per_mb_day: str = Field(alias="MinRatePerMBDay")
    min_span: int = Field(alias="MinSpan")
    max_span: int = Field(alias="MaxSpan")
    max_bag_size_bytes: int = Field(alias="MaxBagSizeBytes")
    storages: list[StorageBackend] = Field(alias="Storages")
    cron: CronConfig = Field(alias="CRON")

    @field_validator("provider_key", "adnl_key", mode="before")
    @classmethod
    def _parse_private_key(cls, value: Any) -> PrivateKey:
        return value if isinstance(value, PrivateKey) else PrivateKey(value)

    @field_serializer("provider_key", "adnl_key")
    def _serialize_private_key(self, value: PrivateKey) -> str:
        return value.keypair.as_b64

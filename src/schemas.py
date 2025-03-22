from pydantic import BaseModel
import os
from dotenv import load_dotenv


load_dotenv()


class StorageScheme(BaseModel):
    name: str = "TonStorage"
    cmd: str = os.environ.get('STORAGE_CMD')
    host: str
    port: int
    login: str
    password: str
    path: str
    space: int


class StorageProviderScheme(BaseModel):
    name: str = "TonStorageProvider"
    cmd: str = os.environ.get('STORAGE_PROVIDER_CMD')
    # host: str
    # port: int
    # login: str
    # password: str
    cost: str | int
    is_storage: bool


class TunnelProviderScheme(BaseModel):
    name: str = "TonTunnelProvider"
    cmd: str = os.environ.get('TUNNEL_PROVIDER_CMD')
    # host: str
    # port: int
    # login: str
    # password: str
    cost: str | int


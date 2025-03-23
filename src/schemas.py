import json

import os
from dataclasses import dataclass
from dotenv import load_dotenv

from src.utils import get_package_path


load_dotenv()

class Mixins:
    @property
    def name(self) -> str:
        return "Ton" + str(self.__class__.__name__)

    @property
    def cmd(self):
        with open(get_package_path() + "/defaults.json") as f:
            data = json.load(f)
        data.get(self.name.lower() + "_cmd")
        return data.get( self.name.lower() + "_cmd")

@dataclass
class Storage(Mixins):
    host: str
    port: int
    login: str
    password: str
    path: str
    size: int


@dataclass
class StorageProvider(Mixins):
    host: str
    port: int
    login: str
    password: str
    cost: str | int

@dataclass
class TunnelProvider(Mixins):
    host: str
    port: int
    login: str
    password: str
    cost: str | int





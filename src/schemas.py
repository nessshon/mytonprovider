from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()


class TonStorageScheme(BaseModel):
    launcher: str = os.environ.get('DEFAULT_COMMAND_LAUNCHER')
    api: bool
    auth: bool
    api_port: int
    api_login: str
    api_pass: str
    go_path: bool

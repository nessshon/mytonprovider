from inquirer import Confirm, Text, List, Path
from src.utils import get_disk_free_space
import os

utils_selection = List(
    name="utils_selection",
    message="Выберете утилиту",
    choices=["ton_storage", "ton_storage_provider", "ton_tunnel_provider"]
)
storage_path = Path(
    name="storage_path",
    message=f"Ввод места хранения файлов ton_storage (по умолчанию: {os.environ.get('DEFAULT_STORAGE_PATH')})",
    default=os.environ.get('DEFAULT_STORAGE_PATH'),
)
storage_disk_space = Text(
    name="storage_disk_space",
    message="Какой размер от свободного размера диска может занять ton_storage в ГБ? (по умолчанию 90% от диска)",
    default=get_disk_free_space() * 0.9
)
storage_cost = Text(
    name="storage_cost",
    message="Сколько будет стоить хранения 1 Гб/мес ?"
)
traffic_cost = Text(
    name="traffic_cost",
    message="Сколько будет стоить 1 Гб трафика сети?"
)
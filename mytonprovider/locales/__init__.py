from pathlib import Path
from typing import Literal, cast

from mypycli import Translator

__all__ = ["_", "lang", "translator"]

_ = translator = Translator(Path(__file__).parent)


def lang() -> Literal["en", "ru", "zh"]:
    return cast("Literal['en', 'ru', 'zh']", translator.language or "en")

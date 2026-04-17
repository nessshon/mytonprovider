from __future__ import annotations

from typing import ClassVar

from ._commandable import CommandableMixin
from ._daemonic import DaemonicMixin
from .schemas import BenchmarkDBSchema


class BenchmarkModule(DaemonicMixin, CommandableMixin):
    name: ClassVar[str] = "benchmark"
    label: ClassVar[str] = "Benchmark"
    mandatory: ClassVar[bool] = True

    db_schema: ClassVar[type[BenchmarkDBSchema]] = BenchmarkDBSchema

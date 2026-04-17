from __future__ import annotations

from typing import ClassVar

from ._daemonic import DaemonicMixin
from .schemas import StatisticsDBSchema


class StatisticsModule(DaemonicMixin):
    name: ClassVar[str] = "statistics"
    label: ClassVar[str] = "Statistics"
    mandatory: ClassVar[bool] = True

    db_schema: ClassVar[type[StatisticsDBSchema]] = StatisticsDBSchema

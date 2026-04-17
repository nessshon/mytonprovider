from __future__ import annotations

from mypycli import DatabaseSchema


class TelemetryDBSchema(DatabaseSchema):
    """Persistent state for the telemetry module.

    ``enabled`` is a runtime toggle flipped via the ``telemetry enable/disable``
    commands — independent from the module's installation state. ``password_hash``
    is the base64-SHA256 link identifier that ties this provider to an account
    on mytonprovider.org (optional; sent empty when unset).
    """

    enabled: bool = False
    password_hash: str = ""
    last_sent_at: int = 0
    last_benchmark_sent_at: int = 0
    telemetry_url: str | None = None
    benchmark_url: str | None = None

from __future__ import annotations

import gzip
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .models import BenchmarkPayload, TelemetryPayload


class TelemetryApi:
    def __init__(self, telemetry_url: str, benchmark_url: str, timeout: float = 5.0) -> None:
        self._telemetry_url = telemetry_url
        self._benchmark_url = benchmark_url
        self._timeout = timeout

    def send_telemetry(self, payload: TelemetryPayload) -> None:
        self._post_gzip(self._telemetry_url, payload.model_dump_json())

    def send_benchmark(self, payload: BenchmarkPayload) -> None:
        self._post_gzip(self._benchmark_url, payload.model_dump_json())

    def _post_gzip(self, url: str, body_json: str) -> None:
        data = gzip.compress(body_json.encode("utf-8"))
        headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
        response = requests.post(url, data=data, headers=headers, timeout=self._timeout)
        response.raise_for_status()

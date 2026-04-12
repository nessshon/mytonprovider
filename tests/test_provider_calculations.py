"""Tests for TonStorageProviderModule pricing formulas."""
from __future__ import annotations

import pytest

from mytonprovider.modules.ton_storage_provider import (
    MAX_SPAN_HARD_LIMIT,
    MIN_MAX_SPAN_SEC,
    STORAGE_COST_REFERENCE_GB,
    TonStorageProviderModule,
)

_calc_max_span = TonStorageProviderModule._calculate_max_span
_calc_rate = TonStorageProviderModule._calculate_min_rate_per_mb_day


class TestCalculateMaxSpan:
    def test_typical_cost(self):
        result = _calc_max_span(10)
        assert result == 6_635_520
        assert result > MIN_MAX_SPAN_SEC

    def test_high_cost_clamps_to_min(self):
        assert _calc_max_span(1000) == MIN_MAX_SPAN_SEC

    def test_very_low_cost_clamps_to_hard_limit(self):
        assert _calc_max_span(0.001) == MAX_SPAN_HARD_LIMIT

    def test_zero_cost_raises(self):
        """Zero cost is guarded by input validation, but function itself doesn't handle it."""
        with pytest.raises(ZeroDivisionError):
            _calc_max_span(0)


class TestCalculateMinRatePerMbDay:
    def test_typical_cost(self):
        assert _calc_rate(10) == "0.000001628"

    def test_high_cost(self):
        assert _calc_rate(1000) == "0.000162760"

    def test_round_trip_with_storage_cost(self):
        """rate -> storage_cost must recover the original price."""
        original_cost = 10
        rate_str = _calc_rate(original_cost)
        recovered = round(float(rate_str) * STORAGE_COST_REFERENCE_GB * 1024 * 30, 2)
        assert recovered == original_cost


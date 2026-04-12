"""Non-interactive init argument validation tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from mytonprovider.commands.init import (
    _validate_max_bag_size,
    _validate_non_interactive,
    _validate_positive_int,
)


class TestAlwaysRequired:
    def test_missing_modules(self):
        with pytest.raises(RuntimeError, match="--modules"):
            _validate_non_interactive(
                selected_modules=None,
                storage_path=Path("/data"),
                storage_cost=10,
                space_to_provide_gigabytes=100,
                max_bag_size_gigabytes=40,
                auto_update_enabled=True,
            )

    def test_missing_auto_update(self):
        with pytest.raises(RuntimeError, match="--auto-update"):
            _validate_non_interactive(
                selected_modules=("ton-storage",),
                storage_path=Path("/data"),
                storage_cost=None,
                space_to_provide_gigabytes=None,
                max_bag_size_gigabytes=None,
                auto_update_enabled=None,
            )


class TestTonStorageRequirements:
    def test_ton_storage_without_path(self):
        with pytest.raises(RuntimeError, match="--storage-path"):
            _validate_non_interactive(
                selected_modules=("ton-storage",),
                storage_path=None,
                storage_cost=None,
                space_to_provide_gigabytes=None,
                max_bag_size_gigabytes=None,
                auto_update_enabled=False,
            )

    def test_ton_storage_happy_path(self):
        # Should not raise
        _validate_non_interactive(
            selected_modules=("ton-storage",),
            storage_path=Path("/data"),
            storage_cost=None,
            space_to_provide_gigabytes=None,
            max_bag_size_gigabytes=None,
            auto_update_enabled=False,
        )


class TestTonStorageProviderRequirements:
    def test_missing_all_provider_fields(self):
        with pytest.raises(RuntimeError) as exc_info:
            _validate_non_interactive(
                selected_modules=("ton-storage-provider",),
                storage_path=None,
                storage_cost=None,
                space_to_provide_gigabytes=None,
                max_bag_size_gigabytes=None,
                auto_update_enabled=False,
            )
        msg = str(exc_info.value)
        assert "--storage-cost" in msg
        assert "--provider-space" in msg
        assert "--max-bag-size" in msg

    def test_provider_renamed_flag_is_reported(self):
        """Regression guard: the error message must say --provider-space, not --space."""
        with pytest.raises(RuntimeError) as exc_info:
            _validate_non_interactive(
                selected_modules=("ton-storage-provider",),
                storage_path=None,
                storage_cost=10,
                space_to_provide_gigabytes=None,
                max_bag_size_gigabytes=40,
                auto_update_enabled=False,
            )
        msg = str(exc_info.value)
        assert "--provider-space" in msg
        assert "--space" not in msg.replace("--provider-space", "")

    def test_happy_full_install(self):
        _validate_non_interactive(
            selected_modules=("ton-storage", "ton-storage-provider", "telemetry"),
            storage_path=Path("/data"),
            storage_cost=10,
            space_to_provide_gigabytes=100,
            max_bag_size_gigabytes=40,
            auto_update_enabled=True,
        )


class TestOptionalModule:
    def test_telemetry_only_no_storage_fields_needed(self):
        """If only telemetry is selected (optional), no storage/provider fields required."""
        _validate_non_interactive(
            selected_modules=("telemetry",),
            storage_path=None,
            storage_cost=None,
            space_to_provide_gigabytes=None,
            max_bag_size_gigabytes=None,
            auto_update_enabled=False,
        )


class TestValidatePositiveInt:
    def test_valid(self):
        assert _validate_positive_int("1") is True
        assert _validate_positive_int("100") is True

    def test_zero_rejected(self):
        assert _validate_positive_int("0") is False

    def test_negative_rejected(self):
        assert _validate_positive_int("-1") is False

    def test_non_numeric_rejected(self):
        assert _validate_positive_int("abc") is False
        assert _validate_positive_int("") is False

    def test_float_string_rejected(self):
        assert _validate_positive_int("1.5") is False


class TestValidateMaxBagSize:
    def test_valid_boundaries(self):
        assert _validate_max_bag_size("1") is True
        assert _validate_max_bag_size("1024") is True

    def test_below_minimum(self):
        assert _validate_max_bag_size("0") is False

    def test_above_maximum(self):
        assert _validate_max_bag_size("1025") is False

    def test_non_numeric_rejected(self):
        assert _validate_max_bag_size("abc") is False


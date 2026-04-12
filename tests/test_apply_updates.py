"""Tests for apply_updates orchestration in commands/update.py."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from mytonprovider.commands.update import apply_updates
from mytonprovider.types import Channel, UpdateStatus


def _make_module(name="dummy", check_result=None, raises=None):
    mod = MagicMock()
    mod.name = name
    mod.format_version = MagicMock(return_value="v1.0.0 (abcdef0)")
    mod.build_update_args = MagicMock(return_value=["echo", "upd"])
    if raises is not None:
        mod.check_update = MagicMock(side_effect=raises)
    else:
        mod.check_update = MagicMock(return_value=check_result)
    return mod


def _make_channel(ref="v1.1.0"):
    return Channel(author="a", repo="r", ref=ref, ref_kind="tag")


class TestCheckOnly:
    def test_available_becomes_checked(self):
        app = MagicMock()
        target = _make_channel("v1.1.0")
        mod = _make_module(
            check_result=UpdateStatus(available=True, target=target, target_commit=None)
        )
        results = apply_updates(app, [mod], check_only=True)
        assert len(results) == 1
        assert results[0].action == "checked"
        assert "v1.1.0" in results[0].message

    def test_up_to_date_becomes_checked_up_to_date(self):
        app = MagicMock()
        mod = _make_module(
            check_result=UpdateStatus(available=False, target=None, target_commit=None)
        )
        results = apply_updates(app, [mod], check_only=True)
        assert results[0].action == "checked"


class TestUpToDate:
    def test_not_available_skipped(self):
        app = MagicMock()
        mod = _make_module(
            check_result=UpdateStatus(available=False, target=None, target_commit=None)
        )
        results = apply_updates(app, [mod])
        assert results[0].action == "up_to_date"
        mod.build_update_args.assert_not_called()


class TestInstall:
    def test_successful_update(self):
        app = MagicMock()
        target = _make_channel("v1.1.0")
        mod = _make_module(
            check_result=UpdateStatus(available=True, target=target, target_commit=None)
        )
        with patch("mytonprovider.commands.update.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            results = apply_updates(app, [mod])
        assert results[0].action == "updated"
        mod.build_update_args.assert_called_once_with(target)
        run.assert_called_once()

    def test_subprocess_failure(self):
        app = MagicMock()
        target = _make_channel("v1.1.0")
        mod = _make_module(
            check_result=UpdateStatus(available=True, target=target, target_commit=None)
        )
        with patch("mytonprovider.commands.update.subprocess.run") as run:
            run.side_effect = subprocess.CalledProcessError(returncode=2, cmd=["x"])
            results = apply_updates(app, [mod])
        assert results[0].action == "failed"
        assert "exit 2" in results[0].message

    def test_os_error(self):
        app = MagicMock()
        target = _make_channel("v1.1.0")
        mod = _make_module(
            check_result=UpdateStatus(available=True, target=target, target_commit=None)
        )
        with patch("mytonprovider.commands.update.subprocess.run") as run:
            run.side_effect = OSError("command not found")
            results = apply_updates(app, [mod])
        assert results[0].action == "failed"


class TestErrors:
    def test_check_update_exception_becomes_failed(self):
        app = MagicMock()
        mod = _make_module(raises=RuntimeError("network down"))
        results = apply_updates(app, [mod])
        assert results[0].action == "failed"
        assert "network down" in results[0].message

    def test_batch_continues_after_failure(self):
        """If one module's check_update fails, others still process."""
        app = MagicMock()
        mod_fail = _make_module(name="fail", raises=RuntimeError("bang"))
        mod_ok = _make_module(
            name="ok",
            check_result=UpdateStatus(available=False, target=None, target_commit=None),
        )
        results = apply_updates(app, [mod_fail, mod_ok])
        assert len(results) == 2
        assert results[0].action == "failed"
        assert results[1].action == "up_to_date"


class TestOverride:
    def test_override_applied(self):
        app = MagicMock()
        override = _make_channel("v99.0.0")
        mod = _make_module()  # check_update should NOT be called
        with patch("mytonprovider.commands.update.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            results = apply_updates(app, [mod], override=override)
        assert results[0].action == "updated"
        mod.check_update.assert_not_called()
        mod.build_update_args.assert_called_once_with(override)


class TestAuto:
    def test_auto_skips_immature_release(self):
        app = MagicMock()
        target = _make_channel("v1.1.0")
        mod = _make_module(
            check_result=UpdateStatus(
                available=True, target=target, target_commit=None, mature=False,
            )
        )
        results = apply_updates(app, [mod], auto=True)
        assert results[0].action == "up_to_date"
        mod.build_update_args.assert_not_called()

    def test_auto_installs_mature_release(self):
        app = MagicMock()
        target = _make_channel("v1.1.0")
        mod = _make_module(
            check_result=UpdateStatus(
                available=True, target=target, target_commit=None, mature=True,
            )
        )
        with patch("mytonprovider.commands.update.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            results = apply_updates(app, [mod], auto=True)
        assert results[0].action == "updated"

    def test_manual_installs_immature_release(self):
        app = MagicMock()
        target = _make_channel("v1.1.0")
        mod = _make_module(
            check_result=UpdateStatus(
                available=True, target=target, target_commit=None, mature=False,
            )
        )
        with patch("mytonprovider.commands.update.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            results = apply_updates(app, [mod])
        assert results[0].action == "updated"


class TestForce:
    def test_force_reinstall_current_when_up_to_date(self):
        app = MagicMock()
        current = _make_channel("v1.0.0")
        mod = _make_module(
            check_result=UpdateStatus(available=False, target=None, target_commit=None)
        )
        mod.get_installed_version = MagicMock(
            return_value=MagicMock(channel=current)
        )
        with patch("mytonprovider.commands.update.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            results = apply_updates(app, [mod], force=True)
        assert results[0].action == "updated"
        # Should have used current channel as target
        mod.build_update_args.assert_called_once_with(current)

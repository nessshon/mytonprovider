"""Tests for Updatable.check_update cooldown and version comparison."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from mytonprovider.modules.core import Updatable
from mytonprovider.types import Channel, InstalledVersion, UpdateStatus


class _DummyUpdatable(Updatable):
    """Minimal concrete subclass for testing check_update logic."""
    name = "dummy"
    github_author = "nessshon"
    github_repo = "mytonprovider"
    default_version = "v1.0.0"

    def __init__(self, installed: InstalledVersion) -> None:
        # Skip parent __init__ (which needs app)
        self._installed = installed
        self._update_status = None

    def get_installed_version(self) -> InstalledVersion:
        return self._installed

    def build_update_args(self, target):
        return ["echo", "test"]


def _make_installed(ref="v1.0.0", ref_kind="tag", commit="a" * 40):
    return InstalledVersion(
        channel=Channel(
            author="nessshon",
            repo="mytonprovider",
            ref=ref,
            ref_kind=ref_kind,
        ),
        commit=commit,
    )


def _iso_days_ago(days: int) -> str:
    ts = datetime.now(timezone.utc) - timedelta(days=days)
    return ts.isoformat().replace("+00:00", "Z")


class TestTagMode:
    def test_same_version_not_available(self):
        mod = _DummyUpdatable(_make_installed("v1.0.0"))
        with patch(
            "mytonprovider.modules.core.interfaces.get_github_release",
            return_value={"tag_name": "v1.0.0", "published_at": _iso_days_ago(30)},
        ):
            status = mod.check_update()
        assert status.available is False
        assert status.target is None

    def test_newer_version_available_after_cooldown(self):
        mod = _DummyUpdatable(_make_installed("v1.0.0"))
        with patch(
            "mytonprovider.modules.core.interfaces.get_github_release",
            return_value={"tag_name": "v1.1.0", "published_at": _iso_days_ago(8)},
        ):
            status = mod.check_update()
        assert status.available is True
        assert status.mature is True
        assert status.target is not None
        assert status.target.ref == "v1.1.0"

    def test_newer_version_within_cooldown(self):
        """New version exists but <= 7 days old → available but not mature."""
        mod = _DummyUpdatable(_make_installed("v1.0.0"))
        with patch(
            "mytonprovider.modules.core.interfaces.get_github_release",
            return_value={"tag_name": "v1.1.0", "published_at": _iso_days_ago(3)},
        ):
            status = mod.check_update()
        assert status.available is True
        assert status.mature is False
        assert status.target is not None
        assert status.target.ref == "v1.1.0"

    def test_cooldown_boundary_exact_7_days(self):
        """Boundary: exactly 7 days → available but NOT mature (strict >)."""
        mod = _DummyUpdatable(_make_installed("v1.0.0"))
        with patch(
            "mytonprovider.modules.core.interfaces.get_github_release",
            return_value={"tag_name": "v1.1.0", "published_at": _iso_days_ago(7)},
        ):
            status = mod.check_update()
        assert status.available is True
        assert status.mature is False

    def test_missing_tag_name_raises(self):
        mod = _DummyUpdatable(_make_installed("v1.0.0"))
        with patch(
            "mytonprovider.modules.core.interfaces.get_github_release",
            return_value={"published_at": _iso_days_ago(10)},
        ):
            with pytest.raises(RuntimeError, match="tag_name"):
                mod.check_update()


class TestBranchMode:
    def test_same_commit_not_available(self):
        mod = _DummyUpdatable(_make_installed("master", "branch", commit="abc" * 13 + "a"))
        with patch(
            "mytonprovider.modules.core.interfaces.fetch_remote_branch_head",
            return_value=("abc" * 13 + "a", 30),
        ):
            status = mod.check_update()
        assert status.available is False

    def test_new_commit_after_cooldown(self):
        mod = _DummyUpdatable(_make_installed("master", "branch", commit="old" * 13 + "a"))
        with patch(
            "mytonprovider.modules.core.interfaces.fetch_remote_branch_head",
            return_value=("new" * 13 + "b", 10),
        ):
            status = mod.check_update()
        assert status.available is True
        assert status.mature is True
        assert status.target_commit.startswith("new")

    def test_new_commit_within_cooldown(self):
        mod = _DummyUpdatable(_make_installed("master", "branch", commit="old" * 13 + "a"))
        with patch(
            "mytonprovider.modules.core.interfaces.fetch_remote_branch_head",
            return_value=("new" * 13 + "b", 3),
        ):
            status = mod.check_update()
        assert status.available is True
        assert status.mature is False

    def test_new_commit_boundary_exact_7(self):
        mod = _DummyUpdatable(_make_installed("master", "branch", commit="old" * 13 + "a"))
        with patch(
            "mytonprovider.modules.core.interfaces.fetch_remote_branch_head",
            return_value=("new" * 13 + "b", 7),
        ):
            status = mod.check_update()
        assert status.available is True
        assert status.mature is False  # > 7 strict


class TestFormatVersion:
    def test_tag_format(self):
        mod = _DummyUpdatable(_make_installed("v1.2.3", "tag", commit="a1b2c3d" + "0" * 33))
        assert mod.format_version() == "v1.2.3 (a1b2c3d)"

    def test_branch_format(self):
        mod = _DummyUpdatable(_make_installed("master", "branch", commit="a1b2c3d" + "0" * 33))
        assert mod.format_version() == "master@a1b2c3d"

    def test_fork_repo_suffix(self):
        installed = InstalledVersion(
            channel=Channel(
                author="otheruser",
                repo="mytonprovider",
                ref="v1.0.0",
                ref_kind="tag",
            ),
            commit="abc1234" + "0" * 33,
        )
        mod = _DummyUpdatable(installed)
        assert "[otheruser/mytonprovider]" in mod.format_version()

    def test_missing_install_state_returns_dev(self):
        class NoInstall(_DummyUpdatable):
            def get_installed_version(self):
                raise RuntimeError("not installed")
        mod = NoInstall(_make_installed())
        assert mod.format_version() == "dev"


class TestIsoDaysAgo:
    def test_z_suffix(self):
        ts = _iso_days_ago(5)
        assert ts.endswith("Z")
        result = _DummyUpdatable._iso_days_ago(ts)
        assert result == 5

    def test_offset_suffix(self):
        ts = datetime.now(timezone.utc) - timedelta(days=10)
        result = _DummyUpdatable._iso_days_ago(ts.isoformat())
        assert result == 10


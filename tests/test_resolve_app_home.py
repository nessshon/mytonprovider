"""Unit tests for mytonprovider.utils.resolve_app_home.

Covers the cascade branches:
1. Non-root → Path.home()
2. Root + SUDO_USER → pwd.getpwnam
3. Root + DOAS_USER → pwd.getpwnam
4. Root, no env vars, no symlink → Path.home() (fallback)
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mytonprovider.utils import resolve_app_home


@pytest.fixture
def clear_env(monkeypatch):
    """Clear SUDO_USER / DOAS_USER for deterministic tests."""
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.delenv("DOAS_USER", raising=False)
    return monkeypatch


class TestNonRoot:
    def test_non_root_returns_path_home(self, clear_env):
        with patch("mytonprovider.utils.os.geteuid", return_value=1000), \
             patch("mytonprovider.utils.Path.home", return_value=Path("/home/alice")):
            assert resolve_app_home() == Path("/home/alice")

    def test_non_root_ignores_sudo_user(self, clear_env, monkeypatch):
        """SUDO_USER set but euid != 0 → don't touch it."""
        monkeypatch.setenv("SUDO_USER", "ghost")
        with patch("mytonprovider.utils.os.geteuid", return_value=1000), \
             patch("mytonprovider.utils.Path.home", return_value=Path("/home/alice")):
            assert resolve_app_home() == Path("/home/alice")


class TestRootWithSudoUser:
    def test_sudo_user_resolved(self, clear_env, monkeypatch):
        monkeypatch.setenv("SUDO_USER", "provider")
        fake_pw = SimpleNamespace(pw_dir="/home/provider")
        with patch("mytonprovider.utils.os.geteuid", return_value=0), \
             patch("mytonprovider.utils.pwd.getpwnam", return_value=fake_pw) as getpwnam:
            assert resolve_app_home() == Path("/home/provider")
            getpwnam.assert_called_once_with("provider")

    def test_sudo_user_root_is_ignored(self, clear_env, monkeypatch):
        """SUDO_USER=root is meaningless, should fall through."""
        monkeypatch.setenv("SUDO_USER", "root")
        with patch("mytonprovider.utils.os.geteuid", return_value=0), \
             patch("mytonprovider.utils.Path.home", return_value=Path("/root")), \
             patch("mytonprovider.utils.pwd.getpwnam") as getpwnam:
            with patch("mytonprovider.utils.constants.APP_NAME", "mytonprovider-test-bin-xyz"):
                assert resolve_app_home() == Path("/root")
                getpwnam.assert_not_called()

    def test_sudo_user_empty_is_ignored(self, clear_env, monkeypatch):
        monkeypatch.setenv("SUDO_USER", "")
        with patch("mytonprovider.utils.os.geteuid", return_value=0), \
             patch("mytonprovider.utils.Path.home", return_value=Path("/root")), \
             patch("mytonprovider.utils.constants.APP_NAME", "nonexistent-xyz"):
            assert resolve_app_home() == Path("/root")

    def test_sudo_user_keyerror_falls_through(self, clear_env, monkeypatch):
        """SUDO_USER set but user doesn't exist → try next strategy."""
        monkeypatch.setenv("SUDO_USER", "ghost")
        with patch("mytonprovider.utils.os.geteuid", return_value=0), \
             patch("mytonprovider.utils.pwd.getpwnam", side_effect=KeyError("ghost")), \
             patch("mytonprovider.utils.Path.home", return_value=Path("/root")), \
             patch("mytonprovider.utils.constants.APP_NAME", "nonexistent-xyz"):
            # Falls through to symlink lookup (which fails) → Path.home()
            assert resolve_app_home() == Path("/root")


class TestRootWithDoasUser:
    def test_doas_user_resolved(self, clear_env, monkeypatch):
        monkeypatch.setenv("DOAS_USER", "provider")
        fake_pw = SimpleNamespace(pw_dir="/home/provider")
        with patch("mytonprovider.utils.os.geteuid", return_value=0), \
             patch("mytonprovider.utils.pwd.getpwnam", return_value=fake_pw):
            assert resolve_app_home() == Path("/home/provider")

    def test_sudo_user_takes_precedence(self, clear_env, monkeypatch):
        monkeypatch.setenv("SUDO_USER", "alice")
        monkeypatch.setenv("DOAS_USER", "bob")
        with patch("mytonprovider.utils.os.geteuid", return_value=0), \
             patch("mytonprovider.utils.pwd.getpwnam") as getpwnam:
            getpwnam.side_effect = lambda u: SimpleNamespace(pw_dir=f"/home/{u}")
            assert resolve_app_home() == Path("/home/alice")
            getpwnam.assert_called_once_with("alice")


class TestRootFallback:
    def test_fallback_no_env_no_symlink(self, clear_env, monkeypatch):
        """Root, no env, no valid symlink → Path.home() fallback."""
        with patch("mytonprovider.utils.os.geteuid", return_value=0), \
             patch("mytonprovider.utils.Path.home", return_value=Path("/root")), \
             patch("mytonprovider.utils.constants.APP_NAME", "nonexistent-xyz-abc"):
            assert resolve_app_home() == Path("/root")

"""Argument validation tests for cmd_update."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mytonprovider.commands.update import cmd_update


def _make_ctx():
    app = MagicMock()
    registry = MagicMock()
    return app, registry


class TestMutualExclusion:
    def test_check_and_force_mutually_exclusive(self):
        app, registry = _make_ctx()
        with pytest.raises(RuntimeError, match="mutually exclusive"):
            cmd_update(
                app, registry,
                target=None, ref=None, author=None, repo=None,
                force=True, check=True,
            )


class TestRefRequirements:
    def test_ref_requires_target(self):
        app, registry = _make_ctx()
        with pytest.raises(RuntimeError, match="--ref requires a target"):
            cmd_update(
                app, registry,
                target=None, ref="v1.2.3", author=None, repo=None,
                force=False, check=False,
            )

    def test_author_without_ref_rejected(self):
        app, registry = _make_ctx()
        with pytest.raises(RuntimeError, match="--author/--repo require --ref"):
            cmd_update(
                app, registry,
                target="mytonprovider", ref=None, author="someone", repo=None,
                force=False, check=False,
            )

    def test_repo_without_ref_rejected(self):
        app, registry = _make_ctx()
        with pytest.raises(RuntimeError, match="--author/--repo require --ref"):
            cmd_update(
                app, registry,
                target="mytonprovider", ref=None, author=None, repo="somefork",
                force=False, check=False,
            )

"""Tests for pure helpers in mytonprovider.utils."""
from __future__ import annotations

import pytest

from mytonprovider.utils import (
    get_threshold_color,
    is_newer_version,
    parse_revision_kind,
)


class TestIsNewerVersion:
    def test_strictly_newer(self):
        assert is_newer_version("v1.0.0", "v1.0.1") is True

    def test_minor_bump(self):
        assert is_newer_version("v1.0.5", "v1.1.0") is True

    def test_major_bump(self):
        assert is_newer_version("v1.9.9", "v2.0.0") is True

    def test_equal_not_newer(self):
        assert is_newer_version("v1.2.3", "v1.2.3") is False

    def test_older_not_newer(self):
        assert is_newer_version("v1.2.3", "v1.2.0") is False

    def test_no_v_prefix(self):
        assert is_newer_version("1.0.0", "1.0.1") is True

    def test_mixed_prefix(self):
        assert is_newer_version("v1.0.0", "1.0.1") is True
        assert is_newer_version("1.0.0", "v1.0.1") is True

    def test_pre_release_stripped(self):
        """Pre-release and build suffixes are stripped — v2.0.0-rc1 == v2.0.0."""
        assert is_newer_version("v2.0.0-rc1", "v2.0.0") is False

    def test_build_suffix_stripped(self):
        assert is_newer_version("v1.0.0+build1", "v1.0.0+build2") is False


class TestParseRevisionKind:
    def test_semver_is_tag(self):
        assert parse_revision_kind("v1.2.3") == "tag"
        assert parse_revision_kind("1.2.3") == "tag"
        assert parse_revision_kind("v0.0.0") == "tag"

    def test_semver_with_prerelease(self):
        assert parse_revision_kind("v1.2.3-rc1") == "tag"
        assert parse_revision_kind("v1.0.0+build42") == "tag"

    def test_branch_names(self):
        assert parse_revision_kind("master") == "branch"
        assert parse_revision_kind("main") == "branch"
        assert parse_revision_kind("dev-feature-x") == "branch"

    def test_ambiguous(self):
        """A branch called 'v1' (not full semver) → branch."""
        assert parse_revision_kind("v1") == "branch"


class TestGetThresholdColor:
    def test_none_value(self):
        assert get_threshold_color(None, 50, "more") == "n/a"
        assert get_threshold_color(None, 50, "less") == "n/a"

    def test_less_good_is_green(self):
        result = get_threshold_color(10, 50, "less")
        assert "\x1b[32m" in result

    def test_less_bad_is_red(self):
        result = get_threshold_color(80, 50, "less")
        assert "\x1b[31m" in result

    def test_more_good_is_green(self):
        result = get_threshold_color(80, 50, "more")
        assert "\x1b[32m" in result

    def test_more_bad_is_red(self):
        result = get_threshold_color(10, 50, "more")
        assert "\x1b[31m" in result

    def test_boundary_equal_less_is_green(self):
        result = get_threshold_color(50, 50, "less")
        assert "\x1b[32m" in result

    def test_boundary_equal_more_is_green(self):
        result = get_threshold_color(50, 50, "more")
        assert "\x1b[32m" in result

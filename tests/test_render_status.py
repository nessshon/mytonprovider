"""Tests for render_status_block and _visible_len in utils.py."""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from mytonprovider.types import StatusBlock
from mytonprovider.utils import _visible_len, render_status_block


class TestVisibleLen:
    def test_plain_text(self) -> None:
        assert _visible_len("hello") == 5

    def test_ansi_colored(self) -> None:
        colored = "\033[32mhello\033[0m"
        assert _visible_len(colored) == 5

    def test_multiple_codes(self) -> None:
        text = "\033[1m\033[31mERROR\033[0m ok"
        assert _visible_len(text) == 8

    def test_empty(self) -> None:
        assert _visible_len("") == 0

    def test_unicode(self) -> None:
        assert _visible_len("✓ working") == 9
        assert _visible_len("⚡ update") == 8


class TestRenderHeader:
    def test_header_contains_name_and_version(self) -> None:
        block = StatusBlock(name="mymod", version="v1.0.0")
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        output = buf.getvalue()
        assert "mymod" in output
        assert "v1.0.0" in output
        assert "●" in output


class TestRenderCard:
    def test_card_lines_printed(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            card=[("Key", "ABC123"), ("Path", "/var/data")],
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        output = buf.getvalue()
        assert "Key:" in output
        assert "ABC123" in output
        assert "Path:" in output
        assert "/var/data" in output

    def test_card_labels_aligned(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            card=[("Short", "val1"), ("Much longer label", "val2")],
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        lines = buf.getvalue().splitlines()
        card_lines = [line for line in lines if "val1" in line or "val2" in line]
        assert len(card_lines) == 2
        pos1 = card_lines[0].index("val1")
        pos2 = card_lines[1].index("val2")
        assert pos1 == pos2


class TestRenderBox:
    def test_box_borders(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            rows=[("Label", "Value")],
            service_text="✓ ok",
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        output = buf.getvalue()
        assert "╭" in output
        assert "╰" in output
        assert "│" in output

    def test_service_text_in_top_border(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            rows=[("CPU", "1.0")],
            service_text="✓ working",
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        lines = buf.getvalue().splitlines()
        top_border = next(line for line in lines if "╭" in line)
        assert "status" in top_border
        assert "working" in top_border

    def test_empty_separator_row(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            rows=[("A", "1"), ("", ""), ("B", "2")],
            service_text="ok",
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        lines = buf.getvalue().splitlines()
        box_lines = [line for line in lines if line.startswith("│")]
        blank_lines = [
            line for line in box_lines
            if line.strip() == "│" or line.replace(" ", "").replace("│", "") == ""
        ]
        assert len(blank_lines) >= 1

    def test_rows_aligned(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            rows=[("Short", "val1"), ("Much longer label", "val2")],
            service_text="ok",
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        lines = buf.getvalue().splitlines()
        val_lines = [line for line in lines if "val1" in line or "val2" in line]
        assert len(val_lines) == 2
        pos1 = val_lines[0].index("val1")
        pos2 = val_lines[1].index("val2")
        assert pos1 == pos2

    def test_right_border_aligned(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            rows=[("Short", "a"), ("Very long label here", "longer value text")],
            service_text="ok",
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        lines = buf.getvalue().splitlines()
        box_lines = [
            line for line in lines
            if "│" in line and "╭" not in line and "╰" not in line
        ]
        widths = {_visible_len(line) for line in box_lines if line.strip()}
        assert len(widths) == 1, f"Box lines have inconsistent visible widths: {widths}"


class TestRenderUpdate:
    def test_update_text_shown(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            rows=[("A", "1")],
            service_text="ok",
            update_text="Update available: v2.0",
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        output = buf.getvalue()
        assert "⚡" in output
        assert "Update available: v2.0" in output

    def test_no_update_text(self) -> None:
        block = StatusBlock(
            name="mod",
            version="v1.0",
            rows=[("A", "1")],
            service_text="ok",
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        output = buf.getvalue()
        assert "⚡" not in output


class TestRenderNoRows:
    def test_no_rows_no_box(self) -> None:
        block = StatusBlock(name="mod", version="v1.0")
        buf = StringIO()
        with patch("sys.stdout", buf):
            render_status_block(block)
        output = buf.getvalue()
        assert "╭" not in output
        assert "mod" in output

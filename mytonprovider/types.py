"""Central data types for mytonprovider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


RefKind = Literal["tag", "branch"]


@dataclass(frozen=True)
class Channel:
    """A versioning target: author/repo@ref."""

    author: str
    repo: str
    ref: str
    ref_kind: RefKind


@dataclass(frozen=True)
class InstalledVersion:
    """Currently installed channel plus its resolved commit."""

    channel: Channel
    commit: str

    @property
    def commit_short(self) -> str:
        """Seven-character commit SHA (UI convention, matches GitHub)."""
        return self.commit[:7]


@dataclass(frozen=True)
class UpdateStatus:
    """Result of an update check."""

    available: bool
    target: Channel | None
    target_commit: str | None
    mature: bool = True


@dataclass(frozen=True)
class StatusBlock:
    """Structured status data for a single module, rendered by ``render_status_block``."""

    name: str
    version: str
    card: list[tuple[str, str]] = field(default_factory=list)
    rows: list[tuple[str, str]] = field(default_factory=list)
    service_text: str = ""
    update_text: str | None = None


class Command(NamedTuple):
    """A console command exposed by a module."""

    name: str
    func: Callable[[list[str]], None]
    description: str


@dataclass(frozen=True)
class InstallContext:
    """Context passed to ``Installable.install()`` during init wizard."""

    user: str
    selected_modules: tuple[str, ...]
    storage_path: Path | None = None
    storage_cost: int | None = None
    space_to_provide_gigabytes: int | None = None
    max_bag_size_gigabytes: int | None = None

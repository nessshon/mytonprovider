"""Central data types for mytonprovider.

Kept free of internal imports so every other module can depend on this
one without introducing cycles. Behavior/orchestration types that live
next to their only consumer (e.g. ``UpdateResult`` in
``commands/update.py``) are intentionally excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


RefKind = Literal["tag", "branch"]


@dataclass(frozen=True)
class Channel:
    """A versioning target: where we install/update from.

    :param author: GitHub repository owner.
    :param repo: GitHub repository name.
    :param ref: Git ref — either a tag name (``"v1.2.3"``) or a branch
        name (``"master"``).
    :param ref_kind: Whether :attr:`ref` is a tag or a branch.
        Classified once at construction time to avoid repeated network
        calls downstream.
    """

    author: str
    repo: str
    ref: str
    ref_kind: RefKind


@dataclass(frozen=True)
class InstalledVersion:
    """Currently installed channel plus its resolved commit.

    :param channel: The channel this install tracks.
    :param commit: Full 40-char commit SHA resolved at install time.
    """

    channel: Channel
    commit: str

    @property
    def commit_short(self) -> str:
        """Seven-character commit SHA (UI convention, matches GitHub)."""
        return self.commit[:7]


@dataclass(frozen=True)
class UpdateStatus:
    """Result of an update check.

    :param available: Whether an update can be applied now (newer
        version found *and* cooldown elapsed).
    :param target: The channel the update would switch to, or ``None``
        if the installed state is already up to date. May be set with
        ``available=False`` when a newer version was found but is still
        within the cooldown window.
    :param target_commit: Full commit SHA of :attr:`target`, or ``None``
        when there is no target.
    """

    available: bool
    target: Channel | None
    target_commit: str | None


class Command(NamedTuple):
    """A console command exposed by a module."""

    name: str
    func: Callable[[list[str]], None]
    description: str


@dataclass(frozen=True)
class InstallContext:
    """Context passed to ``Installable.install()`` during init wizard.

    ``user`` and ``selected_modules`` are always required. Module-specific
    fields are optional — each module that needs them is responsible for
    validating presence (or ``cmd_init`` must guarantee it before calling).
    """

    user: str
    selected_modules: tuple[str, ...]
    storage_path: Path | None = None
    storage_cost: int | None = None
    space_to_provide_gigabytes: int | None = None
    max_bag_size_gigabytes: int | None = None

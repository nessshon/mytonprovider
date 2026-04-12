from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, cast

from mypylib import fetch_remote_branch_head, get_github_release

from mytonprovider.types import Channel, InstalledVersion, UpdateStatus
from mytonprovider.utils import is_newer_version

from .module import BaseModule

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from mytonprovider.types import Command, InstallContext


class Startable(BaseModule):
    """Module with startup initialization logic."""

    @abstractmethod
    def pre_up(self) -> None: ...


class Statusable(BaseModule):
    """Module that can print its own status."""

    @abstractmethod
    def show_status(self) -> None: ...


class Daemonic(BaseModule):
    """Module with a periodic background task."""

    daemon_interval: ClassVar[int]

    @abstractmethod
    def daemon(self) -> None: ...


class Installable(BaseModule):
    """Module that knows how to install itself."""

    @abstractmethod
    def install(self, context: InstallContext) -> None: ...


class Updatable(BaseModule):
    """Module that tracks its installed version and can update itself."""

    github_author: ClassVar[str]
    github_repo: ClassVar[str]
    default_version: ClassVar[str]
    update_cooldown_days: ClassVar[int] = 7

    def __init__(self, app: MyPyClass) -> None:
        super().__init__(app)
        self._update_status: UpdateStatus | None = None

    @classmethod
    def default_channel(cls) -> Channel:
        """Return the default channel for first install."""
        return Channel(
            author=cls.github_author,
            repo=cls.github_repo,
            ref=cls.default_version,
            ref_kind="tag",
        )

    @abstractmethod
    def get_installed_version(self) -> InstalledVersion:
        """Return currently installed state (offline, no network)."""

    @abstractmethod
    def build_update_args(self, target: Channel) -> list[str]:
        """Return subprocess args to install/update to *target* channel."""

    def check_update(self) -> UpdateStatus:
        """Compare installed state against GitHub, applying cooldown."""
        installed = self.get_installed_version()
        if installed.channel.ref_kind == "tag":
            return self._check_release_update(installed)
        return self._check_branch_update(installed)

    def _check_release_update(self, installed: InstalledVersion) -> UpdateStatus:
        channel = installed.channel
        release = get_github_release(channel.author, channel.repo)

        latest_tag = release.get("tag_name")
        if not latest_tag:
            raise RuntimeError(
                f"{channel.author}/{channel.repo}: latest release has no tag_name"
            )
        latest_tag = str(latest_tag)

        if not is_newer_version(channel.ref, latest_tag):
            return UpdateStatus(available=False, target=None, target_commit=None)

        published_at = release.get("published_at")
        if not published_at:
            raise RuntimeError(
                f"{channel.author}/{channel.repo}: release {latest_tag} has no published_at"
            )
        age_days = self._iso_days_ago(str(published_at))

        target = Channel(
            author=channel.author,
            repo=channel.repo,
            ref=latest_tag,
            ref_kind="tag",
        )
        return UpdateStatus(
            available=True,
            target=target,
            target_commit=None,
            mature=age_days > self.update_cooldown_days,
        )

    def _check_branch_update(self, installed: InstalledVersion) -> UpdateStatus:
        channel = installed.channel
        sha, days_ago = cast(
            "tuple[str, int]",
            fetch_remote_branch_head(
                channel.author, channel.repo, channel.ref, with_days_ago=True,
            ),
        )
        if sha == installed.commit:
            return UpdateStatus(available=False, target=None, target_commit=None)

        return UpdateStatus(
            available=True,
            target=channel,
            target_commit=sha,
            mature=days_ago > self.update_cooldown_days,
        )

    @staticmethod
    def _iso_days_ago(iso_timestamp: str) -> int:
        """Return days elapsed since an ISO 8601 timestamp."""
        normalized = iso_timestamp.replace("Z", "+00:00")
        published = datetime.fromisoformat(normalized)
        return (datetime.now(timezone.utc) - published).days

    def format_version(self) -> str:
        """Return a single-line version string for status display."""
        try:
            installed = self.get_installed_version()
        except RuntimeError:
            return "dev"

        channel = installed.channel
        if channel.ref_kind == "tag":
            text = f"{channel.ref} ({installed.commit_short})"
        else:
            text = f"{channel.ref}@{installed.commit_short}"

        if channel.author != self.github_author or channel.repo != self.github_repo:
            text += f" [{channel.author}/{channel.repo}]"
        return text


class Commandable(BaseModule):
    """Module exposing console commands."""

    @abstractmethod
    def get_commands(self) -> list[Command]: ...

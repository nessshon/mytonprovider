from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, cast

from mypylib import bcolors, fetch_remote_branch_head, get_github_release

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
    """Module that tracks its installed version and can update itself.

    Every module declares its "home" repo via ClassVars
    (:attr:`github_author`, :attr:`github_repo`, :attr:`default_version`).
    The default channel is always a pinned tag — reproducible first
    install, updates follow whichever channel is detected at runtime
    (tag or branch, possibly from a fork).

    Subclasses implement two hooks:
      - :meth:`get_installed_version` — offline read of current state.
      - :meth:`build_update_args` — subprocess args to switch to a
        target channel.

    The mixin provides uniform :meth:`check_update` (GitHub API + 7-day
    cooldown) and :meth:`format_version` (display).
    """

    github_author: ClassVar[str]
    github_repo: ClassVar[str]
    default_version: ClassVar[str]
    update_cooldown_days: ClassVar[int] = 7

    def __init__(self, app: MyPyClass) -> None:
        super().__init__(app)
        self._update_status: UpdateStatus | None = None

    @classmethod
    def default_channel(cls) -> Channel:
        """Return the default channel for first install (always tag mode)."""
        return Channel(
            author=cls.github_author,
            repo=cls.github_repo,
            ref=cls.default_version,
            ref_kind="tag",
        )

    @abstractmethod
    def get_installed_version(self) -> InstalledVersion:
        """Return currently installed state.

        Must be offline (no network). Raises :class:`RuntimeError` if
        the package is not installed or state cannot be determined.
        """

    @abstractmethod
    def build_update_args(self, target: Channel) -> list[str]:
        """Return subprocess args to install/update to *target* channel."""

    def check_update(self) -> UpdateStatus:
        """Compare installed state against GitHub; apply cooldown.

        Branches on installed channel's ``ref_kind``:
          - ``tag``    → ``/releases/latest``, semver compare,
            cooldown by ``published_at``.
          - ``branch`` → ``/branches/{ref}``, SHA compare,
            cooldown by commit author date.

        :raises RuntimeError: On network or API failures (caller logs & skips).
        """
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
            available=age_days > self.update_cooldown_days,
            target=target,
            target_commit=None,
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
            available=days_ago > self.update_cooldown_days,
            target=channel,
            target_commit=sha,
        )

    @staticmethod
    def _iso_days_ago(iso_timestamp: str) -> int:
        """Return days elapsed since an ISO 8601 timestamp.

        Accepts timestamps with trailing ``Z`` (as returned by the
        GitHub API). Raises :class:`ValueError` on malformed input.
        """
        normalized = iso_timestamp.replace("Z", "+00:00")
        published = datetime.fromisoformat(normalized)
        return (datetime.now(timezone.utc) - published).days

    def format_version(self) -> str:
        """Single-line version string for status display.

        Pure, offline — safe to call on every ``show_status`` tick.
        Returns ``"dev"`` if installed state cannot be read (editable
        install, package not installed).

        Formats:
          - tag mode:    ``v1.0.0 (a1b2c3d)``
          - branch mode: ``master@a1b2c3d``
          - non-default repo gets ``[author/repo]`` suffix.
        """
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

    def _print_version(self) -> None:
        """Print the version line ('Package version: ...') with update marker.

        Internal display helper called from :meth:`show_status` of
        concrete Statusable + Updatable modules. Uses the
        ``package_version`` and ``update_available`` translation keys.
        Reads cached :attr:`_update_status` (populated by a background
        update check) — if ``None`` (not yet checked, or check failed),
        only the version is shown.

        Subclasses may override to customize the version line format.
        """
        version_text = bcolors.yellow_text(self.format_version())
        text = self.app.translate("package_version").format(version_text)
        status = self._update_status
        if status and status.available and status.target:
            update_text = self.app.translate("update_available").format(status.target.ref)
            text += ", " + bcolors.magenta_text(update_text)
        print(text)


class Commandable(BaseModule):
    """Module exposing console commands."""

    @abstractmethod
    def get_commands(self) -> list[Command]: ...

from __future__ import annotations

from mypycli import Updatable
from mypycli.utils.github import GitError, LocalGitRepo

from mytonprovider import constants
from mytonprovider.utils import run_root_script

from ._installable import SERVICE_NAME

SRC_PATH = constants.SRC_DIR / constants.TONUTILS_STORAGE_REPO


class UpdatableMixin(Updatable):
    __abstract__ = True

    @property
    def version(self) -> str:
        try:
            return LocalGitRepo(str(SRC_PATH)).info.version
        except GitError:
            return "unknown"

    def check_update(self) -> str | None:
        try:
            repo = LocalGitRepo(str(SRC_PATH))
            if repo.has_updates(by="version"):
                return repo.remote.info.latest_version
            return None
        except GitError:
            self.logger.warning("update check failed", exc_info=True)
            return None

    def on_update(self) -> None:
        repo = LocalGitRepo(str(SRC_PATH))
        latest = repo.remote.info.latest_version
        if latest is None:
            return
        helper = constants.SCRIPTS_DIR / "install_go_package.sh"
        run_root_script(
            [
                str(helper),
                "-a",
                constants.TONUTILS_STORAGE_AUTHOR,
                "-r",
                constants.TONUTILS_STORAGE_REPO,
                "-b",
                latest,
                "-e",
                constants.TONUTILS_STORAGE_ENTRY,
                "-s",
                SERVICE_NAME,
            ]
        )

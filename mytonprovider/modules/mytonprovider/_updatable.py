from __future__ import annotations

from mypycli import Updatable
from mypycli.utils.github import GitError, LocalGitRepo

from mytonprovider import constants
from mytonprovider.utils import run_root_script

from ._installable import SERVICE_NAME

SRC_PATH = constants.SRC_DIR / constants.APP_NAME


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
            self.logger.warning("version check failed", exc_info=True)
            return None

    def on_update(self) -> None:
        repo = LocalGitRepo(str(SRC_PATH))
        latest = repo.remote.info.latest_version
        if latest is None:
            return
        repo.update(ref=latest)
        helper = constants.SCRIPTS_DIR / "install_py_package.sh"
        run_root_script(
            [
                str(helper),
                "-u",
                constants.INSTALL_USER,
                "-v",
                str(constants.VENV_DIR),
                "-p",
                str(SRC_PATH),
                "-s",
                SERVICE_NAME,
            ]
        )

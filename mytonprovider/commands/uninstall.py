from __future__ import annotations

import os
import subprocess
import sys

from mytonprovider import constants


def _resolve_uninstall_user() -> str | None:
    """Try to detect the target user for per-user cleanup."""
    for env_var in ("SUDO_USER", "DOAS_USER", "USER"):
        value = os.environ.get(env_var)
        if value and value != "root":
            return value
    return None


def cmd_uninstall(*, yes: bool = False) -> None:
    """Run the uninstall.sh script with appropriate flags."""
    script = constants.SCRIPTS_DIR / "uninstall.sh"
    if not script.exists():
        print(f"Error: uninstall script not found at {script}", file=sys.stderr)
        sys.exit(1)

    cmd: list[str] = ["bash", str(script)]

    user = _resolve_uninstall_user()
    if user:
        cmd += ["-u", user]

    if yes:
        cmd.append("-y")

    is_root = os.geteuid() == 0
    if not is_root:
        cmd = ["sudo"] + cmd

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except KeyboardInterrupt:
        sys.exit(130)

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final

import psutil
from mypylib import (
    DEBUG,
    INFO,
    add2systemd,
    bcolors,
    color_print,
    get_cpu_count,
    get_load_avg,
    get_request,
    get_service_status,
    get_service_uptime,
    time2human,
)

from mytonprovider import constants
from mytonprovider.modules.core import (
    Commandable,
    Daemonic,
    Installable,
    Startable,
    Statusable,
    Updatable,
)
from mytonprovider.modules.statistics import StatisticsModule
from mytonprovider.types import Command, StatusBlock
from mytonprovider.utils import (
    get_threshold_color,
    read_pep610_version,
    render_status_block,
)

if TYPE_CHECKING:
    from mytonprovider.types import Channel, InstallContext, InstalledVersion

# Threshold values used to color-code status output
NET_LOAD_BORDERLINE_MBIT: Final[int] = 300
DISK_LOAD_BORDERLINE_PERCENT: Final[int] = 80
MEMORY_USAGE_BORDERLINE_GB: Final[int] = 100
MEMORY_USAGE_PERCENT_BORDERLINE: Final[int] = 90

# Auto-update daemon tick interval. Matches the old updater.py cycle
# (86400 = once per day); per-module cooldown (Updatable) still gates
# actual installs at >7 days.
AUTO_UPDATE_INTERVAL_SEC: Final[int] = 86400


class MytonproviderModule(Startable, Statusable, Daemonic, Installable, Updatable, Commandable):
    """Main mytonprovider daemon: systemd service, status display, self-updates, and install wizard."""

    name = "mytonprovider"
    service_name = "mytonproviderd"
    mandatory = True
    daemon_interval = AUTO_UPDATE_INTERVAL_SEC

    github_author = constants.MYTONPROVIDER_AUTHOR
    github_repo = constants.MYTONPROVIDER_REPO
    default_version = constants.MYTONPROVIDER_VERSION

    def get_commands(self) -> list[Command]:
        return [
            Command(
                name="auto_update",
                func=self._cmd_toggle_auto_update,
                description=self.app.translate("auto_update_cmd"),
            ),
        ]

    def pre_up(self) -> None:
        """Start background update check in a separate thread."""
        self.app.start_thread(self._check_update_background)

    def daemon(self) -> None:
        """Apply updates for all Updatable modules if auto-update is enabled."""
        if not self.app.db.get("auto_update_enabled"):
            return
        # Local import breaks the commands ↔ modules cycle at load time.
        from mytonprovider.commands.update import apply_updates

        updatables = self.registry.updatables()
        if not updatables:
            return
        results = apply_updates(self.app, updatables, auto=True)
        self_updated = any(
            r.module == self.name and r.action == "updated" for r in results
        )
        if self_updated:
            self.app.add_log(
                f"{self.name}: self-update applied, exiting for systemd restart",
                INFO,
            )
            self.app.exit()

    def show_status(self) -> None:
        block = StatusBlock(
            name=self.name,
            version=self.format_version(),
            rows=[
                self._get_cpu_load(),
                self._get_ram_load(),
                self._get_swap_load(),
                self._get_network_load(),
                self._get_disks_load(),
            ],
            service_text=self._get_service_text(),
            update_text=self._get_update_text(),
        )
        render_status_block(block)

    def get_installed_version(self) -> InstalledVersion:
        return read_pep610_version(constants.APP_NAME)

    def build_update_args(self, target: Channel) -> list[str]:
        import sys

        pip_path = Path(sys.executable).parent / "pip"
        return [
            str(pip_path),
            "install",
            "--upgrade",
            "--quiet",
            f"git+https://github.com/{target.author}/{target.repo}@{target.ref}",
        ]

    def install(self, context: InstallContext) -> None:
        """Set up config, symlinks, sudoers, and systemd unit."""
        print(f"Installing {self.name} module")

        if os.geteuid() != 0:
            raise RuntimeError(f"{self.name}: install must be run as root (use sudo)")

        try:
            user_info = pwd.getpwnam(context.user)
        except KeyError as exc:
            raise RuntimeError(f"{self.name}: user {context.user!r} does not exist") from exc
        user_home = Path(user_info.pw_dir)

        work_dir = user_home / constants.WORK_DIR
        venv_path = user_home / constants.VENV_PATH
        venv_exe = venv_path / "bin" / constants.APP_NAME

        global_config_path = constants.GLOBAL_CONFIG_PATH
        global_config_dir = global_config_path.parent

        if not venv_exe.exists():
            raise RuntimeError(
                f"{self.name}: {constants.APP_NAME} executable not found at {venv_exe}. "
                "Run install.sh first to create venv and install the package."
            )

        work_dir.mkdir(parents=True, exist_ok=True)
        global_config_dir.mkdir(parents=True, exist_ok=True)

        global_config_path.write_text(get_request(constants.GLOBAL_CONFIG_URL))

        self.app.db.config.logLevel = "info"
        self.app.db.config.isLocaldbSaving = True
        self.app.db.config.isStartOnlyOneProcess = False
        self.app.db.install_user = context.user
        self.app.save()

        subprocess.run(
            [
                "chown",
                "-R",
                f"{context.user}:{context.user}",
                str(venv_path),
                str(work_dir),
                str(global_config_dir),
            ],
            check=True,
        )

        for name, target in (
            (constants.APP_NAME, venv_exe),
            ("tonutils", venv_path / "bin" / "tonutils"),
        ):
            link = Path("/usr/local/bin") / name
            if link.exists() or link.is_symlink():
                link.unlink()
            if target.exists():
                link.symlink_to(target)

        self._write_sudoers(context.user)

        add2systemd(
            name=self.service_name,
            user=context.user,
            start=f"/usr/bin/env PYTHONUNBUFFERED=1 {venv_exe} --daemon",
            force=True,
        )

    @staticmethod
    def _write_sudoers(user: str) -> None:
        """Grant passwordless sudo for ``install_go_package.sh`` to the install user."""
        bash_path = shutil.which("bash") or "/bin/bash"
        script_path = constants.SCRIPTS_DIR / "install_go_package.sh"
        sudoers_path = constants.SUDOERS_PATH

        content = (
            f"{user} ALL=(root) NOPASSWD: "
            f"{bash_path} {script_path} *\n"
        )

        sudoers_path.write_text(content)
        sudoers_path.chmod(0o440)

        result = subprocess.run(
            ["visudo", "-c", "-f", str(sudoers_path)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            sudoers_path.unlink(missing_ok=True)
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"sudoers validation failed (removed {sudoers_path}): {stderr}"
            )

    def _check_update_background(self) -> None:
        """Query GitHub for a newer version in a background thread."""
        try:
            self._update_status = self.check_update()
        except (RuntimeError, ValueError) as exc:
            self.app.add_log(f"Failed to check for updates: {exc}", DEBUG)
            self._update_status = None

    def _cmd_toggle_auto_update(self, _args: list[str]) -> None:
        """Toggle auto-update on/off."""
        current = bool(self.app.db.get("auto_update_enabled"))
        self.app.db.auto_update_enabled = not current
        self.app.save()
        state = bcolors.green_text("ON") if not current else bcolors.red_text("OFF")
        color_print(f"auto update: {state}")

    def _get_cpu_load(self) -> tuple[str, str]:
        cpu_count = get_cpu_count()
        avg1, avg5, avg15 = get_load_avg()
        load1 = get_threshold_color(avg1, cpu_count, logic="less")
        load5 = get_threshold_color(avg5, cpu_count, logic="less")
        load15 = get_threshold_color(avg15, cpu_count, logic="less")
        return f"CPU load [{bcolors.yellow_text(cpu_count)}]", f"{load1}, {load5}, {load15}"

    def _get_ram_load(self) -> tuple[str, str]:
        vm = psutil.virtual_memory()
        used = get_threshold_color(round(vm.used / 10**9, 2), MEMORY_USAGE_BORDERLINE_GB, logic="less", ending=" GB")
        pct = get_threshold_color(vm.percent, MEMORY_USAGE_PERCENT_BORDERLINE, logic="less", ending="%")
        return ("RAM", f"{used}, {pct}")

    def _get_swap_load(self) -> tuple[str, str]:
        sm = psutil.swap_memory()
        used = get_threshold_color(round(sm.used / 10**9, 2), MEMORY_USAGE_BORDERLINE_GB, logic="less", ending=" GB")
        pct = get_threshold_color(sm.percent, MEMORY_USAGE_PERCENT_BORDERLINE, logic="less", ending="%")
        return "Swap", f"{used}, {pct}"

    def _get_network_load(self) -> tuple[str, str]:
        stats = self.registry.get_by_class(StatisticsModule)
        load1, load5, load15 = stats.get_net_load_avg()
        t1 = get_threshold_color(load1, NET_LOAD_BORDERLINE_MBIT, logic="less")
        t5 = get_threshold_color(load5, NET_LOAD_BORDERLINE_MBIT, logic="less")
        t15 = get_threshold_color(load15, NET_LOAD_BORDERLINE_MBIT, logic="less")
        return ("Network load average (Mbit/s)", f"{t1}, {t5}, {t15}")

    def _get_disks_load(self) -> tuple[str, str]:
        stats = self.registry.get_by_class(StatisticsModule)
        disks_load_avg = stats.get_disks_load_avg()
        disks_load_percent_avg = stats.get_disks_load_percent_avg()
        entries: list[str] = []
        for disk_name, data in disks_load_avg.items():
            speed = bcolors.green_text(data[2])
            pct = get_threshold_color(
                disks_load_percent_avg[disk_name][2],
                DISK_LOAD_BORDERLINE_PERCENT,
                logic="less",
                ending="%",
            )
            entries.append(
                f"{bcolors.cyan}{disk_name}:[{bcolors.default}"
                f"{speed}, {pct}"
                f"{bcolors.cyan}]{bcolors.endc}"
            )
        return ("Disks load (MB/s)", ", ".join(entries))

    def _get_service_text(self) -> str:
        is_active = get_service_status(self.service_name)
        uptime = get_service_uptime(self.service_name) or 0
        if is_active:
            indicator = bcolors.green_text("✓")
            status = bcolors.green_text("working")
            return f"{indicator} {status}, uptime {bcolors.green_text(time2human(uptime))}"
        return f"{bcolors.red_text('✗')} {bcolors.red_text('not working')}"

    def _get_update_text(self) -> str | None:
        status = self._update_status
        if status and status.available and status.target:
            return f"Update available: {status.target.ref}"
        return None


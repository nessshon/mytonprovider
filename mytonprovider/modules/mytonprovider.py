from __future__ import annotations

import os
import pwd
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mypylib import (
    DEBUG,
    INFO,
    add2systemd,
    bcolors,
    color_print,
    get_cpu_count,
    get_load_avg,
    get_ram_info,
    get_request,
    get_service_status,
    get_service_uptime,
    get_swap_info,
    time2human,
)

from mytonprovider import constants
from mytonprovider.modules.core import (
    Daemonic,
    Installable,
    Startable,
    Statusable,
    Updatable,
)
from mytonprovider.modules.statistics import StatisticsModule
from mytonprovider.utils import (
    get_service_status_color,
    get_threshold_color,
    read_pep610_version,
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


class MytonproviderModule(Startable, Statusable, Daemonic, Installable, Updatable):
    """Main mytonprovider daemon: systemd service, status display, self-updates, and install wizard."""

    name = "mytonprovider"
    service_name = "mytonproviderd"
    mandatory = True
    daemon_interval = AUTO_UPDATE_INTERVAL_SEC

    github_author = constants.MYTONPROVIDER_AUTHOR
    github_repo = constants.MYTONPROVIDER_REPO
    default_version = constants.MYTONPROVIDER_VERSION

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
        results = apply_updates(self.app, updatables)
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
        color_print("{cyan}===[ Main status ]==={endc}")
        self._print_module_name()
        self._print_cpu_load()
        self._print_network_load()
        self._print_disks_load()
        self._print_memory_load()
        self._print_service_status()
        self._print_version()

    def get_installed_version(self) -> InstalledVersion:
        return read_pep610_version(constants.APP_NAME)

    def build_update_args(self, target: Channel) -> list[str]:
        return [
            "pip",
            "install",
            "--upgrade",
            f"git+https://github.com/{target.author}/{target.repo}@{target.ref}",
        ]

    def install(self, context: InstallContext) -> None:
        """Set up config, symlinks, sudoers, and systemd unit."""
        self.app.add_log(f"Installing {self.name} module")

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

        self.app.db.config.logLevel = "debug"
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
            start=f"{venv_exe} --daemon",
            force=True,
        )

        self.app.add_log(f"Starting {self.service_name} service")
        self.app.start_service(self.service_name)

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

    def _print_module_name(self) -> None:
        module_name = bcolors.yellow_text(self.name)
        text = self.app.translate("module_name").format(module_name)
        print(text)

    def _print_cpu_load(self) -> None:
        cpu_count = get_cpu_count()
        cpu_load1, cpu_load5, cpu_load15 = get_load_avg()
        cpu_count_text = bcolors.yellow_text(cpu_count)
        cpu_load1_text = get_threshold_color(cpu_load1, cpu_count, logic="less")
        cpu_load5_text = get_threshold_color(cpu_load5, cpu_count, logic="less")
        cpu_load15_text = get_threshold_color(cpu_load15, cpu_count, logic="less")
        text = self.app.translate("cpu_load").format(cpu_count_text, cpu_load1_text, cpu_load5_text, cpu_load15_text)
        print(text)

    def _print_memory_load(self) -> None:
        ram = get_ram_info()
        swap = get_swap_info()
        ram_usage_text = get_threshold_color(ram.used, MEMORY_USAGE_BORDERLINE_GB, logic="less", ending=" Gb")
        ram_percent_text = get_threshold_color(ram.percent, MEMORY_USAGE_PERCENT_BORDERLINE, logic="less", ending="%")
        swap_usage_text = get_threshold_color(swap.used, MEMORY_USAGE_BORDERLINE_GB, logic="less", ending=" Gb")
        swap_percent_text = get_threshold_color(swap.percent, MEMORY_USAGE_PERCENT_BORDERLINE, logic="less", ending="%")
        ram_load_text = (
            f"{bcolors.cyan}ram:[{bcolors.default}{ram_usage_text}, {ram_percent_text}{bcolors.cyan}]{bcolors.endc}"
        )
        swap_load_text = (
            f"{bcolors.cyan}swap:[{bcolors.default}{swap_usage_text}, {swap_percent_text}{bcolors.cyan}]{bcolors.endc}"
        )
        text = self.app.translate("memory_load").format(ram_load_text, swap_load_text)
        print(text)

    def _print_network_load(self) -> None:
        stats = self.registry.get_by_class(StatisticsModule)
        net_load1, net_load5, net_load15 = stats.get_net_load_avg()
        net_load1_text = get_threshold_color(net_load1, NET_LOAD_BORDERLINE_MBIT, logic="less")
        net_load5_text = get_threshold_color(net_load5, NET_LOAD_BORDERLINE_MBIT, logic="less")
        net_load15_text = get_threshold_color(net_load15, NET_LOAD_BORDERLINE_MBIT, logic="less")
        text = self.app.translate("net_load").format(net_load1_text, net_load5_text, net_load15_text)
        print(text)

    def _print_disks_load(self) -> None:
        stats = self.registry.get_by_class(StatisticsModule)
        disks_load_avg = stats.get_disks_load_avg()
        disks_load_percent_avg = stats.get_disks_load_percent_avg()

        disks_load_list: list[str] = []
        for name, data in disks_load_avg.items():
            disk_load_text = bcolors.green_text(data[2])  # [1m, 5m, 15m]
            disk_load_percent_text = get_threshold_color(
                disks_load_percent_avg[name][2],
                DISK_LOAD_BORDERLINE_PERCENT,
                logic="less",
                ending="%",
            )
            entry = (
                f"{bcolors.cyan}{name}:[{bcolors.default}"
                f"{disk_load_text}, {disk_load_percent_text}"
                f"{bcolors.cyan}]{bcolors.endc}"
            )
            disks_load_list.append(entry)

        text = self.app.translate("disks_load").format(", ".join(disks_load_list))
        print(text)

    def _print_service_status(self) -> None:
        service_status = get_service_status(self.service_name)
        service_uptime = get_service_uptime(self.service_name) or 0
        status_color = get_service_status_color(service_status)
        uptime_color = bcolors.green_text(time2human(service_uptime))
        text = self.app.translate("service_status_and_uptime").format(status_color, uptime_color)
        color_print(text)


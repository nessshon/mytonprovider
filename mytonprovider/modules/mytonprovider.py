from pathlib import Path
from typing import Any, ClassVar, Final

from mypycli import Commandable, Installable, Startable, Statusable, Updatable, utils
from mypycli.console.ansi import colorize_text, colorize_threshold
from mypycli.types import ByteUnit, ByteUnitDec, Color, Command, StatusPanel

from mytonprovider import constants
from mytonprovider.database import MetricsSnapshot
from mytonprovider.locales import _, lang
from mytonprovider.modules.sys_metrics import SysMetricsModule
from mytonprovider.utils import check_update, create_status_footer, create_status_header, display_version


class MytonproviderModule(
    Startable,
    Statusable,
    Installable,
    Updatable,
    Commandable,
):
    mandatory: ClassVar[bool] = True
    name: ClassVar[str] = constants.APP_NAME
    label: ClassVar[str] = constants.APP_LABEL

    SERVICE_NAME: Final[str] = f"{constants.APP_NAME}d"
    GIT_AUTHOR: ClassVar[str] = "nessshon"
    GIT_REPO: ClassVar[str] = "mytonprovider"

    CHECK_UPDATE_INTERVAL_SEC: Final[int] = 300
    PIP_INSTALL_TIMEOUT_SEC: Final[int] = 300

    service: ClassVar[utils.SystemdService] = utils.SystemdService(SERVICE_NAME)
    src_path: ClassVar[Path] = constants.SRC_DIR / GIT_REPO

    _update_available: bool | None = None
    _update_target: str | None = None

    @property
    def repo(self) -> utils.LocalGitRepo:
        return utils.LocalGitRepo(self.src_path)

    @property
    def version(self) -> str:
        return display_version(self.repo, author=self.GIT_AUTHOR, repo_name=self.GIT_REPO)

    def get_commands(self) -> list[Command]:
        return [Command("info", self._cmd_info, _("modules.mytonprovider.cmd.info"))]

    def on_install(self) -> None:
        venv_bin = constants.VENV_DIR / "bin" / constants.APP_NAME
        self.service.create(
            exec_start=f"{venv_bin} daemon",
            user=self.app.work_dir.owner(),
            work_dir=str(self.app.work_dir),
            environment={"PYTHONUNBUFFERED": "1"},
            description=f"{constants.APP_NAME} daemon",
        )
        self.service.enable()

    def on_uninstall(self) -> None:
        self.service.disable()
        self.service.remove()
        cmd_args = ["bash", str(self.src_path / "scripts" / "uninstall.sh")]
        utils.run(cmd_args, capture=False, check=False)

    def on_update(self) -> None:
        avail, _target = check_update(self.repo)
        if avail:
            self.repo.update()
            self.build()

    def build(self) -> None:
        install_args = [
            str(constants.VENV_DIR / "bin" / "pip"),
            "install",
            "--no-cache-dir",
            "--force-reinstall",
            str(self.src_path),
        ]
        utils.run(install_args, check=True, timeout=self.PIP_INSTALL_TIMEOUT_SEC)
        self.service.restart()

    def on_start(self) -> None:
        self.run_cycle(self.task_check_update, seconds=self.CHECK_UPDATE_INTERVAL_SEC)

    def on_stop(self) -> None:
        self._update_available = None
        self._update_target = None

    def show_status(self) -> StatusPanel:
        module = self.app.modules.get_by_class(SysMetricsModule)
        snapshot = module.snapshot
        return StatusPanel(
            items=[
                self._status_cpu(),
                *self._status_memory(),
                (),
                self._status_traffic(snapshot),
                self._status_network(snapshot),
                (),
                self._status_disk_space(),
                *self._status_disks(snapshot),
            ],
            header=create_status_header(
                self.label,
                self.version,
                target=self._update_target,
                available=bool(self._update_available),
            ),
            footer=create_status_footer(self.service, lang=lang()),
        )

    def task_check_update(self) -> None:
        try:
            self._update_available, self._update_target = check_update(self.repo)
        except Exception as exc:
            self.logger.warning(f"update check failed: {exc}")

    @staticmethod
    def _cmd_info(app: Any, _args: list[str]) -> None:
        app.console.print(_("modules.mytonprovider.info"))

    @staticmethod
    def _status_cpu() -> tuple[str, str]:
        cpu = utils.sysinfo.cpu
        cores = colorize_text(f"{cpu.count_logical}", Color.CYAN)
        loads = ", ".join(
            colorize_threshold(load, cpu.count_logical, logic="less", precision=2)
            for load in (cpu.load_1m, cpu.load_5m, cpu.load_15m)
        )
        return _("modules.mytonprovider.status.cpu_load", cores=cores), loads

    @staticmethod
    def _status_memory() -> list[tuple[str, str]]:
        label = _("modules.mytonprovider.status.memory_load")
        ram, swap = utils.sysinfo.ram, utils.sysinfo.swap
        sources = [("ram", ram)] if swap.total == 0 else [("ram", ram), ("swap", swap)]
        name_width = max(len(name) for name, _info in sources)
        rows: list[tuple[str, str]] = []
        for index, (name, info) in enumerate(sources):
            used = utils.bytes_to(info.used, ByteUnitDec.GB)
            total = utils.bytes_to(info.total, ByteUnitDec.GB)
            pct = colorize_threshold(info.percent, 90, logic="less", ending="%", precision=1)
            name_pad = " " * (name_width - len(name))
            value = f"{colorize_text(name, Color.CYAN)}{name_pad}  {used:.1f}/{total:.1f} GB ({pct})"
            rows.append((label if index == 0 else "", value))
        return rows

    @staticmethod
    def _status_traffic(snapshot: MetricsSnapshot | None) -> tuple[str, str]:
        label = _("modules.mytonprovider.status.network_total")
        if snapshot is None:
            return label, colorize_text(_("common.status.collecting"), Color.GRAY)
        return label, f"↓ {utils.format_bytes(snapshot.bytes_recv)}, ↑ {utils.format_bytes(snapshot.bytes_sent)}"

    @staticmethod
    def _status_network(snapshot: MetricsSnapshot | None) -> tuple[str, str]:
        label = _("modules.mytonprovider.status.network_io")
        if snapshot is None or snapshot.net is None:
            return label, colorize_text(_("common.status.collecting"), Color.GRAY)
        loads = ", ".join(f"{v:.1f}" for v in snapshot.net.load)
        return label, f"{loads} Mbit/s"

    def _status_disk_space(self) -> tuple[str, str]:
        path = colorize_text(str(self.app.work_dir), Color.CYAN)
        usage = utils.sysinfo.get_disk_usage(str(self.app.work_dir))
        used_gb = utils.bytes_to(usage.used, ByteUnit.GB)
        total_gb = utils.bytes_to(usage.total, ByteUnit.GB)
        pct = colorize_threshold(usage.percent, 90, logic="less", ending="%", precision=1)
        return _("modules.mytonprovider.status.disk_space"), f"{path} {used_gb:.1f}/{total_gb:.1f} GB ({pct})"

    @staticmethod
    def _status_disks(snapshot: MetricsSnapshot | None) -> list[tuple[str, str]]:
        label = _("modules.mytonprovider.status.disk_io")
        if snapshot is None or not snapshot.disks:
            return [(label, colorize_text(_("common.status.collecting"), Color.GRAY))]
        ranked = sorted(snapshot.disks.items(), key=lambda item: item[1].load[2], reverse=True)
        name_width = max(len(name) for name, _avg in ranked)
        load_width = max(len(f"{avg.load[2]:.1f}") for _name, avg in ranked)
        rows: list[tuple[str, str]] = []
        for index, (name, avg) in enumerate(ranked):
            name_pad = " " * (name_width - len(name))
            load_str = f"{avg.load[2]:.1f}".rjust(load_width)
            pct = colorize_threshold(avg.load_percent[2], 80, logic="less", ending="%", precision=1)
            value = f"{colorize_text(name, Color.CYAN)}{name_pad}  {load_str} MB/s ({pct})"
            rows.append((label if index == 0 else "", value))
        return rows

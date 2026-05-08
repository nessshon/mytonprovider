from typing import cast

from mypycli import Application, utils
from mypycli.types import ByteUnit, ByteUnitDec
from nicegui import run, ui

from mytonprovider.database import AppDatabaseSchema
from mytonprovider.locales import _
from mytonprovider.modules.sys_metrics import SysMetricsModule
from mytonprovider.modules.ton_storage import TonStorageModule
from mytonprovider.modules.ton_storage_provider import TonStorageProviderModule
from mytonprovider.web import theme
from mytonprovider.web.components import card, placeholder, row, row_mono
from mytonprovider.web.layout import page_shell


def register(provider_app: Application[AppDatabaseSchema]) -> None:
    @ui.page("/")
    def index() -> None:
        with (
            page_shell(app_label=provider_app.label, current="dashboard"),
            ui.element("div").classes(theme.GRID_CLASSES),
        ):
            _provider_card(provider_app)
            _ton_storage_card(provider_app)
            _ton_provider_card(provider_app)
            _wallet_card(provider_app)


def _refresh_sec(provider_app: Application[AppDatabaseSchema]) -> float:
    return float(provider_app.db.settings.web.refresh_sec)


def _provider_card(provider_app: Application[AppDatabaseSchema]) -> None:
    sys_metrics = cast(SysMetricsModule | None, provider_app.modules.get("sys-metrics"))
    provider_module = provider_app.modules.get("mytonprovider")

    @ui.refreshable
    def body() -> None:
        snap = sys_metrics.snapshot if sys_metrics is not None else None
        if snap is None or snap.net is None:
            placeholder()
            return
        cpu_loads = ", ".join(f"{v:.2f}" for v in snap.cpu.load)
        row(_("modules.mytonprovider.status.cpu_load", cores=snap.cpu.count_logical), cpu_loads)
        ram_used = utils.bytes_to(snap.ram.used, ByteUnitDec.GB)
        ram_total = utils.bytes_to(snap.ram.total, ByteUnitDec.GB)
        row(
            _("modules.mytonprovider.status.memory_load"),
            f"{ram_used:.1f} / {ram_total:.1f} GB · {snap.ram.percent:.1f}%",
        )
        row(
            _("modules.mytonprovider.status.network_total"),
            f"↓ {utils.format_bytes(snap.bytes_recv)} · ↑ {utils.format_bytes(snap.bytes_sent)}",
        )
        net_loads = ", ".join(f"{v:.1f}" for v in snap.net.load)
        row(_("modules.mytonprovider.status.network_io"), f"{net_loads} Mbit/s")
        try:
            usage = utils.sysinfo.get_disk_usage(str(provider_app.work_dir))
            used_gb = utils.bytes_to(usage.used, ByteUnit.GB)
            total_gb = utils.bytes_to(usage.total, ByteUnit.GB)
            row(
                _("modules.mytonprovider.status.disk_space"),
                f"{used_gb:.1f} / {total_gb:.1f} GB · {usage.percent:.1f}%",
            )
        except Exception:
            pass

    card(
        title=provider_app.label,
        service=getattr(provider_module, "service", None),
        body=body,
        refresh_sec=_refresh_sec(provider_app),
    )


def _ton_storage_card(provider_app: Application[AppDatabaseSchema]) -> None:
    ts = cast(TonStorageModule | None, provider_app.modules.get("ton-storage"))

    @ui.refreshable
    async def body() -> None:
        if ts is None:
            placeholder()
            return
        port = provider_app.db.modules.ton_storage.udp_port
        row(_("modules.ton_storage.status.udp_port"), str(port) if port else "—")

        try:
            data = await run.io_bound(ts.api.list_bags)
        except Exception:
            data = None
        if data is None:
            row(_("modules.ton_storage.status.bags"), _("common.status.collecting"))
        else:
            count = len(data.bags)
            total = utils.format_bytes(sum(b.size for b in data.bags))
            row(_("modules.ton_storage.status.bags"), f"{count} · {total}")

        path = provider_app.db.modules.ton_storage.storage_path
        if path:
            try:
                usage = utils.sysinfo.get_disk_usage(path)
                used_gb = utils.bytes_to(usage.used, ByteUnit.GB)
                total_gb = utils.bytes_to(usage.total, ByteUnit.GB)
                row(
                    _("modules.ton_storage.status.disk_space"),
                    f"{used_gb:.1f} / {total_gb:.1f} GB · {usage.percent:.1f}%",
                )
            except Exception:
                pass

    card(
        title=ts.label if ts is not None else "TON Storage",
        service=ts.service if ts is not None else None,
        body=body,
        refresh_sec=_refresh_sec(provider_app),
    )


def _ton_provider_card(provider_app: Application[AppDatabaseSchema]) -> None:
    provider = cast(TonStorageProviderModule | None, provider_app.modules.get("ton-storage-provider"))

    @ui.refreshable
    async def body() -> None:
        if provider is None:
            placeholder()
            return
        try:
            cfg = await run.io_bound(provider.get_provider_config)
        except Exception:
            cfg = None
        if cfg is None:
            placeholder()
            return

        row(_("modules.ton_storage_provider.status.udp_port"), str(cfg.udp_port) if cfg.udp_port else "—")
        row_mono(_("modules.ton_storage_provider.status.pubkey"), cfg.provider_pubkey or "—")
        row(_("modules.ton_storage_provider.status.storage_cost"), f"{cfg.storage_cost} TON / 200 GB / mo")
        used_gb = await run.io_bound(provider.get_used_space_gb)
        total_gb = cfg.space_gb
        rate = cfg.storage_cost / 200 if total_gb else 0.0
        real_profit = round(used_gb * rate, 2)
        max_profit = round(total_gb * rate, 2)
        row(
            _("modules.ton_storage_provider.status.profit"),
            f"{real_profit} TON · max {max_profit} TON",
        )
        pct = (used_gb / total_gb * 100) if total_gb else 0.0
        row(
            _("modules.ton_storage_provider.status.provided"),
            f"{used_gb:.2f} / {total_gb} GB · {pct:.1f}%",
        )
        row(
            _("modules.ton_storage_provider.status.max_bag_size"),
            f"{cfg.max_bag_size_gb} GB",
        )

    card(
        title=provider.label if provider is not None else "TON Storage Provider",
        service=provider.service if provider is not None else None,
        body=body,
        refresh_sec=_refresh_sec(provider_app),
    )


def _wallet_card(provider_app: Application[AppDatabaseSchema]) -> None:
    @ui.refreshable
    def body() -> None:
        registered = bool(provider_app.db.modules.ton_wallet.registered)
        if registered:
            row(
                _("modules.web.dashboard.wallet.registration"),
                _("modules.web.dashboard.wallet.registered"),
                value_class="text-positive",
            )
        else:
            row(
                _("modules.web.dashboard.wallet.registration"),
                _("modules.web.dashboard.wallet.not_registered"),
                value_class="text-warning",
            )
        ui.label(_("modules.web.dashboard.wallet.balance_hint")).classes("text-caption text-grey-6 q-mt-sm")

    card(
        title="TON Wallet",
        service=None,
        body=body,
        refresh_sec=_refresh_sec(provider_app),
    )

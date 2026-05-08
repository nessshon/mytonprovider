from collections.abc import Awaitable, Callable

from mypycli.utils.service import SystemdService
from nicegui import ui

from mytonprovider.locales import _
from mytonprovider.web import theme


def card(
    *,
    title: str,
    service: SystemdService | None,
    body: Callable[[], None] | Callable[[], Awaitable[None]],
    refresh_sec: float | None = None,
) -> None:
    with ui.card().classes(theme.CARD_CLASSES):
        with ui.row().classes("w-full items-center justify-between q-mb-sm"):
            ui.label(title).classes(theme.LABEL_HEADING)
            if service is not None:
                service_badge(service)
        ui.separator()
        with ui.column().classes("w-full gap-1 q-pt-sm"):
            body()
    refresh_fn = getattr(body, "refresh", None)
    if refresh_fn is not None and refresh_sec is not None:
        ui.timer(refresh_sec, refresh_fn)


def row(label: str, value: str, *, value_class: str = "") -> None:
    with ui.row().classes(theme.ROW_CLASSES):
        ui.label(label).classes(theme.LABEL_MUTED)
        ui.label(value).classes(f"{theme.LABEL_VALUE} {value_class}".strip())


def row_mono(label: str, value: str) -> None:
    with ui.row().classes(theme.ROW_CLASSES):
        ui.label(label).classes(theme.LABEL_MUTED)
        ui.label(value).classes("text-caption text-weight-regular ellipsis text-right").style(theme.MONO_STYLE)


def service_badge(service: SystemdService) -> None:
    try:
        active = service.is_active
    except Exception:
        active = False
    text = _("common.status.active") if active else _("common.status.inactive")
    color = "positive" if active else "grey"
    ui.badge(text, color=color).props("rounded")


def placeholder() -> None:
    ui.label(_("common.status.collecting")).classes("text-grey-5 text-body2 q-py-md")

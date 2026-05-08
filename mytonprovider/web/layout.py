from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Final

from nicegui import ui

from mytonprovider.locales import _
from mytonprovider.web import auth, theme

_NavItem = tuple[str, str, str, str]

NAV_ITEMS: Final[tuple[_NavItem, ...]] = (
    ("dashboard", "/", "dashboard", "modules.web.nav.dashboard"),
    ("bags", "/bags", "folder", "modules.web.nav.bags"),
    ("provider", "/provider", "settings_input_component", "modules.web.nav.provider"),
    ("wallet", "/wallet", "account_balance_wallet", "modules.web.nav.wallet"),
    ("benchmark", "/benchmark", "speed", "modules.web.nav.benchmark"),
    ("system", "/system", "miscellaneous_services", "modules.web.nav.system"),
    ("settings", "/settings", "settings", "modules.web.nav.settings"),
)


@contextmanager
def page_shell(*, app_label: str, current: str) -> Iterator[None]:
    ui.colors(primary=theme.PRIMARY_COLOR)
    with (
        ui.header(elevated=False).classes("bg-grey-10 q-py-sm"),
        ui.row().classes("w-full items-center q-px-md"),
    ):
        with ui.row().classes("items-center gap-2"):
            ui.icon("dns").classes("text-primary").props("size=1.6em")
            ui.label(app_label).classes("text-weight-bold")
        ui.space()
        with ui.row().classes("gap-1 items-center wrap"):
            for key, path, icon_name, label_key in NAV_ITEMS:
                btn = ui.button(_(label_key), icon=icon_name, on_click=_nav_handler(path))
                btn.props("flat dense" + (" color=primary" if key == current else ""))
            ui.button(icon="logout", on_click=_logout_handler()).props("flat round dense")
    with ui.column().classes(theme.PAGE_CLASSES):
        yield


def _nav_handler(path: str) -> Callable[[], None]:
    def handler() -> None:
        ui.navigate.to(path)

    return handler


def _logout_handler() -> Callable[[], None]:
    def handler() -> None:
        auth.logout_session()
        ui.navigate.to("/login")

    return handler

from mypycli import Application
from nicegui import ui

from mytonprovider.database import AppDatabaseSchema
from mytonprovider.locales import _
from mytonprovider.web.layout import page_shell


def register(provider_app: Application[AppDatabaseSchema]) -> None:
    @ui.page("/settings")
    def settings() -> None:
        with page_shell(app_label=provider_app.label, current="settings"):
            ui.label(_("modules.web.nav.settings")).classes("text-h4 text-weight-bold")
            ui.label(_("modules.web.stub.coming_soon")).classes("text-grey-6")

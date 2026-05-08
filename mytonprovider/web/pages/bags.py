from mypycli import Application
from nicegui import ui

from mytonprovider.database import AppDatabaseSchema
from mytonprovider.locales import _
from mytonprovider.web.layout import page_shell


def register(provider_app: Application[AppDatabaseSchema]) -> None:
    @ui.page("/bags")
    def bags() -> None:
        with page_shell(app_label=provider_app.label, current="bags"):
            ui.label(_("modules.web.nav.bags")).classes("text-h4 text-weight-bold")
            ui.label(_("modules.web.stub.coming_soon")).classes("text-grey-6")

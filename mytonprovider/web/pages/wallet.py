from mypycli import Application
from nicegui import ui

from mytonprovider.database import AppDatabaseSchema
from mytonprovider.locales import _
from mytonprovider.web.layout import page_shell


def register(provider_app: Application[AppDatabaseSchema]) -> None:
    @ui.page("/wallet")
    def wallet() -> None:
        with page_shell(app_label=provider_app.label, current="wallet"):
            ui.label(_("modules.web.nav.wallet")).classes("text-h4 text-weight-bold")
            ui.label(_("modules.web.stub.coming_soon")).classes("text-grey-6")

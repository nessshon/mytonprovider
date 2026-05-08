from mypycli import Application
from nicegui import app, ui

from mytonprovider.database import AppDatabaseSchema
from mytonprovider.web import auth
from mytonprovider.web.pages import register_all


def run_server(provider_app: Application[AppDatabaseSchema]) -> None:
    web_state = provider_app.db.modules.web
    web_settings = provider_app.db.settings.web

    if not web_state.session_secret:
        web_state.session_secret = auth.generate_secret()

    app.add_middleware(auth.AuthMiddleware)
    register_all(provider_app)

    ui.run(
        host=web_settings.host,
        port=web_settings.port,
        title=provider_app.label,
        reload=False,
        show=False,
        dark=True,
        favicon="🛰",
        storage_secret=web_state.session_secret,
    )

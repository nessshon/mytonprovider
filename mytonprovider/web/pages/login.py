import time

from fastapi.responses import RedirectResponse
from mypycli import Application
from nicegui import ui
from starlette.responses import Response

from mytonprovider.database import AppDatabaseSchema
from mytonprovider.locales import _
from mytonprovider.web import auth, theme


def _safe_redirect(target: str | None) -> str:
    if not target or not target.startswith("/") or target.startswith("/_nicegui"):
        return "/"
    return target


def register(provider_app: Application[AppDatabaseSchema]) -> None:
    @ui.page("/login")
    def login(redirect_to: str = "/") -> Response | None:
        target = _safe_redirect(redirect_to)
        if auth.is_authenticated():
            return RedirectResponse(target)

        ui.colors(primary=theme.PRIMARY_COLOR)

        with ui.card().classes("absolute-center q-pa-lg gap-md").style("min-width: 340px;"):
            ui.label(provider_app.label).classes("text-h5 text-weight-bold")
            ui.label(_("modules.web.login.subtitle")).classes("text-caption text-grey-6")

            password_input = ui.input(_("modules.web.login.password"), password=True)
            password_input.classes("w-full").props("autofocus outlined")

            def attempt() -> None:
                state = provider_app.db.modules.web
                now = int(time.time())
                lock_remaining = auth.is_locked_out(state, now=now)
                if lock_remaining:
                    minutes = max(1, lock_remaining // 60)
                    ui.notify(_("modules.web.login.locked_out", minutes=minutes), type="negative")
                    return
                if not state.password_hash or not state.password_salt:
                    ui.notify(_("modules.web.login.no_password"), type="negative")
                    return
                if auth.verify_password(
                    password_input.value or "",
                    state.password_salt,
                    state.password_hash,
                ):
                    auth.register_success(state)
                    auth.login_session()
                    ui.navigate.to(target)
                    return
                locked = auth.register_failure(state, now=now)
                password_input.value = ""
                if locked:
                    ui.notify(_("modules.web.login.now_locked"), type="negative")
                else:
                    ui.notify(_("modules.web.login.wrong"), type="negative")

            password_input.on("keydown.enter", attempt)
            ui.button(_("modules.web.login.submit"), on_click=attempt).classes("w-full")
        return None

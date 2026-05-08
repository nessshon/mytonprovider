from mypycli import Application

from mytonprovider.database import AppDatabaseSchema
from mytonprovider.web.pages import (
    bags,
    benchmark,
    dashboard,
    login,
    provider,
    settings,
    system,
    wallet,
)


def register_all(provider_app: Application[AppDatabaseSchema]) -> None:
    login.register(provider_app)
    dashboard.register(provider_app)
    bags.register(provider_app)
    provider.register(provider_app)
    wallet.register(provider_app)
    benchmark.register(provider_app)
    system.register(provider_app)
    settings.register(provider_app)

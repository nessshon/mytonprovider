import sys
from typing import cast

from mypycli import Application

from mytonprovider import constants
from mytonprovider.database import AppDatabaseSchema
from mytonprovider.locales import translator
from mytonprovider.modules import MODULES
from mytonprovider.modules.updater import UpdaterModule


def cmd_updater_daemon(app: Application[AppDatabaseSchema]) -> None:
    app.start()
    updater = cast(UpdaterModule, app.modules.get("updater"))
    updater.run_cycle(updater.update_modules, seconds=updater.CHECK_UPDATES_INTERVAL_SEC)
    app.run_forever()
    app.stop()


def cmd_web_daemon(app: Application[AppDatabaseSchema]) -> None:
    app.start()
    from mytonprovider.web import run_server

    run_server(app)
    app.stop()


def main() -> None:
    app: Application[AppDatabaseSchema] = Application(
        db_schema=AppDatabaseSchema,
        work_dir=constants.WORK_DIR,
        translator=translator,
        name=constants.APP_NAME,
        label=constants.APP_LABEL,
        modules=MODULES,
        env_prefix="MTP",
    )

    command = sys.argv[1] if len(sys.argv) > 1 else None
    if command == "updater-daemon":
        cmd_updater_daemon(app)
        return
    if command == "web-daemon":
        cmd_web_daemon(app)
        return

    app.run()


if __name__ == "__main__":
    main()

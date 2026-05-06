import sys

from mypycli import Application
from mypycli.logger import add_stream_handler

from mytonprovider import constants
from mytonprovider.database import AppDatabaseSchema
from mytonprovider.locales import translator
from mytonprovider.modules import MODULES
from mytonprovider.modules.updater import UpdaterModule


def cmd_auto_update(app: Application[AppDatabaseSchema]) -> None:
    add_stream_handler(app.logger)
    app.start()
    updater = app.modules.get_by_class(UpdaterModule)
    updater.run_cycle(updater.update_modules, seconds=updater.CHECK_UPDATES_INTERVAL_SEC)
    app.run_forever()
    app.stop()


def main() -> None:
    app: Application[AppDatabaseSchema] = Application(
        db_schema=AppDatabaseSchema,
        work_dir=constants.WORK_DIR,
        translator=translator,
        name=constants.APP_NAME,
        label=constants.APP_LABEL,
        prompt=constants.APP_PROMPT,
        modules=MODULES,
        env_prefix="MTP",
    )

    command = sys.argv[1] if len(sys.argv) > 1 else None
    if command == "auto-update":
        cmd_auto_update(app)
        return

    app.run()


if __name__ == "__main__":
    main()

from mypycli import Application, DatabaseSchema

from mytonprovider import constants
from mytonprovider.modules import MODULES


def main() -> None:
    app = Application[DatabaseSchema](
        db_schema=DatabaseSchema,
        work_dir=constants.WORK_DIR,
        name=constants.APP_NAME,
        label=constants.APP_LABEL,
        modules=MODULES,
    )
    app.run()


if __name__ == "__main__":
    main()

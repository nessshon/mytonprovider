from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mypylib import MyPyClass

from mytonprovider import constants
from mytonprovider.commands import (
    cmd_console,
    cmd_daemon,
    cmd_init,
    cmd_uninstall,
    cmd_update,
)
from mytonprovider.commands.init import is_initialized
from mytonprovider.modules import MODULE_CLASSES, ModuleRegistry, build_registry
from mytonprovider.utils import resolve_app_home


def setup_app() -> tuple[MyPyClass, ModuleRegistry]:
    """Create the MyPyClass instance and module registry."""
    app = MyPyClass(
        file=__file__,
        name=constants.APP_NAME,
        work_dir=str(resolve_app_home() / constants.WORK_DIR),
    )
    app.init_translator(str(constants.TRANSLATIONS_PATH))
    app.run()
    registry = build_registry(app, MODULE_CLASSES)
    return app, registry


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog=constants.APP_NAME,
        description="TON storage provider management daemon and CLI.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {constants.MYTONPROVIDER_VERSION}",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a background daemon (used by systemd ExecStart).",
    )

    subparsers = parser.add_subparsers(dest="command")

    init_p = subparsers.add_parser("init", help="Initialize mytonprovider.")
    init_p.add_argument(
        "--user",
        type=str,
        default=None,
        help="Target system user (defaults to SUDO_USER / DOAS_USER / $USER).",
    )
    init_p.add_argument(
        "--modules",
        type=str,
        default=None,
        help="Comma-separated optional module names to install.",
    )
    init_p.add_argument(
        "--storage-path",
        type=Path,
        default=None,
        help="Filesystem path where ton-storage keeps bags.",
    )
    init_p.add_argument(
        "--storage-cost",
        type=int,
        default=None,
        help="Storage price in TON per 200 GB per month.",
    )
    init_p.add_argument(
        "--provider-space",
        type=int,
        default=None,
        help="Disk space (GB) the provider allocates for stored bags.",
    )
    init_p.add_argument(
        "--max-bag-size",
        type=int,
        default=None,
        help="Maximum accepted BAG size (GB, 1-1024).",
    )
    init_p.add_argument(
        "--auto-update",
        type=str,
        choices=["yes", "no"],
        default=None,
        help="Enable module auto-update daemon.",
    )

    update_p = subparsers.add_parser("update", help="Update modules.")
    update_p.add_argument(
        "module",
        nargs="?",
        default=None,
        help="Module to update; if omitted, all updatables are processed.",
    )
    update_p.add_argument(
        "--ref",
        type=str,
        default=None,
        help="Git ref (tag or branch) to install; requires a target module.",
    )
    update_p.add_argument(
        "--author",
        type=str,
        default=None,
        help="Override git author; requires --ref.",
    )
    update_p.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Override git repo name; requires --ref.",
    )
    update_p.add_argument(
        "--force",
        action="store_true",
        help="Reinstall even when no update is reported.",
    )
    update_p.add_argument(
        "--check",
        action="store_true",
        help="Only report availability, do not install.",
    )

    uninstall_p = subparsers.add_parser(
        "uninstall",
        help="Uninstall mytonprovider: stop services, remove units/binaries/config.",
    )
    uninstall_p.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip the wallet-keys confirmation prompt.",
    )

    return parser


def require_initialized() -> None:
    """Exit with error if mytonprovider is not initialized."""
    if not is_initialized():
        print(f"Error: {constants.APP_NAME} is not initialized.", file=sys.stderr)
        print(f"Run `{constants.APP_NAME} init` first.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args, _unknown = parser.parse_known_args()

    if args.daemon:
        require_initialized()
        app, registry = setup_app()
        cmd_daemon(app, registry)
        return

    if args.command == "uninstall":
        cmd_uninstall(yes=args.yes)
        return

    if args.command == "init":
        app, registry = setup_app()
        modules_tuple = tuple(args.modules.split(",")) if args.modules is not None else None
        auto_update_enabled = (
            args.auto_update == "yes" if args.auto_update is not None else None
        )
        cmd_init(
            app,
            registry,
            user=args.user,
            selected_modules=modules_tuple,
            storage_path=args.storage_path,
            storage_cost=args.storage_cost,
            space_to_provide_gigabytes=args.provider_space,
            max_bag_size_gigabytes=args.max_bag_size,
            auto_update_enabled=auto_update_enabled,
        )
        return

    if args.command == "update":
        require_initialized()
        app, registry = setup_app()
        cmd_update(
            app,
            registry,
            target=args.module,
            ref=args.ref,
            author=args.author,
            repo=args.repo,
            force=args.force,
            check=args.check,
        )
        return

    if not is_initialized():
        print(f"{constants.APP_NAME} is not initialized.")
        answer = input("Run init wizard now? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            app, registry = setup_app()
            cmd_init(app, registry)
        return

    app, registry = setup_app()
    cmd_console(app, registry)


if __name__ == "__main__":
    main()

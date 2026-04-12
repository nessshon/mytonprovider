from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from mypyconsole import MyPyConsole
from mypylib import DEBUG, color_print, print_table

from mytonprovider import constants
from mytonprovider.commands.update import cmd_update

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from mytonprovider.modules import ModuleRegistry
    from mytonprovider.modules.core import Startable


def cmd_console(app: MyPyClass, registry: ModuleRegistry) -> None:
    """Run the interactive REPL with module commands."""
    console = MyPyConsole()
    console.name = "MyTonProvider"
    console.local = app
    console.debug = bool(app.db.get("debug"))
    def _on_start() -> None:
        _run_pre_up(app, registry)
        _console_status(registry)

    console.start_function = _on_start

    if console.debug:
        color_print("{red}Debug mode enabled{endc}")

    console.add_item(
        "status",
        lambda _args: _console_status(registry),
        app.translate("status_cmd"),
    )
    console.add_item(
        "update",
        lambda args: _console_update(app, registry, args),
        app.translate("update_cmd"),
    )
    console.add_item(
        "get",
        lambda args: _console_get(app, args),
        app.translate("get_cmd"),
    )
    console.add_item(
        "set",
        lambda args: _console_set(app, args),
        app.translate("set_cmd"),
    )
    console.add_item(
        "modules_list",
        lambda _args: _console_modules_list(registry),
        app.translate("modules_list_cmd"),
    )

    for module in registry.commandables():
        for command in module.get_commands():
            console.add_item(command.name, command.func, command.description)

    console.run()


def _run_pre_up(app: MyPyClass, registry: ModuleRegistry) -> None:
    """Invoke ``pre_up`` on every Startable module, logging failures."""
    for startable in registry.startables():
        _safe_pre_up(app, startable)


def _safe_pre_up(app: MyPyClass, startable: Startable) -> None:
    """Call ``pre_up`` once, logging exceptions at DEBUG level."""
    try:
        startable.pre_up()
    except Exception as exc:
        app.add_log(f"{startable.name}: pre_up failed: {exc}", DEBUG)


def _console_status(registry: ModuleRegistry) -> None:
    """Print status blocks for every Statusable module, main module last."""
    print()
    statusables = registry.statusables()
    main = [m for m in statusables if m.mandatory]
    rest = [m for m in statusables if not m.mandatory]
    ordered = rest + main
    for index, module in enumerate(ordered):
        module.show_status()
        if index < len(ordered) - 1:
            print()


def _console_update(app: MyPyClass, registry: ModuleRegistry, args: list[str]) -> None:
    """Parse REPL ``update`` args and delegate to ``cmd_update``."""
    parser = argparse.ArgumentParser(prog="update", add_help=False)
    parser.add_argument("module", nargs="?", default=None)
    parser.add_argument("--ref", type=str, default=None)
    parser.add_argument("--author", type=str, default=None)
    parser.add_argument("--repo", type=str, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        color_print(
            "{red}Usage:{endc} update [<module>] [--ref X] [--author Y] "
            "[--repo Z] [--force | --check]",
        )
        return

    try:
        results = cmd_update(
            app,
            registry,
            target=parsed.module,
            ref=parsed.ref,
            author=parsed.author,
            repo=parsed.repo,
            force=parsed.force,
            check=parsed.check,
        )
    except RuntimeError as exc:
        color_print(f"{{red}}{exc}{{endc}}")
        return

    self_updated = any(
        r.module == constants.APP_NAME and r.action == "updated"
        for r in results
    )
    if self_updated:
        color_print("{green}Restart to apply the update.{endc}")
        sys.exit(0)


def _resolve_path(obj: object, path: str) -> tuple[dict[str, object], str]:
    """Walk *obj* along dot-separated *path*, return ``(parent, last_key)``."""
    keys = path.split(".")
    current: object = obj
    for key in keys[:-1]:
        current = current[key] if isinstance(current, dict) else getattr(current, key)
        if current is None:
            raise KeyError(path)
    return current, keys[-1]  # type: ignore[return-value]


def _console_get(app: MyPyClass, args: list[str]) -> None:
    """Print a value from the database as pretty JSON."""
    if len(args) != 1:
        color_print("{red}Usage:{endc} get <name>")
        return
    try:
        parent, key = _resolve_path(app.db, args[0])
        value = parent.get(key) if isinstance(parent, dict) else getattr(parent, key, None)
    except (KeyError, AttributeError, TypeError):
        value = None
    print(json.dumps(value, indent=2, default=str))


def _console_set(app: MyPyClass, args: list[str]) -> None:
    """Set a database value from JSON and persist."""
    if len(args) != 2:
        color_print("{red}Usage:{endc} set <name> <json-value>")
        return
    name, raw = args
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        color_print(f"{{red}}Invalid JSON: {exc}{{endc}}")
        return
    try:
        parent, key = _resolve_path(app.db, name)
    except (KeyError, AttributeError, TypeError):
        color_print(f"{{red}}Path not found: {name}{{endc}}")
        return
    parent[key] = value
    app.save()
    color_print("set - {green}OK{endc}")


def _console_modules_list(registry: ModuleRegistry) -> None:
    """Print a table of all modules with their capabilities."""
    table: list[list[str]] = [["Name", "Enabled", "Mandatory", "Capabilities"]]
    for module in registry.all(enabled_only=False):
        enabled = "" if module.mandatory else str(module.is_enabled)
        capabilities = _module_capabilities(module)
        table.append([
            module.name,
            enabled,
            str(module.mandatory),
            ", ".join(capabilities),
        ])
    print_table(table)


def _module_capabilities(module: object) -> list[str]:
    """Return capability-mixin names this module implements."""
    from mytonprovider.modules.core import (
        Commandable,
        Daemonic,
        Installable,
        Startable,
        Statusable,
        Updatable,
    )

    labels: list[tuple[type, str]] = [
        (Startable, "startable"),
        (Statusable, "statusable"),
        (Daemonic, "daemonic"),
        (Installable, "installable"),
        (Updatable, "updatable"),
        (Commandable, "commandable"),
    ]
    return [label for cls, label in labels if isinstance(module, cls)]

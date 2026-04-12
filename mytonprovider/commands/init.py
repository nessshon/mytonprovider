from __future__ import annotations

import os
import pwd
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import inquirer
from mypylib import ByteUnit, Dict, get_disk_space, read_config_from_file

from mytonprovider.modules.core import Installable
from mytonprovider.types import InstallContext
from mytonprovider.utils import get_config_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from mypylib import MyPyClass

    from mytonprovider.modules import ModuleRegistry


def is_initialized() -> bool:
    """Return ``True`` if the init wizard has been completed."""
    db_path = get_config_path()
    if not db_path.exists():
        return False
    try:
        db = read_config_from_file(str(db_path))
    except Exception:
        return False
    return bool(db.get("initialized"))


def _resolve_user(cli_user: str | None) -> str:
    """Resolve the target install user from CLI flag or environment."""
    candidate: str | None = cli_user
    if candidate is None:
        for env_var in ("SUDO_USER", "DOAS_USER", "USER"):
            value = os.environ.get(env_var)
            if value and value != "root":
                candidate = value
                break

    if candidate is None:
        raise RuntimeError(
            "Cannot detect target user. Run via sudo/doas from a non-root user, "
            "or pass --user explicitly.",
        )

    try:
        pwd.getpwnam(candidate)
    except KeyError as exc:
        raise RuntimeError(f"User {candidate!r} does not exist") from exc

    return candidate


def _is_non_interactive(
    selected_modules: tuple[str, ...] | None,
    storage_path: Path | None,
    storage_cost: int | None,
    space_to_provide_gigabytes: int | None,
    max_bag_size_gigabytes: int | None,
    auto_update_enabled: bool | None,
) -> bool:
    """Return ``True`` if any wizard parameter was passed via CLI."""
    return any(
        value is not None
        for value in (
            selected_modules,
            storage_path,
            storage_cost,
            space_to_provide_gigabytes,
            max_bag_size_gigabytes,
            auto_update_enabled,
        )
    )


def _validate_non_interactive(
    *,
    selected_modules: tuple[str, ...] | None,
    storage_path: Path | None,
    storage_cost: int | None,
    space_to_provide_gigabytes: int | None,
    max_bag_size_gigabytes: int | None,
    auto_update_enabled: bool | None,
) -> None:
    """Ensure all required parameters for non-interactive mode are present."""
    missing: list[str] = []

    if selected_modules is None:
        missing.append("--modules")
    if auto_update_enabled is None:
        missing.append("--auto-update")

    modules = selected_modules or ()
    if "ton-storage" in modules and storage_path is None:
        missing.append("--storage-path")
    if "ton-storage-provider" in modules:
        if storage_cost is None:
            missing.append("--storage-cost")
        if space_to_provide_gigabytes is None:
            missing.append("--provider-space")
        if max_bag_size_gigabytes is None:
            missing.append("--max-bag-size")

    if missing:
        raise RuntimeError(
            f"Missing required arguments for non-interactive init: {', '.join(missing)}",
        )


def _validate_storage_path(value: str) -> bool:
    try:
        os.makedirs(value, exist_ok=True)
    except OSError:
        return False
    return True


def _validate_positive_int(value: str) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _validate_max_bag_size(value: str) -> bool:
    try:
        gb = int(value)
    except (TypeError, ValueError):
        return False
    return 1 <= gb <= 1024


def _run_wizard(app: MyPyClass, registry: ModuleRegistry) -> dict[str, Any]:
    """Run the interactive install wizard and return collected answers."""
    previous: Dict = app.db.get("install_answers") or Dict()

    optional_modules = [
        m.name
        for m in registry.all(enabled_only=False)
        if not m.mandatory
    ]

    def _ignore_unless(module: str) -> Callable[[dict[str, Any]], bool]:
        def _check(answers: dict[str, Any]) -> bool:
            return module not in (answers.get("selected_modules") or [])
        return _check

    def _default_space(answers: dict[str, Any]) -> str:
        prev = previous.get("space_to_provide_gigabytes")
        if prev is not None:
            return str(prev)
        storage_path = answers.get("storage_path")
        if not storage_path:
            return "100"
        try:
            disk = get_disk_space(storage_path, unit=ByteUnit.GB, ndigits=0)
            return str(int(disk.free * 0.9))
        except Exception:
            return "100"

    def _space_message(answers: dict[str, Any]) -> str:
        storage_path = answers.get("storage_path") or "/"
        try:
            disk = get_disk_space(storage_path, unit=ByteUnit.GB, ndigits=0)
            return app.translate("question_space_to_provide").format(disk.total, disk.free)
        except Exception:
            return app.translate("question_space_to_provide").format("?", "?")

    questions = [
        inquirer.Checkbox(
            name="selected_modules",
            message=app.translate("question_utils"),
            choices=optional_modules,
            default=previous.get("selected_modules") or [],
        ),
        inquirer.Text(
            name="storage_path",
            message=app.translate("question_storage_path"),
            default=lambda _a: previous.get("storage_path") or "/var/storage",
            ignore=_ignore_unless("ton-storage"),
            validate=lambda _a, v: _validate_storage_path(v),
        ),
        inquirer.Text(
            name="storage_cost",
            message=app.translate("question_storage_cost"),
            default=lambda _a: str(previous.get("storage_cost") or 10),
            ignore=_ignore_unless("ton-storage-provider"),
            validate=lambda _a, v: _validate_positive_int(v),
        ),
        inquirer.Text(
            name="space_to_provide_gigabytes",
            message=_space_message,
            default=_default_space,
            ignore=_ignore_unless("ton-storage-provider"),
            validate=lambda _a, v: _validate_positive_int(v),
        ),
        inquirer.Text(
            name="max_bag_size_gigabytes",
            message=app.translate("question_max_bag_size"),
            default=lambda _a: str(previous.get("max_bag_size_gigabytes") or 40),
            ignore=_ignore_unless("ton-storage-provider"),
            validate=lambda _a, v: _validate_max_bag_size(v),
        ),
        inquirer.Confirm(
            name="auto_update_enabled",
            message=app.translate("question_auto_update"),
            default=bool(previous.get("auto_update_enabled", False)),
        ),
    ]

    answers = inquirer.prompt(questions)
    if answers is None:
        raise RuntimeError("init cancelled by user")
    return cast("dict[str, Any]", answers)


def _run_installs(
    app: MyPyClass,
    registry: ModuleRegistry,
    context: InstallContext,
) -> None:
    """Install modules in registration order."""
    for module in registry.all(enabled_only=False):
        if not isinstance(module, Installable):
            continue
        if not module.mandatory and module.name not in context.selected_modules:
            continue
        module.install(context)


def _save_install_state(
    app: MyPyClass,
    context: InstallContext,
    auto_update_enabled: bool,
) -> None:
    """Persist install answers, global flags, and the initialized marker."""
    answers = Dict()
    answers.user = context.user
    answers.selected_modules = list(context.selected_modules)
    answers.storage_path = (
        str(context.storage_path) if context.storage_path is not None else None
    )
    answers.storage_cost = context.storage_cost
    answers.space_to_provide_gigabytes = context.space_to_provide_gigabytes
    answers.max_bag_size_gigabytes = context.max_bag_size_gigabytes
    answers.auto_update_enabled = auto_update_enabled

    app.db.install_answers = answers
    app.db.auto_update_enabled = auto_update_enabled
    app.db.telemetry_enabled = "telemetry" in context.selected_modules
    app.db.initialized = True
    app.save()


def cmd_init(
    app: MyPyClass,
    registry: ModuleRegistry,
    user: str | None = None,
    selected_modules: tuple[str, ...] | None = None,
    storage_path: Path | None = None,
    storage_cost: int | None = None,
    space_to_provide_gigabytes: int | None = None,
    max_bag_size_gigabytes: int | None = None,
    auto_update_enabled: bool | None = None,
) -> None:
    """Run the init wizard (interactive or non-interactive)."""
    resolved_user = _resolve_user(user)

    final_selected: tuple[str, ...]
    final_storage_path: Path | None
    final_storage_cost: int | None
    final_space: int | None
    final_max_bag: int | None
    final_auto_update: bool

    if _is_non_interactive(
        selected_modules,
        storage_path,
        storage_cost,
        space_to_provide_gigabytes,
        max_bag_size_gigabytes,
        auto_update_enabled,
    ):
        _validate_non_interactive(
            selected_modules=selected_modules,
            storage_path=storage_path,
            storage_cost=storage_cost,
            space_to_provide_gigabytes=space_to_provide_gigabytes,
            max_bag_size_gigabytes=max_bag_size_gigabytes,
            auto_update_enabled=auto_update_enabled,
        )
        assert selected_modules is not None
        assert auto_update_enabled is not None
        final_selected = selected_modules
        final_storage_path = storage_path
        final_storage_cost = storage_cost
        final_space = space_to_provide_gigabytes
        final_max_bag = max_bag_size_gigabytes
        final_auto_update = auto_update_enabled
    else:
        answers = _run_wizard(app, registry)
        final_selected = tuple(answers["selected_modules"])
        final_storage_path = (
            Path(answers["storage_path"]) if answers.get("storage_path") else None
        )
        final_storage_cost = (
            int(answers["storage_cost"]) if answers.get("storage_cost") else None
        )
        final_space = (
            int(answers["space_to_provide_gigabytes"])
            if answers.get("space_to_provide_gigabytes")
            else None
        )
        final_max_bag = (
            int(answers["max_bag_size_gigabytes"])
            if answers.get("max_bag_size_gigabytes")
            else None
        )
        final_auto_update = bool(answers["auto_update_enabled"])

    context = InstallContext(
        user=resolved_user,
        selected_modules=final_selected,
        storage_path=final_storage_path,
        storage_cost=final_storage_cost,
        space_to_provide_gigabytes=final_space,
        max_bag_size_gigabytes=final_max_bag,
    )

    _run_installs(app, registry, context)
    _save_install_state(app, context, final_auto_update)

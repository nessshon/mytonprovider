from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from mypylib import DEBUG, ERROR, INFO, bcolors, color_print

from mytonprovider.modules.core import Updatable
from mytonprovider.types import Channel, UpdateStatus
from mytonprovider.utils import classify_ref

if TYPE_CHECKING:
    from mypylib import MyPyClass

    from mytonprovider.modules import ModuleRegistry


UpdateAction = Literal["up_to_date", "checked", "updated", "failed"]


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of a single module's update attempt."""

    module: str
    action: UpdateAction
    message: str
    target: Channel | None = None


def apply_updates(
    app: MyPyClass,
    modules: list[Updatable],
    *,
    override: Channel | None = None,
    force: bool = False,
    check_only: bool = False,
) -> list[UpdateResult]:
    """Check and optionally install updates for each module."""
    return [_apply_one(app, module, override, force, check_only) for module in modules]


def _apply_one(
    app: MyPyClass,
    module: Updatable,
    override: Channel | None,
    force: bool,
    check_only: bool,
) -> UpdateResult:
    target: Channel | None
    if override is not None:
        target = override
        status = UpdateStatus(available=True, target=override, target_commit=None)
    else:
        try:
            status = module.check_update()
        except Exception as exc:
            app.add_log(f"{module.name}: update check failed: {exc}", ERROR)
            return UpdateResult(module.name, "failed", f"check failed: {exc}")
        target = status.target

    if check_only:
        if status.available and target is not None:
            return UpdateResult(
                module.name, "checked", f"update available: {target.ref}", target,
            )
        return UpdateResult(module.name, "checked", "up to date")

    if not force and (not status.available or target is None):
        return UpdateResult(module.name, "up_to_date", "up to date")

    if target is None:
        # force=True but no target known -- reinstall current channel
        try:
            target = module.get_installed_version().channel
        except Exception as exc:
            app.add_log(f"{module.name}: cannot resolve install target: {exc}", ERROR)
            return UpdateResult(module.name, "failed", f"no target: {exc}")

    args = module.build_update_args(target)
    app.add_log(f"{module.name}: installing {target.ref} ({target.author}/{target.repo})", INFO)
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as exc:
        app.add_log(f"{module.name}: update failed ({exc.returncode})", ERROR)
        return UpdateResult(module.name, "failed", f"exit {exc.returncode}", target)
    except OSError as exc:
        app.add_log(f"{module.name}: update failed to start: {exc}", ERROR)
        return UpdateResult(module.name, "failed", str(exc), target)

    app.add_log(f"{module.name}: updated to {target.ref}", INFO)
    return UpdateResult(module.name, "updated", f"updated to {target.ref}", target)


def _resolve_targets(
    registry: ModuleRegistry,
    target: str | None,
) -> list[Updatable]:
    """Return Updatable modules matching the given target name."""
    if target is None:
        return registry.updatables()
    try:
        module = registry.get(target)
    except KeyError as exc:
        raise RuntimeError(f"Unknown module: {target}") from exc
    if not isinstance(module, Updatable):
        raise RuntimeError(f"Module {target!r} is not updatable")
    return [module]


def _build_override(
    module: Updatable,
    ref: str,
    author: str | None,
    repo: str | None,
) -> Channel:
    """Build an override Channel from the given ref and repo info."""
    final_author = author or module.github_author
    final_repo = repo or module.github_repo
    ref_kind = classify_ref(final_author, final_repo, ref)
    return Channel(author=final_author, repo=final_repo, ref=ref, ref_kind=ref_kind)


def _print_result(result: UpdateResult) -> None:
    """Pretty-print one update result to the terminal."""
    name = bcolors.yellow_text(result.module)
    if result.action == "updated":
        status = bcolors.green_text("updated")
    elif result.action == "up_to_date":
        status = bcolors.green_text("up to date")
    elif result.action == "checked":
        status = bcolors.cyan_text("checked")
    else:  # failed
        status = bcolors.red_text("failed")
    print(f"{name}: {status} — {result.message}")


def cmd_update(
    app: MyPyClass,
    registry: ModuleRegistry,
    target: str | None,
    ref: str | None,
    author: str | None,
    repo: str | None,
    force: bool,
    check: bool,
) -> None:
    """Update modules (or check for available updates)."""
    if check and force:
        raise RuntimeError("--check and --force are mutually exclusive")
    if (author is not None or repo is not None) and ref is None:
        raise RuntimeError("--author/--repo require --ref")
    if ref is not None and target is None:
        raise RuntimeError("--ref requires a target module")

    modules = _resolve_targets(registry, target)
    if not modules:
        color_print("{yellow}no updatable modules found{endc}")
        return

    override: Channel | None = None
    if ref is not None:
        try:
            override = _build_override(modules[0], ref, author, repo)
        except RuntimeError as exc:
            app.add_log(f"ref classification failed: {exc}", DEBUG)
            raise

    results = apply_updates(
        app,
        modules,
        override=override,
        force=force,
        check_only=check,
    )
    for result in results:
        _print_result(result)

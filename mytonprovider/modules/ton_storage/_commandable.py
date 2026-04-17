from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mypycli import Commandable
from mypycli.types import BoxStyle, Color, ColorText, Command
from mypycli.utils.convert import format_bytes, format_rate

from .api.client import StorageApi

if TYPE_CHECKING:
    from mypycli import Application


class CommandableMixin(Commandable):
    __abstract__ = True

    def get_commands(self) -> list[Command]:
        return [
            Command(
                "bags",
                description="Bag operations",
                children=[
                    Command("list", self._cmd_list, "List bags"),
                    Command("info", self._cmd_info, "Show bag", usage="<bag_id>"),
                    Command("add", self._cmd_add, "Add bag", usage="<bag_id> [path]"),
                    Command("remove", self._cmd_remove, "Remove bag", usage="<bag_id>"),
                    Command("verify", self._cmd_verify, "Verify bag", usage="<bag_id>"),
                ],
            ),
            Command(
                "storage",
                description="Storage config",
                children=[
                    Command("log-level", self._cmd_log_level, "Set log level", usage="<0-3>"),
                ],
            ),
        ]

    def _api(self) -> StorageApi:
        return StorageApi(self.db.api_host, self.db.api_port)

    def _cmd_list(self, app: Application[Any], _args: list[str]) -> None:
        try:
            bags = self._api().list_bags().bags
        except Exception as exc:
            app.console.print(f"Failed to list bags: {exc}", color=Color.RED)
            return
        if not bags:
            app.console.print("No bags.", color=Color.YELLOW)
            return
        rows: list[list[ColorText | str]] = [
            [
                ColorText("Bag ID", Color.CYAN),
                ColorText("Progress", Color.CYAN),
                ColorText("Size", Color.CYAN),
                ColorText("Files", Color.CYAN),
                ColorText("Peers", Color.CYAN),
                ColorText("↓ Download", Color.CYAN),
                ColorText("↑ Upload", Color.CYAN),
                ColorText("State", Color.CYAN),
            ]
        ]
        for b in bags:
            state_color = Color.GREEN if b.completed else Color.YELLOW
            progress = round(b.downloaded / b.size * 100, 2) if b.size else 0.0
            rows.append(
                [
                    b.bag_id,
                    f"{progress}%",
                    format_bytes(b.size),
                    str(b.files_count),
                    str(b.peers),
                    format_rate(b.download_speed),
                    format_rate(b.upload_speed),
                    ColorText("complete" if b.completed else "syncing", state_color),
                ]
            )
        app.console.print_table(rows=rows, style=BoxStyle.ROUNDED)

    def _cmd_info(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: bags info <bag_id>", color=Color.RED)
            return
        try:
            details = self._api().get_bag(args[0])
        except Exception as exc:
            app.console.print(f"Failed to get bag: {exc}", color=Color.RED)
            return
        app.console.print_panel(
            items=[
                (ColorText("Bag ID", Color.CYAN), details.bag_id),
                (ColorText("Description", Color.CYAN), details.description or "—"),
                (ColorText("Path", Color.CYAN), details.path or "—"),
                (),
                (ColorText("Size", Color.CYAN), format_bytes(details.size)),
                (ColorText("Downloaded", Color.CYAN), format_bytes(details.downloaded)),
                (ColorText("Files", Color.CYAN), str(details.files_count)),
                (ColorText("Piece size", Color.CYAN), format_bytes(details.piece_size)),
                (),
                (ColorText("Peers", Color.CYAN), str(len(details.peers))),
                (ColorText("Download", Color.CYAN), format_rate(details.download_speed)),
                (ColorText("Upload", Color.CYAN), format_rate(details.upload_speed)),
                (),
                (ColorText("Completed", Color.CYAN), "yes" if details.completed else "no"),
                (ColorText("Seeding", Color.CYAN), "yes" if details.seeding else "no"),
            ],
            header="Bag Info",
            style=BoxStyle.ROUNDED,
        )

    def _cmd_add(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: bags add <bag_id> [path]", color=Color.RED)
            return
        bag_id = args[0]
        path = args[1] if len(args) > 1 else str(self.db.storage_path)
        if not path:
            app.console.print("No storage path available; pass one explicitly.", color=Color.RED)
            return
        try:
            self._api().add_bag(bag_id, path=path)
        except Exception as exc:
            app.console.print(f"Failed to add bag: {exc}", color=Color.RED)
            return
        app.console.print(f"Added {bag_id} → {path}", color=Color.GREEN)

    def _cmd_remove(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: bags remove <bag_id>", color=Color.RED)
            return
        if not app.console.confirm(f"Remove bag {args[0]}?", default=False):
            app.console.print("Cancelled.", color=Color.YELLOW)
            return
        try:
            self._api().remove_bag(args[0])
        except Exception as exc:
            app.console.print(f"Failed to remove bag: {exc}", color=Color.RED)
            return
        app.console.print(f"Removed {args[0]}", color=Color.GREEN)

    def _cmd_verify(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: bags verify <bag_id>", color=Color.RED)
            return
        try:
            ok = self._api().verify_bag(args[0])
        except Exception as exc:
            app.console.print(f"Failed to verify bag: {exc}", color=Color.RED)
            return
        if ok:
            app.console.print(f"Bag {args[0]} is intact.", color=Color.GREEN)
        else:
            app.console.print(f"Bag {args[0]} is corrupted; re-download started.", color=Color.YELLOW)

    def _cmd_log_level(self, app: Application[Any], args: list[str]) -> None:
        if not args:
            app.console.print("Usage: storage log-level <0-3>", color=Color.RED)
            return
        try:
            level = int(args[0])
        except ValueError:
            app.console.print(f"Invalid level: {args[0]}", color=Color.RED)
            return
        try:
            self._api().set_verbosity(level)
        except Exception as exc:
            app.console.print(f"Failed to set log level: {exc}", color=Color.RED)
            return
        app.console.print(f"Log level set to {level}.", color=Color.GREEN)

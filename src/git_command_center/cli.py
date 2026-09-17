from __future__ import annotations

import argparse
import msvcrt
import os
import sys
import time
from pathlib import Path

from .config import ConfigStore
from .repository_service import RepositoryService
from .state import ApplicationState, RepositoryRefresher
from .ui import TerminalUI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grcc", description="Git Repository Command Center")
    parser.add_argument("path", nargs="?", type=Path, help="Repository path (defaults to current directory)")
    parser.add_argument("--no-mouse", action="store_true", help="Disable terminal mouse reporting")
    parser.add_argument("--debug", action="store_true", help="Print Git command history on exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ConfigStore()
    settings = config.load()
    target = (args.path or Path.cwd()).expanduser().resolve()
    state = ApplicationState(message="Loading repository…", loading=True)
    service = RepositoryService()
    refresher = RepositoryRefresher(service)
    ui = TerminalUI(ascii_only=settings.ascii_only)
    # A redirected stream cannot receive Windows console key events. Render a
    # single snapshot so the command is useful in scripts and diagnostics.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        state.repository = service.inspect(target)
        state.loading = False
        state.message = state.repository.error or f"Loaded {state.repository.repository_name}."
        ui.draw(state)
        return 0 if state.repository.is_repository else 2
    ui.start(mouse=settings.use_mouse and not args.no_mouse)
    refresher.refresh(target)
    last_draw = 0.0
    try:
        while True:
            result = refresher.poll()
            if result:
                state.repository = result
                state.loading = False
                state.message = result.error or f"Loaded {result.repository_name}."
                settings.last_repository = str(result.root or target)
                config.save(settings)
            if time.monotonic() - last_draw > 0.08:
                ui.draw(state)
                last_draw = time.monotonic()
            key = _read_key()
            if key is None:
                time.sleep(0.02)
                continue
            if key in {"q", "Q"}:
                break
            if key in {"h", "H", "ESC"}:
                state.show_help = not state.show_help if key != "ESC" else False
            elif key in {"ENTER"}:
                state.dashboard = state.repository is not None and state.repository.is_repository
                if not state.dashboard:
                    state.message = "Open a valid Git repository first."
            elif key in {"r", "R"}:
                if refresher.refresh(target):
                    state.message = "Refreshing repository…"
                else:
                    state.message = "Refresh already in progress."
            elif key in {"o", "O"}:
                new_path = _prompt_path(ui, state)
                if new_path:
                    target = new_path
                    state.dashboard = False
                    state.message = "Opening repository…"
                    refresher.refresh(target)
    except KeyboardInterrupt:
        pass
    finally:
        refresher.close()
        ui.stop()
    if args.debug:
        for command in service.runner.history:
            print(f"git {' '.join(command.args)} [{command.status}/{command.exit_code}] {command.duration_ms}ms", file=sys.stderr)
    return 0


def _read_key() -> str | None:
    if not msvcrt.kbhit():
        return None
    value = msvcrt.getwch()
    if value in {"\r", "\n"}:
        return "ENTER"
    if value == "\x1b":
        return "ESC"
    if value in {"\x00", "\xe0"}:
        msvcrt.getwch()
        return "SPECIAL"
    return value


def _prompt_path(ui: TerminalUI, state: ApplicationState) -> Path | None:
    ui.stop()
    try:
        raw = input("Repository path (blank cancels): ").strip()
    finally:
        ui.start(mouse=False)
    if not raw:
        return None
    return Path(os.path.expandvars(os.path.expanduser(raw))).resolve()

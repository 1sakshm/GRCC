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
from .status_service import WorkingTreeService
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
    working_tree = WorkingTreeService(service.runner)
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
                state.selected_file = min(state.selected_file, max(0, len(state.visible_files()) - 1))
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
            elif state.pending_discard:
                if key in {"y", "Y"}:
                    _discard_selected(state, working_tree, target)
                    state.pending_discard = False
                    refresher.refresh(target)
                elif key in {"n", "N", "ESC"}:
                    state.pending_discard = False
                    state.message = "Discard cancelled."
            elif key in {"ENTER"}:
                if state.dashboard:
                    file = _current_file(state)
                    state.detail_file_path = None if not file or state.detail_file_path == file.path else file.path
                    continue
                state.dashboard = state.repository is not None and state.repository.is_repository
                if not state.dashboard:
                    state.message = "Open a valid Git repository first."
            elif key in {"r", "R"}:
                if refresher.refresh(target):
                    state.message = "Refreshing repository…"
                else:
                    state.message = "Refresh already in progress."
            elif key in {"DOWN", "j", "J"}:
                state.selected_file = min(state.selected_file + 1, max(0, len(state.visible_files()) - 1))
            elif key in {"UP", "k", "K"}:
                state.selected_file = max(0, state.selected_file - 1)
            elif key == " ":
                file = _current_file(state)
                if file:
                    if file.path in state.selected_paths:
                        state.selected_paths.remove(file.path)
                    else:
                        state.selected_paths.add(file.path)
            elif key in {"s", "S"}:
                _stage_selected(state, working_tree, target)
                refresher.refresh(target)
            elif key in {"u", "U"}:
                _unstage_selected(state, working_tree, target)
                refresher.refresh(target)
            elif key in {"d", "D"}:
                if _action_paths(state):
                    state.pending_discard = True
                else:
                    state.message = "Select a modified file to discard."
            elif key in {"f", "F"}:
                modes = ("all", "staged", "unstaged", "untracked", "conflicts")
                state.filter_mode = modes[(modes.index(state.filter_mode) + 1) % len(modes)] if state.filter_mode in modes else "all"
                state.selected_file = 0
            elif key in {"x", "X"}:
                extension = _prompt_text(ui, "Extension filter (example: .py; blank clears): ")
                state.filter_mode = f"ext:{extension.lower()}" if extension else "all"
                state.selected_file = 0
            elif key == "/":
                query = _prompt_text(ui, "Find files (blank clears): ")
                state.search_query = query or ""
                state.selected_file = 0
            elif key in {"c", "C"}:
                file = _current_file(state)
                state.message = working_tree.copy_path(target, file.path) if file else "No file selected."
            elif key in {"e", "E"}:
                file = _current_file(state)
                state.message = working_tree.open_in_editor(target, file.path, settings.external_editor) if file else "No file selected."
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
        return {"H": "UP", "P": "DOWN"}.get(msvcrt.getwch(), "SPECIAL")
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


def _prompt_text(ui: TerminalUI, prompt: str) -> str | None:
    ui.stop()
    try:
        return input(prompt).strip() or None
    finally:
        ui.start(mouse=False)


def _current_file(state: ApplicationState):
    files = state.visible_files()
    return files[state.selected_file] if files else None


def _action_paths(state: ApplicationState) -> list[str]:
    return sorted(state.selected_paths) or ([file.path] if (file := _current_file(state)) else [])


def _stage_selected(state: ApplicationState, service: WorkingTreeService, root: Path) -> None:
    paths = _action_paths(state)
    if not paths:
        state.message = "No file selected."
        return
    result = service.stage(root, paths)
    state.message = f"Staged {len(paths)} file(s)." if result.succeeded else result.stderr.strip() or "Could not stage files."


def _unstage_selected(state: ApplicationState, service: WorkingTreeService, root: Path) -> None:
    paths = _action_paths(state)
    if not paths:
        state.message = "No file selected."
        return
    result = service.unstage(root, paths)
    state.message = f"Unstaged {len(paths)} file(s)." if result.succeeded else result.stderr.strip() or "Could not unstage files."


def _discard_selected(state: ApplicationState, service: WorkingTreeService, root: Path) -> None:
    paths = _action_paths(state)
    result = service.discard(root, paths)
    state.message = f"Discarded {len(paths)} file(s)." if result.succeeded else result.stderr.strip() or "Could not discard files."

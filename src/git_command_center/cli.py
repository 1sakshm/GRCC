from __future__ import annotations

import argparse
import msvcrt
import os
import sys
import time
from pathlib import Path

from .config import ConfigStore
from .commit_service import CommitService
from .management_service import RepositoryManagementService
from .operation_service import OperationService
from .rebase_service import RebaseService
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
    commits = CommitService(service.runner)
    management = RepositoryManagementService(service.runner)
    operations = OperationService(service.runner)
    rebases = RebaseService(service.runner)
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
            if state.view == "diff":
                _handle_diff_key(key, state, working_tree, target, refresher)
                continue
            if state.view == "history":
                _handle_history_key(key, state, commits, target, ui)
                continue
            if state.view == "management":
                _handle_management_key(key, state, management, target, ui, refresher)
                continue
            if state.view == "conflicts":
                _handle_conflict_key(key, state, operations, target, refresher)
                continue
            if state.view == "rebase":
                _handle_rebase_key(key, state, rebases, target)
                continue
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
            elif key == "d":
                _open_diff(state, working_tree, target)
            elif key in {"g", "G"}:
                state.view = "history"
                state.history_skip = state.selected_commit = 0
                _load_history(state, commits, target)
            elif key in {"b", "B", "t", "T", "z", "Z", "w", "W"}:
                state.view = "management"
                state.management_kind = {"b": "branches", "t": "tags", "z": "stashes", "w": "worktrees"}[key.lower()]
                state.selected_management = 0
                _load_management(state, management, target)
            elif key in {"m", "M"}:
                branch = _prompt_text(ui, "Merge branch: ")
                if branch:
                    result = operations.merge(target, branch)
                    state.message = "Merge completed." if result.succeeded else result.stderr.strip() or "Merge needs resolution."
                    _load_conflicts(state, operations, target); refresher.refresh(target)
            elif key in {"x", "X"}:
                _load_conflicts(state, operations, target)
                if state.conflict: state.view = "conflicts"
            elif key in {"p", "P"}:
                commits_to_pick = (_prompt_text(ui, "Commit hash(es) to cherry-pick: ") or "").split()
                if commits_to_pick:
                    result = operations.cherry_pick(target, commits_to_pick); state.message = "Cherry-pick completed." if result.succeeded else result.stderr.strip() or "Cherry-pick needs resolution."; _load_conflicts(state, operations, target); refresher.refresh(target)
            elif key in {"v", "V"}:
                commits_to_revert = (_prompt_text(ui, "Commit hash(es) to revert: ") or "").split()
                if commits_to_revert:
                    result = operations.revert(target, commits_to_revert); state.message = "Revert completed." if result.succeeded else result.stderr.strip() or "Revert needs resolution."; _load_conflicts(state, operations, target); refresher.refresh(target)
            elif key in {"l", "k", "a"}:
                operation = operations.state(target)
                if operation.in_progress and operation.kind:
                    action = {"l": operations.continue_operation, "k": operations.skip_operation, "a": operations.abort_operation}[key]
                    result = action(target, operation.kind); state.message = f"{operation.kind} { {'l':'continued','k':'skipped','a':'aborted'}[key] }." if result.succeeded else result.stderr.strip() or "Operation failed."; refresher.refresh(target)
            elif key in {"i", "I"}:
                state.rebase_upstream = _prompt_text(ui, "Rebase upstream (example: origin/main): ") or ""
                state.rebase_todos = rebases.preview(target, state.rebase_upstream) if state.rebase_upstream else ()
                state.view = "rebase"; state.selected_rebase = 0
            elif key == "D":
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


def _open_diff(state: ApplicationState, service: WorkingTreeService, root: Path) -> None:
    file = _current_file(state)
    if not file:
        state.message = "Select a file to inspect its diff."
        return
    state.view = "diff"
    state.diff_comparison = "staged" if file.staged and not file.unstaged else "working"
    state.diff_file_index = state.diff_hunk_index = 0
    _load_diff(state, service, root, file.path)


def _load_diff(state: ApplicationState, service: WorkingTreeService, root: Path, path: str | None) -> None:
    if state.diff_comparison == "staged":
        state.diff_files = service.diffs.staged(root, path)
    elif state.diff_comparison == "head":
        state.diff_files = service.diffs.against_head(root, path)
    else:
        state.diff_files = service.diffs.working_tree(root, path)
    state.diff_file_index = min(state.diff_file_index, max(0, len(state.diff_files) - 1))
    current = state.current_diff_file()
    state.diff_hunk_index = min(state.diff_hunk_index, max(0, len(current.hunks) - 1 if current else 0))
    state.message = "No textual changes found." if not state.diff_files else f"Loaded {state.diff_comparison} diff."


def _handle_diff_key(key: str, state: ApplicationState, service: WorkingTreeService, root: Path, refresher: RepositoryRefresher) -> None:
    if key == "ESC":
        state.view = "dashboard"
        return
    diff_file = state.current_diff_file()
    if key in {"n", "N", "DOWN"} and diff_file:
        state.diff_hunk_index = min(state.diff_hunk_index + 1, max(0, len(diff_file.hunks) - 1))
    elif key in {"p", "P", "UP"}:
        state.diff_hunk_index = max(0, state.diff_hunk_index - 1)
    elif key == "\t":
        state.diff_layout = "side-by-side" if state.diff_layout == "unified" else "unified"
    elif key in {"w", "W", "i", "I", "a", "A"}:
        state.diff_comparison = {"w": "working", "i": "staged", "a": "head"}[key.lower()]
        state.diff_hunk_index = 0
        _load_diff(state, service, root, diff_file.path if diff_file else None)
    elif key in {"s", "S"} and diff_file and state.current_hunk():
        if state.diff_comparison != "working":
            state.message = "Switch to working-tree comparison to stage a hunk."
            return
        result = service.stage_hunk(root, diff_file, state.current_hunk())
        state.message = "Hunk staged." if result.succeeded else result.stderr.strip() or "Could not stage hunk."
        refresher.refresh(root)
        _load_diff(state, service, root, diff_file.path)
    elif key in {"u", "U"} and diff_file and state.current_hunk():
        if state.diff_comparison != "staged":
            state.message = "Switch to staged comparison to unstage a hunk."
            return
        result = service.unstage_hunk(root, diff_file, state.current_hunk())
        state.message = "Hunk unstaged." if result.succeeded else result.stderr.strip() or "Could not unstage hunk."
        refresher.refresh(root)
        _load_diff(state, service, root, diff_file.path)
    elif key == "D" and diff_file and state.current_hunk():
        if state.diff_comparison != "working":
            state.message = "Switch to working-tree comparison to discard a hunk."
            return
        result = service.diffs.discard_hunk(root, diff_file, state.current_hunk())
        state.message = "Hunk discarded." if result.succeeded else result.stderr.strip() or "Could not discard hunk."
        refresher.refresh(root)
        _load_diff(state, service, root, diff_file.path)


def _load_history(state: ApplicationState, service: CommitService, root: Path) -> None:
    state.commits = service.history(root, limit=80, skip=state.history_skip, query=state.history_query or None, author=state.history_author or None, branch=state.history_branch or None, path=state.history_path or None)
    state.selected_commit = min(state.selected_commit, max(0, len(state.commits) - 1))
    state.message = f"Loaded {len(state.commits)} commits." if state.commits else "No commits matched history filters."


def _handle_history_key(key: str, state: ApplicationState, service: CommitService, root: Path, ui: TerminalUI) -> None:
    if key == "ESC":
        state.view = "dashboard"
        return
    if key in {"DOWN", "j", "J"}:
        state.selected_commit = min(state.selected_commit + 1, max(0, len(state.commits) - 1))
    elif key in {"UP", "k", "K"}:
        state.selected_commit = max(0, state.selected_commit - 1)
    elif key in {"n", "N"}:
        state.history_skip += 80
        state.selected_commit = 0
        _load_history(state, service, root)
    elif key in {"p", "P"}:
        state.history_skip = max(0, state.history_skip - 80)
        state.selected_commit = 0
        _load_history(state, service, root)
    elif key == "/":
        state.history_query = _prompt_text(ui, "Commit message filter (blank clears): ") or ""
        state.history_skip = state.selected_commit = 0
        _load_history(state, service, root)
    elif key in {"a", "A"}:
        state.history_author = _prompt_text(ui, "Author filter (blank clears): ") or ""
        state.history_skip = state.selected_commit = 0
        _load_history(state, service, root)
    elif key in {"b", "B"}:
        state.history_branch = _prompt_text(ui, "Branch or revision filter (blank clears): ") or ""
        state.history_skip = state.selected_commit = 0
        _load_history(state, service, root)
    elif key in {"f", "F"}:
        state.history_path = _prompt_text(ui, "Path history filter (blank clears): ") or ""
        state.history_skip = state.selected_commit = 0
        _load_history(state, service, root)
    elif key == "ENTER":
        commit = state.current_commit()
        if commit:
            detail = service.details(root, commit.hash)
            if detail:
                state.commits = tuple(detail if item.hash == detail.hash else item for item in state.commits)
                state.message = "Loaded selected commit details."


def _load_management(state: ApplicationState, service: RepositoryManagementService, root: Path) -> None:
    state.management_items = {"branches": service.branches, "tags": service.tags, "stashes": service.stashes, "worktrees": service.worktrees}[state.management_kind](root)
    state.selected_management = min(state.selected_management, max(0, len(state.management_items) - 1))
    state.message = f"Loaded {len(state.management_items)} {state.management_kind}."


def _handle_management_key(key: str, state: ApplicationState, service: RepositoryManagementService, root: Path, ui: TerminalUI, refresher: RepositoryRefresher) -> None:
    if key == "ESC": state.view = "dashboard"; return
    if state.pending_management_delete:
        item = state.current_management()
        state.pending_management_delete = False
        if key not in {"y", "Y"} or not item:
            state.message = "Delete cancelled."; return
        result = {"branches": lambda: service.delete_branch(root, item.name), "tags": lambda: service.delete_tag(root, item.name), "stashes": lambda: service.drop_stash(root, item.reference), "worktrees": lambda: service.remove_worktree(root, item.path)}[state.management_kind]()
        state.message = "Operation completed." if result.succeeded else result.stderr.strip() or "Operation failed."
        _load_management(state, service, root); refresher.refresh(root); return
    if key in {"DOWN", "j", "J"}: state.selected_management = min(state.selected_management + 1, max(0, len(state.management_items) - 1)); return
    if key in {"UP", "k", "K"}: state.selected_management = max(0, state.selected_management - 1); return
    if key in {"r", "R"}: _load_management(state, service, root); return
    item = state.current_management()
    result = None
    if key in {"ENTER"} and item:
        if state.management_kind == "branches": result = service.switch_branch(root, item.name)
        elif state.management_kind == "stashes": result = service.apply_stash(root, item.reference)
    elif key in {"n", "N"}:
        if state.management_kind == "branches":
            name = _prompt_text(ui, "New branch name: "); result = service.create_branch(root, name) if name else None
        elif state.management_kind == "tags":
            name = _prompt_text(ui, "New tag name: "); result = service.create_tag(root, name) if name else None
        elif state.management_kind == "stashes":
            result = service.create_stash(root, _prompt_text(ui, "Stash message (blank allowed): "))
        else:
            path = _prompt_text(ui, "New worktree path: "); branch = _prompt_text(ui, "Existing branch: "); result = service.create_worktree(root, path, branch) if path and branch else None
    elif key == "D" and item:
        state.pending_management_delete = True
        state.message = f"Delete {getattr(item, 'name', getattr(item, 'reference', getattr(item, 'path', 'item')))}? Press Y to confirm."
        return
    if result:
        state.message = "Operation completed." if result.succeeded else result.stderr.strip() or "Operation failed."
        _load_management(state, service, root); refresher.refresh(root)


def _load_conflicts(state: ApplicationState, service: OperationService, root: Path) -> None:
    state.operation = service.state(root); state.conflict_files = service.conflicted_files(root)
    state.conflict = service.conflict_file(root, state.conflict_files[0]) if state.conflict_files else None
    state.conflict_index = 0
    if state.conflict: state.message = f"Loaded {len(state.conflict.blocks)} conflict block(s)."


def _handle_conflict_key(key: str, state: ApplicationState, service: OperationService, root: Path, refresher: RepositoryRefresher) -> None:
    if key == "ESC": state.view = "dashboard"; return
    block = state.current_conflict()
    if key in {"n", "N"} and state.conflict: state.conflict_index = min(state.conflict_index + 1, len(state.conflict.blocks) - 1); return
    if key in {"p", "P"}: state.conflict_index = max(0, state.conflict_index - 1); return
    if key in {"1", "2", "3", "4"} and block and state.conflict:
        choice = {"1": "ours", "2": "theirs", "3": "both", "4": "base"}[key]
        result = service.resolve(root, state.conflict.path, block, choice)
        state.message = "Conflict block resolved and staged." if result.succeeded else result.stderr.strip() or "Could not resolve conflict."
        _load_conflicts(state, service, root); refresher.refresh(root)


def _handle_rebase_key(key: str, state: ApplicationState, service: RebaseService, root: Path) -> None:
    if key == "ESC": state.view = "dashboard"; return
    if key in {"DOWN", "j", "J"}: state.selected_rebase = min(state.selected_rebase + 1, max(0, len(state.rebase_todos) - 1)); return
    if key in {"UP", "k", "K"}: state.selected_rebase = max(0, state.selected_rebase - 1); return
    if key in {"a", "A"} and state.rebase_todos:
        todo = state.rebase_todos[state.selected_rebase]; actions = service.actions; action = actions[(actions.index(todo.action) + 1) % len(actions)]
        state.rebase_todos = tuple(type(item)(action, item.commit, item.subject) if index == state.selected_rebase else item for index, item in enumerate(state.rebase_todos)); return
    if key in {"r", "R"} and state.rebase_todos and state.selected_rebase > 0:
        todos = list(state.rebase_todos); todos[state.selected_rebase - 1], todos[state.selected_rebase] = todos[state.selected_rebase], todos[state.selected_rebase - 1]; state.rebase_todos = tuple(todos); state.selected_rebase -= 1; return
    if key == "ENTER" and state.rebase_upstream:
        result = service.start(root, state.rebase_upstream); state.message = "Rebase started." if result.succeeded else result.stderr.strip() or "Rebase did not start."

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

from .models import RepositoryState
from .state import ApplicationState


@dataclass(frozen=True)
class Theme:
    accent: str = "38;5;81"
    muted: str = "38;5;245"
    success: str = "38;5;114"
    warning: str = "38;5;214"
    error: str = "38;5;203"


class TerminalUI:
    def __init__(self, ascii_only: bool = False, theme: Theme | None = None) -> None:
        self.theme = theme or Theme()
        self._interactive = sys.stdout.isatty()
        self.ascii_only = ascii_only or not self._interactive

    def start(self, mouse: bool) -> None:
        if not self._interactive:
            return
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
        if mouse:
            sys.stdout.write("\x1b[?1000h\x1b[?1006h")
        sys.stdout.flush()

    def stop(self) -> None:
        if self._interactive:
            sys.stdout.write("\x1b[?1000l\x1b[?1006l\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()

    def draw(self, state: ApplicationState) -> None:
        width, height = shutil.get_terminal_size((78, 24))
        if width < 44 or height < 12:
            frame = ["Terminal too small — resize to at least 44 × 12.", "[Q] Quit"]
        elif state.show_help:
            frame = self._help(width)
        elif state.view == "diff":
            frame = self._diff(state, width, height)
        elif state.view == "history":
            frame = self._history(state, width, height)
        elif state.dashboard:
            frame = self._dashboard(state, width)
        else:
            frame = self._welcome(state, width)
        content = "\n".join(line[:width].ljust(width) for line in frame[:height])
        if self._interactive:
            sys.stdout.write("\x1b[H\x1b[2J" + content)
        else:
            sys.stdout.write(content + "\n")
        sys.stdout.flush()

    def _welcome(self, state: ApplicationState, width: int) -> list[str]:
        lines = self._box("GIT COMMAND CENTER", width)
        lines.extend(self._repository_rows(state.repository, width))
        lines.append(self._border(width, "bottom"))
        lines.extend([self._row("[Enter] Open Dashboard", width), self._row("[O] Open Repository", width),
                      self._row("[R] Refresh  [H] Help  [Q] Quit", width), self._border(width, "bottom"),
                      self._status(state.message, width)])
        return lines

    def _diff(self, state: ApplicationState, width: int, height: int) -> list[str]:
        diff_file = state.current_diff_file()
        title = f"DIFF - {diff_file.path if diff_file else 'No change selected'}"
        rows = self._box(title, width)
        if not diff_file:
            rows.append(self._row("No diff is available for this comparison.", width, self.theme.muted))
        elif diff_file.binary:
            rows.append(self._row("Binary file: textual diff is unavailable.", width, self.theme.warning))
        elif not diff_file.hunks:
            rows.append(self._row("No textual hunks.", width, self.theme.muted))
        else:
            hunk = state.current_hunk()
            assert hunk is not None
            rows.append(self._row(f"{state.diff_comparison} · {state.diff_layout} · Hunk {state.diff_hunk_index + 1}/{len(diff_file.hunks)}  +{hunk.additions} -{hunk.deletions}", width, self.theme.accent))
            rows.append(self._row(f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@ {hunk.heading}", width, self.theme.muted))
            available = max(4, height - 8)
            if state.diff_layout == "side-by-side":
                rows.extend(self._side_by_side(hunk.lines, width, available))
            else:
                rows.extend(self._unified(hunk.lines, width, available))
        rows.append(self._border(width, "bottom"))
        rows.append(self._row("[N/P] Hunk  [Tab] Layout  [W/I/A] Compare  [S] Stage  [U] Unstage", width))
        rows.append(self._row("[D] Discard hunk  [Esc] Back", width))
        rows.append(self._status(state.message, width))
        if self.ascii_only:
            rows = [row.encode("ascii", "replace").decode("ascii") for row in rows]
        return rows

    def _history(self, state: ApplicationState, width: int, height: int) -> list[str]:
        rows = self._box("COMMIT HISTORY", width)
        if not state.commits:
            rows.append(self._row("No commits match the active filters.", width, self.theme.muted))
        else:
            capacity = max(4, height - 9)
            start = max(0, min(state.selected_commit - capacity + 1, len(state.commits) - capacity))
            for index, commit in enumerate(state.commits[start:start + capacity], start):
                cursor = ">" if index == state.selected_commit else " "
                decoration = f" [{', '.join(commit.decorations)}]" if commit.decorations else ""
                rows.append(self._row(f"{cursor} {commit.graph:<9} {commit.short_hash} {commit.subject}{decoration}", width))
            selected = state.current_commit()
            if selected:
                rows.append(self._border(width, "bottom"))
                rows.append(self._row(f"Author: {selected.author} <{selected.author_email}>  Date: {selected.timestamp[:10]}", width))
                rows.append(self._row(f"Parents: {', '.join(parent[:8] for parent in selected.parents) or 'none'}  Files: {selected.files_changed}  +{selected.additions} -{selected.deletions}", width))
        rows.append(self._border(width, "bottom"))
        rows.append(self._row("[Up/Down] Select [Enter] Details [N/P] Page [/] Msg [A] Author [B] Branch [F] Path", width))
        rows.append(self._row("[Esc] Back", width))
        rows.append(self._status(state.message, width))
        if self.ascii_only:
            rows = [row.encode("ascii", "replace").decode("ascii") for row in rows]
        return rows

    def _unified(self, lines, width: int, capacity: int) -> list[str]:
        prefix = {"context": " ", "addition": "+", "deletion": "-", "meta": "\\"}
        rows = []
        for line in lines[:capacity]:
            old = "" if line.old_line is None else str(line.old_line)
            new = "" if line.new_line is None else str(line.new_line)
            rows.append(self._row(f"{old:>5} {new:>5} {prefix[line.type]} {line.content}", width))
        return rows

    def _side_by_side(self, lines, width: int, capacity: int) -> list[str]:
        half = max(12, (width - 7) // 2)
        rows, pending = [], None
        for line in lines:
            if len(rows) >= capacity:
                break
            if line.type == "deletion":
                pending = line
                continue
            if line.type == "addition" and pending:
                rows.append(self._row(f"-{pending.old_line or '':>4} {pending.content[:half]} | +{line.new_line or '':>4} {line.content[:half]}", width))
                pending = None
            elif line.type == "addition":
                rows.append(self._row(f"{'':{half + 6}} | +{line.new_line or '':>4} {line.content[:half]}", width))
            else:
                if pending:
                    rows.append(self._row(f"-{pending.old_line or '':>4} {pending.content[:half]} |", width))
                    pending = None
                rows.append(self._row(f" {line.old_line or '':>4} {line.content[:half]} |  {line.new_line or '':>4} {line.content[:half]}", width))
        if pending and len(rows) < capacity:
            rows.append(self._row(f"-{pending.old_line or '':>4} {pending.content[:half]} |", width))
        return rows

    def _dashboard(self, state: ApplicationState, width: int) -> list[str]:
        repo = state.repository
        title = f"DASHBOARD {'-' if self.ascii_only else '·'} {repo.repository_name if repo else 'No repository'}"
        lines = self._box(title, width)
        if repo and repo.is_repository:
            lines.extend(self._dashboard_header(repo, width))
            lines.extend(self._working_tree(state, width))
        else:
            lines.extend(self._repository_rows(repo, width))
        lines.append(self._border(width, "bottom"))
        controls = "[S] Stage [U] Unstage [d] Diff [G] Graph [D] Discard [Space] Select [F] Filter"
        lines.append(self._row(controls, width))
        lines.append(self._row("[E] Editor [C] Copy path [R] Refresh [O] Open [H] Help [Q] Quit", width))
        if state.pending_discard:
            lines.append(self._row("Discard selected changes? [Y] Yes  [N] No", width, self.theme.warning))
        lines.append(self._status(state.message, width))
        return lines

    def _dashboard_header(self, repo: RepositoryState, width: int) -> list[str]:
        upstream = repo.upstream or "no upstream"
        ahead_behind = f"+{repo.ahead} -{repo.behind}" if self.ascii_only else f"↑{repo.ahead} ↓{repo.behind}"
        remote_url = repo.remotes[0].fetch_url if repo.remotes else "no remote"
        return [self._row(f"{repo.repository_name}   {repo.branch or 'detached'}   {ahead_behind}", width),
                self._row(f"HEAD {(repo.head or 'No commits')[:12]}   {upstream}", width),
                self._row(f"Remote: {remote_url or 'no remote'}", width), self._border(width, "bottom"),
                self._row(f"Branches {repo.branch_count}   Commits {repo.commit_count}   Tags {repo.tag_count}   Stashes {repo.stash_count}", width),
                self._row(f"User: {repo.user_name or 'not configured'} <{repo.user_email or 'not configured'}>", width),
                self._row(f"Size: {_format_size(repo.repository_size)}   Latest: {repo.head_subject or 'No commits yet'}", width), self._border(width, "bottom")]

    def _working_tree(self, state: ApplicationState, width: int) -> list[str]:
        files = state.visible_files()
        separator = "-" if self.ascii_only else "·"
        label = f"WORKING TREE {separator} {state.filter_mode} {separator} {len(files)} files"
        rows = [self._row(label, width, self.theme.accent)]
        if not files:
            rows.append(self._row("Clean working tree (or no files match the filter).", width, self.theme.success))
            return rows
        capacity = 7
        start = max(0, min(state.selected_file - capacity + 1, len(files) - capacity))
        for number, file in enumerate(files[start:start + capacity], start):
            cursor = ">" if number == state.selected_file else " "
            checked = "*" if file.path in state.selected_paths else " "
            rename = f" {'<-' if self.ascii_only else '←'} {file.original_path}" if file.original_path else ""
            rows.append(self._row(f"{cursor}[{checked}] {file.code:2} {file.path}{rename}", width))
        if len(files) > capacity:
            rows.append(self._row(f"Showing {start + 1}-{min(start + capacity, len(files))} of {len(files)}", width, self.theme.muted))
        selected = state.visible_files()[state.selected_file] if state.visible_files() else None
        if selected and state.detail_file_path == selected.path:
            location = f" from {selected.original_path}" if selected.original_path else ""
            rows.append(self._row(f"Details: {selected.kind}; index={selected.index_status!r}; worktree={selected.worktree_status!r}{location}", width, self.theme.muted))
        return rows

    def _help(self, width: int) -> list[str]:
        lines = self._box("HELP", width)
        entries = ["Up/Down Navigate files", "Enter  Toggle file metadata", "Space Select file", "S/U Stage or unstage", "d      Open selected-file diff", "D      Discard (confirm)", "F/X    Cycle filters / filter extension", "/      Search file names", "E/C    External editor / copy path", "R      Refresh", "H/Esc  Close help", "Q      Quit"]
        lines.extend(self._row(entry, width) for entry in entries)
        lines += [self._border(width, "bottom"), self._row("All Git operations run through the application service layer.", width)]
        return lines

    def _repository_rows(self, repo: RepositoryState | None, width: int) -> list[str]:
        if repo is None:
            return [self._row("Repository: loading…", width)]
        if repo.error:
            return [self._row(f"Repository: {repo.requested_path}", width), self._row(f"Error: {repo.error}", width, self.theme.error)]
        remote = repo.remotes[0].name if repo.remotes else "none"
        mode = "detached HEAD" if repo.detached_head else repo.branch or "unborn branch"
        if repo.bare:
            mode += " · bare"
        return [self._row(f"Repository: {repo.root}", width), self._row(f"Branch:     {mode}", width),
                self._row(f"HEAD:       {(repo.head or 'No commits')[:12]}", width),
                self._row(f"Remote:     {remote}", width), self._row(f"Status:     {repo.status.label}", width),
                self._row(f"Git:        {repo.git_version or 'unavailable'}", width)]

    def _box(self, title: str, width: int) -> list[str]:
        return [self._border(width, "top", title)]

    def _border(self, width: int, position: str, title: str = "") -> str:
        horizontal = "-" if self.ascii_only else "─"
        left, right = ("+", "+") if self.ascii_only else (("┌", "┐") if position == "top" else ("└", "┘"))
        label = f" {title} " if title else ""
        return left + label + horizontal * max(0, width - 2 - len(label)) + right

    def _row(self, value: str, width: int, color: str | None = None) -> str:
        inner = value[: width - 4].ljust(width - 4)
        rendered = f"\x1b[{color}m{inner}\x1b[0m" if color and self._interactive else inner
        side = "|" if self.ascii_only else "│"
        return f"{side} {rendered} {side}"

    def _status(self, message: str, width: int) -> str:
        return self._row(message, width, self.theme.muted)


def _format_size(size: int) -> str:
    for unit, divisor in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if size >= divisor:
            return f"{size / divisor:.1f} {unit}"
    return f"{size} bytes"

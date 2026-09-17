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

    def _dashboard(self, state: ApplicationState, width: int) -> list[str]:
        repo = state.repository
        title = f"DASHBOARD · {repo.repository_name if repo else 'No repository'}"
        lines = self._box(title, width)
        lines.extend(self._repository_rows(repo, width))
        if repo and repo.is_repository:
            lines.append(self._row(f"Latest: {repo.head_subject or 'No commits yet'}", width))
            lines.append(self._row(f"Working tree: {repo.status.label}", width))
        lines.append(self._border(width, "bottom"))
        lines.append(self._row("[R] Refresh  [O] Open Repository  [H] Help  [Q] Quit", width))
        lines.append(self._status(state.message, width))
        return lines

    def _help(self, width: int) -> list[str]:
        lines = self._box("HELP", width)
        entries = ["Enter  Open dashboard", "O      Open another repository", "R      Refresh state", "H/Esc  Close help", "Q      Quit"]
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

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .git_runner import GitCommandRunner
from .models import GitCommandResult


class WorkingTreeService:
    """Mutating working-tree actions, deliberately kept outside TUI code."""

    def __init__(self, runner: GitCommandRunner) -> None:
        self.runner = runner

    def stage(self, root: Path, paths: list[str]) -> GitCommandResult:
        return self.runner.run(["add", "--", *paths], cwd=root)

    def unstage(self, root: Path, paths: list[str]) -> GitCommandResult:
        return self.runner.run(["restore", "--staged", "--", *paths], cwd=root)

    def discard(self, root: Path, paths: list[str]) -> GitCommandResult:
        return self.runner.run(["restore", "--worktree", "--", *paths], cwd=root)

    def copy_path(self, root: Path, path: str) -> str:
        full_path = str((root / path).resolve())
        try:
            subprocess.run(["clip"], input=full_path, text=True, check=True, shell=False)
            return "Copied path to clipboard."
        except (OSError, subprocess.CalledProcessError):
            return full_path

    def open_in_editor(self, root: Path, path: str, editor: str | None) -> str:
        if not editor:
            return "Set external_editor in settings to open files."
        try:
            subprocess.Popen([editor, str((root / path).resolve())], shell=False)
            return f"Opened {path}."
        except OSError as error:
            return f"Could not open editor: {error}"

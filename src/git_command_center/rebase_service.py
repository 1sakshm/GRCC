from __future__ import annotations
from pathlib import Path
from .git_runner import GitCommandRunner
from .models import GitCommandResult, RebaseTodo

class RebaseService:
    actions = ("pick", "reword", "edit", "squash", "fixup", "drop")
    def __init__(self, runner: GitCommandRunner): self.runner = runner
    def preview(self, root: Path, upstream: str) -> tuple[RebaseTodo, ...]:
        result = self.runner.run(["log", "--reverse", "--format=%H%x1f%s", f"{upstream}..HEAD"], cwd=root)
        return tuple(RebaseTodo("pick", *row.split("\x1f", 1)) for row in result.stdout.splitlines() if "\x1f" in row)
    def continue_rebase(self, root: Path) -> GitCommandResult: return self.runner.run(["rebase", "--continue"], cwd=root, timeout=60)
    def abort_rebase(self, root: Path) -> GitCommandResult: return self.runner.run(["rebase", "--abort"], cwd=root, timeout=60)
    def skip_rebase(self, root: Path) -> GitCommandResult: return self.runner.run(["rebase", "--skip"], cwd=root, timeout=60)
    def start(self, root: Path, upstream: str, autosquash: bool = False) -> GitCommandResult:
        return self.runner.run(["-c", "sequence.editor=true", "rebase", "--interactive", *( ["--autosquash"] if autosquash else []), upstream], cwd=root, timeout=60)

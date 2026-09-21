from __future__ import annotations
from pathlib import Path
from .git_runner import GitCommandRunner
from .models import BlameLine, TimelineCommit

class TimeMachineService:
    def __init__(self, runner: GitCommandRunner): self.runner = runner
    def timeline(self, root: Path, limit: int = 120) -> tuple[TimelineCommit, ...]:
        result = self.runner.run(["log", f"--max-count={limit}", "--format=%H%x1f%aI%x1f%s"], cwd=root)
        return tuple(TimelineCommit(*row.split("\x1f", 2)) for row in result.stdout.splitlines() if row.count("\x1f") == 2)
    def files_at(self, root: Path, commit: str) -> tuple[str, ...]:
        result = self.runner.run(["ls-tree", "-r", "--name-only", commit], cwd=root, timeout=30)
        return tuple(path for path in result.stdout.splitlines() if path)
    def file_history(self, root: Path, path: str, limit: int = 120) -> tuple[TimelineCommit, ...]:
        result = self.runner.run(["log", "--follow", f"--max-count={limit}", "--format=%H%x1f%aI%x1f%s", "--", path], cwd=root)
        return tuple(TimelineCommit(*row.split("\x1f", 2)) for row in result.stdout.splitlines() if row.count("\x1f") == 2)
    def blame(self, root: Path, path: str, commit: str = "HEAD") -> tuple[BlameLine, ...]:
        result = self.runner.run(["blame", "--line-porcelain", commit, "--", path], cwd=root, timeout=30)
        lines, current, number = [], {}, 0
        for row in result.stdout.splitlines():
            if row.startswith("\t"):
                number += 1; lines.append(BlameLine(number, current.get("hash", ""), current.get("author", ""), current.get("author-time", ""), row[1:])); current = {}
            elif row and " " in row:
                key, value = row.split(" ", 1)
                if len(key) == 40: current["hash"] = key
                else: current[key] = value
        return tuple(lines)

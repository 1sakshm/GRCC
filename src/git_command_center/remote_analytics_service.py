from __future__ import annotations
from collections import Counter
from pathlib import Path
from .git_runner import GitCommandRunner
from .models import AnalyticsSnapshot, GitCommandResult

class RemoteAnalyticsService:
    def __init__(self, runner: GitCommandRunner): self.runner = runner
    def fetch(self, root: Path, remote: str = "origin") -> GitCommandResult: return self.runner.run(["fetch", "--prune", remote], cwd=root, timeout=120)
    def pull(self, root: Path, remote: str = "origin") -> GitCommandResult: return self.runner.run(["pull", remote], cwd=root, timeout=120)
    def push(self, root: Path, remote: str = "origin", force_with_lease: bool = False) -> GitCommandResult: return self.runner.run(["push", *( ["--force-with-lease"] if force_with_lease else []), remote], cwd=root, timeout=120)
    def add_remote(self, root: Path, name: str, url: str) -> GitCommandResult: return self.runner.run(["remote", "add", name, url], cwd=root)
    def remove_remote(self, root: Path, name: str) -> GitCommandResult: return self.runner.run(["remote", "remove", name], cwd=root)
    def analytics(self, root: Path) -> AnalyticsSnapshot:
        count = self.runner.run(["rev-list", "--all", "--count"], cwd=root).stdout.strip(); total = int(count) if count.isdigit() else 0
        authors = Counter(self.runner.run(["log", "--all", "--format=%aN"], cwd=root, timeout=30).stdout.splitlines())
        paths = Counter(self.runner.run(["log", "--all", "--name-only", "--format="], cwd=root, timeout=30).stdout.splitlines())
        languages = Counter()
        for path in paths:
            suffix = Path(path).suffix.lower().lstrip(".") or "other"; languages[suffix] += 1
        return AnalyticsSnapshot(total, tuple(authors.most_common(10)), tuple((p,c) for p,c in paths.most_common(10) if p), tuple(languages.most_common(10)))

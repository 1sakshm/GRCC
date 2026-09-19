from __future__ import annotations

from pathlib import Path

from .git_runner import GitCommandRunner
from .models import BranchRecord, GitCommandResult, StashRecord, TagRecord, WorktreeRecord


class RepositoryManagementService:
    """Branch, tag, stash, and worktree operations outside the TUI layer."""
    def __init__(self, runner: GitCommandRunner) -> None:
        self.runner = runner

    def branches(self, root: Path, remote: bool = False) -> tuple[BranchRecord, ...]:
        ref = "refs/remotes" if remote else "refs/heads"
        result = self.runner.run(["for-each-ref", "--sort=-committerdate", "--format=%(refname:short)\x1f%(upstream:short)\x1f%(HEAD)\x1f%(committerdate:iso-strict)\x1e", ref], cwd=root)
        return tuple(BranchRecord(parts[0], parts[1] or None, parts[2] == "*", remote, parts[3] or None) for parts in _records(result.stdout, 4))

    def tags(self, root: Path) -> tuple[TagRecord, ...]:
        result = self.runner.run(["for-each-ref", "--sort=-creatordate", "--format=%(refname:short)\x1f%(objectname)\x1f%(objecttype)\x1f%(creatordate:iso-strict)\x1e", "refs/tags"], cwd=root)
        return tuple(TagRecord(parts[0], parts[1], parts[2] == "tag", parts[3] or None) for parts in _records(result.stdout, 4))

    def stashes(self, root: Path) -> tuple[StashRecord, ...]:
        result = self.runner.run(["stash", "list", "--format=%gd%x1f%gs%x1f%H%x1e"], cwd=root)
        return tuple(StashRecord(parts[0], parts[1], parts[2]) for parts in _records(result.stdout, 3))

    def worktrees(self, root: Path) -> tuple[WorktreeRecord, ...]:
        result = self.runner.run(["worktree", "list", "--porcelain"], cwd=root)
        records, current = [], {}
        for line in result.stdout.splitlines() + [""]:
            if not line:
                if current:
                    records.append(WorktreeRecord(current.get("worktree", ""), current.get("HEAD", ""), current.get("branch", "").removeprefix("refs/heads/") or None, "bare" in current, "locked" in current))
                    current = {}
            else:
                key, _, value = line.partition(" ")
                current[key] = value
        return tuple(records)

    def create_branch(self, root: Path, name: str, start: str = "HEAD") -> GitCommandResult: return self.runner.run(["branch", name, start], cwd=root)
    def switch_branch(self, root: Path, name: str) -> GitCommandResult: return self.runner.run(["switch", name], cwd=root)
    def delete_branch(self, root: Path, name: str, force: bool = False) -> GitCommandResult: return self.runner.run(["branch", "-D" if force else "-d", name], cwd=root)
    def rename_branch(self, root: Path, old: str, new: str) -> GitCommandResult: return self.runner.run(["branch", "-m", old, new], cwd=root)
    def set_upstream(self, root: Path, branch: str, upstream: str) -> GitCommandResult: return self.runner.run(["branch", "--set-upstream-to", upstream, branch], cwd=root)
    def create_tag(self, root: Path, name: str, target: str = "HEAD", message: str | None = None) -> GitCommandResult: return self.runner.run(["tag", "-a", name, target, "-m", message or name] if message is not None else ["tag", name, target], cwd=root)
    def delete_tag(self, root: Path, name: str) -> GitCommandResult: return self.runner.run(["tag", "-d", name], cwd=root)
    def create_stash(self, root: Path, message: str | None = None, include_untracked: bool = False) -> GitCommandResult: return self.runner.run(["stash", "push", *( ["--include-untracked"] if include_untracked else []), *( ["-m", message] if message else [])], cwd=root)
    def apply_stash(self, root: Path, reference: str, pop: bool = False) -> GitCommandResult: return self.runner.run(["stash", "pop" if pop else "apply", reference], cwd=root)
    def drop_stash(self, root: Path, reference: str) -> GitCommandResult: return self.runner.run(["stash", "drop", reference], cwd=root)
    def create_worktree(self, root: Path, path: str, branch: str) -> GitCommandResult: return self.runner.run(["worktree", "add", path, branch], cwd=root, timeout=60)
    def remove_worktree(self, root: Path, path: str, force: bool = False) -> GitCommandResult: return self.runner.run(["worktree", "remove", *( ["--force"] if force else []), path], cwd=root, timeout=60)
    def prune_worktrees(self, root: Path) -> GitCommandResult: return self.runner.run(["worktree", "prune"], cwd=root)


def _records(output: str, fields: int):
    for raw in output.split("\x1e"):
        parts = raw.strip("\r\n").split("\x1f")
        if len(parts) >= fields and parts[0]:
            yield parts

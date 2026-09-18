from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


CommandStatus = Literal["ok", "failed", "timed_out", "cancelled"]


@dataclass(frozen=True)
class GitCommandResult:
    args: tuple[str, ...]
    cwd: Path | None
    stdout: str
    stderr: str
    exit_code: int | None
    status: CommandStatus
    duration_ms: int

    @property
    def succeeded(self) -> bool:
        return self.status == "ok" and self.exit_code == 0


@dataclass(frozen=True)
class Remote:
    name: str
    fetch_url: str | None
    push_url: str | None


@dataclass(frozen=True)
class WorkingTreeSummary:
    staged: int = 0
    modified: int = 0
    untracked: int = 0
    conflicted: int = 0
    ignored: int = 0

    @property
    def label(self) -> str:
        values = []
        if self.staged:
            values.append(f"{self.staged} staged")
        if self.modified:
            values.append(f"{self.modified} modified")
        if self.untracked:
            values.append(f"{self.untracked} untracked")
        if self.conflicted:
            values.append(f"{self.conflicted} conflicted")
        return ", ".join(values) or "clean"


FileKind = Literal["modified", "added", "deleted", "renamed", "copied", "untracked", "ignored", "conflicted"]


@dataclass(frozen=True)
class FileChange:
    path: str
    index_status: str = " "
    worktree_status: str = " "
    kind: FileKind = "modified"
    original_path: str | None = None

    @property
    def staged(self) -> bool:
        return self.index_status != " " and self.kind not in {"untracked", "ignored"}

    @property
    def unstaged(self) -> bool:
        return self.worktree_status != " " or self.kind == "untracked"

    @property
    def code(self) -> str:
        if self.kind == "untracked":
            return "?"
        if self.kind == "ignored":
            return "!"
        if self.kind == "conflicted":
            return "U"
        return f"{self.index_status}{self.worktree_status}".strip() or "M"


@dataclass(frozen=True)
class RepositoryState:
    requested_path: Path
    root: Path | None = None
    git_version: str | None = None
    branch: str | None = None
    head: str | None = None
    head_subject: str | None = None
    detached_head: bool = False
    bare: bool = False
    remotes: tuple[Remote, ...] = ()
    status: WorkingTreeSummary = field(default_factory=WorkingTreeSummary)
    files: tuple[FileChange, ...] = ()
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    stash_count: int = 0
    tag_count: int = 0
    branch_count: int = 0
    commit_count: int = 0
    repository_size: int = 0
    user_name: str | None = None
    user_email: str | None = None
    loaded_at: datetime = field(default_factory=datetime.now)
    error: str | None = None

    @property
    def repository_name(self) -> str:
        return (self.root or self.requested_path).name

    @property
    def is_repository(self) -> bool:
        return self.root is not None and self.error is None

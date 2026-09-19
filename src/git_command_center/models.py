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
DiffLineType = Literal["context", "addition", "deletion", "meta"]


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
class DiffLine:
    type: DiffLineType
    content: str
    old_line: int | None = None
    new_line: int | None = None


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    heading: str
    lines: tuple[DiffLine, ...]
    patch: str

    @property
    def additions(self) -> int:
        return sum(line.type == "addition" for line in self.lines)

    @property
    def deletions(self) -> int:
        return sum(line.type == "deletion" for line in self.lines)


@dataclass(frozen=True)
class DiffFile:
    old_path: str | None
    new_path: str | None
    status: str
    hunks: tuple[DiffHunk, ...] = ()
    header: tuple[str, ...] = ()
    binary: bool = False

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or "unknown"

    @property
    def additions(self) -> int:
        return sum(hunk.additions for hunk in self.hunks)

    @property
    def deletions(self) -> int:
        return sum(hunk.deletions for hunk in self.hunks)


@dataclass(frozen=True)
class CommitRecord:
    hash: str
    parents: tuple[str, ...]
    author: str
    author_email: str
    timestamp: str
    subject: str
    decorations: tuple[str, ...] = ()
    graph: str = "*"
    lane: int = 0
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0

    @property
    def short_hash(self) -> str:
        return self.hash[:8]


@dataclass(frozen=True)
class BranchRecord:
    name: str
    upstream: str | None = None
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

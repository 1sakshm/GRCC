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
    loaded_at: datetime = field(default_factory=datetime.now)
    error: str | None = None

    @property
    def repository_name(self) -> str:
        return (self.root or self.requested_path).name

    @property
    def is_repository(self) -> bool:
        return self.root is not None and self.error is None


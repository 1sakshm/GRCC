from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .models import AnalyticsSnapshot, CommitRecord, ConflictFile, DiffFile, OperationState, RebaseTodo, RepositoryState, TimelineCommit
from .repository_service import RepositoryService


@dataclass
class ApplicationState:
    repository: RepositoryState | None = None
    message: str = "Press H for help."
    show_help: bool = False
    dashboard: bool = False
    loading: bool = False
    selected_file: int = 0
    selected_paths: set[str] = field(default_factory=set)
    filter_mode: str = "all"
    search_query: str = ""
    pending_discard: bool = False
    detail_file_path: str | None = None
    view: str = "dashboard"
    diff_files: tuple[DiffFile, ...] = ()
    diff_file_index: int = 0
    diff_hunk_index: int = 0
    diff_comparison: str = "working"
    diff_layout: str = "unified"
    commits: tuple[CommitRecord, ...] = ()
    selected_commit: int = 0
    history_skip: int = 0
    history_query: str = ""
    history_author: str = ""
    history_branch: str = ""
    history_path: str = ""
    management_kind: str = "branches"
    management_items: tuple = ()
    selected_management: int = 0
    pending_management_delete: bool = False
    operation: OperationState = field(default_factory=OperationState)
    conflict_files: tuple[str, ...] = ()
    conflict: ConflictFile | None = None
    conflict_index: int = 0
    rebase_todos: tuple[RebaseTodo, ...] = ()
    selected_rebase: int = 0
    rebase_upstream: str = ""
    timeline: tuple[TimelineCommit, ...] = ()
    selected_timeline: int = 0
    analytics: AnalyticsSnapshot | None = None

    def current_conflict(self):
        return self.conflict.blocks[self.conflict_index] if self.conflict and self.conflict.blocks else None

    def current_management(self):
        return self.management_items[self.selected_management] if self.management_items else None

    def current_commit(self) -> CommitRecord | None:
        return self.commits[self.selected_commit] if self.commits else None

    def visible_files(self):
        if not self.repository:
            return ()
        files = self.repository.files
        if self.filter_mode == "staged":
            files = tuple(file for file in files if file.staged)
        elif self.filter_mode == "unstaged":
            files = tuple(file for file in files if file.unstaged and file.kind != "untracked")
        elif self.filter_mode == "untracked":
            files = tuple(file for file in files if file.kind == "untracked")
        elif self.filter_mode == "conflicts":
            files = tuple(file for file in files if file.kind == "conflicted")
        elif self.filter_mode.startswith("ext:"):
            suffix = self.filter_mode.removeprefix("ext:").lower()
            files = tuple(file for file in files if file.path.lower().endswith(suffix))
        if self.search_query:
            needle = self.search_query.lower()
            files = tuple(file for file in files if needle in file.path.lower())
        return files

    def current_diff_file(self) -> DiffFile | None:
        return self.diff_files[self.diff_file_index] if self.diff_files else None

    def current_hunk(self):
        file = self.current_diff_file()
        return file.hunks[self.diff_hunk_index] if file and file.hunks else None


class RepositoryRefresher:
    """Background repository inspection with UI-thread result delivery."""
    def __init__(self, service: RepositoryService) -> None:
        self._service = service
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="git-refresh")
        self._results: queue.SimpleQueue[RepositoryState] = queue.SimpleQueue()
        self._pending = False

    def refresh(self, path: Path) -> bool:
        if self._pending:
            return False
        self._pending = True
        future = self._executor.submit(self._service.inspect, path)
        future.add_done_callback(lambda result: self._results.put(result.result()))
        return True

    def poll(self) -> RepositoryState | None:
        try:
            result = self._results.get_nowait()
            self._pending = False
            return result
        except queue.Empty:
            return None

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

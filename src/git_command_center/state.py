from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .models import RepositoryState
from .repository_service import RepositoryService


@dataclass
class ApplicationState:
    repository: RepositoryState | None = None
    message: str = "Press H for help."
    show_help: bool = False
    dashboard: bool = False
    loading: bool = False


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


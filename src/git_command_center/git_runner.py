from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .models import GitCommandResult


class GitCommandRunner:
    """Single gateway for Git subprocesses; UI code never invokes Git directly."""

    def __init__(self, history_limit: int = 100) -> None:
        self._history: deque[GitCommandResult] = deque(maxlen=history_limit)
        self._history_lock = threading.Lock()

    @property
    def history(self) -> tuple[GitCommandResult, ...]:
        with self._history_lock:
            return tuple(self._history)

    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path | None = None,
        timeout: float = 12.0,
        cancellation: threading.Event | None = None,
    ) -> GitCommandResult:
        if not args or any(not isinstance(arg, str) or "\x00" in arg for arg in args):
            raise ValueError("Git arguments must be non-empty strings without NUL bytes")
        safe_cwd = Path(cwd).resolve() if cwd is not None else None
        command = ("git", *args)
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=safe_cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        status = "ok"
        stdout = stderr = ""
        try:
            while process.poll() is None:
                if cancellation and cancellation.is_set():
                    status = "cancelled"
                    process.terminate()
                    break
                if time.monotonic() - started > timeout:
                    status = "timed_out"
                    process.kill()
                    break
                time.sleep(0.025)
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            status = "timed_out"
            process.kill()
            stdout, stderr = process.communicate()
        result = GitCommandResult(
            args=tuple(args), cwd=safe_cwd, stdout=stdout, stderr=stderr,
            exit_code=process.returncode, status=status,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        with self._history_lock:
            self._history.append(result)
        return result


from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .git_runner import GitCommandRunner
from .models import CommitRecord


class CommitService:
    """Paged, structured history queries and ASCII graph lane assignment."""

    def __init__(self, runner: GitCommandRunner) -> None:
        self.runner = runner

    def history(self, root: Path, *, limit: int = 80, skip: int = 0, query: str | None = None, author: str | None = None, branch: str | None = None, path: str | None = None) -> tuple[CommitRecord, ...]:
        args = ["log", "--topo-order", "--date=iso-strict", f"--max-count={limit}", f"--skip={skip}", "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%D%x1e"]
        if query:
            args.append(f"--grep={query}")
        if author:
            args.append(f"--author={author}")
        if branch:
            args.append(branch)
        if path:
            args.extend(["--", path])
        result = self.runner.run(args, cwd=root, timeout=30)
        if not result.succeeded:
            return ()
        records = tuple(self._parse(result.stdout))
        return self._with_lanes(records)

    def details(self, root: Path, commit_hash: str) -> CommitRecord | None:
        records = self.history(root, limit=1, branch=commit_hash)
        if not records:
            return None
        record = records[0]
        stats = self.runner.run(["show", "--format=", "--numstat", "--no-renames", commit_hash], cwd=root)
        files = additions = deletions = 0
        for row in stats.stdout.splitlines():
            parts = row.split("\t")
            if len(parts) < 3:
                continue
            files += 1
            additions += int(parts[0]) if parts[0].isdigit() else 0
            deletions += int(parts[1]) if parts[1].isdigit() else 0
        return replace(record, files_changed=files, additions=additions, deletions=deletions)

    @staticmethod
    def _parse(output: str):
        for raw in output.split("\x1e"):
            fields = raw.strip("\r\n").split("\x1f")
            if len(fields) < 7 or not fields[0]:
                continue
            decorations = tuple(item.strip() for item in fields[6].split(",") if item.strip())
            yield CommitRecord(fields[0], tuple(parent for parent in fields[1].split() if parent), fields[2], fields[3], fields[4], fields[5], decorations)

    @staticmethod
    def _with_lanes(records: tuple[CommitRecord, ...]) -> tuple[CommitRecord, ...]:
        lanes: list[str] = []
        rendered: list[CommitRecord] = []
        for record in records:
            if record.hash in lanes:
                lane = lanes.index(record.hash)
            else:
                lane = len(lanes)
                lanes.append(record.hash)
            graph = "".join("* " if index == lane else "| " for index in range(max(1, len(lanes)))).rstrip()
            lanes.pop(lane)
            for parent in reversed(record.parents):
                if parent not in lanes:
                    lanes.insert(lane, parent)
            rendered.append(replace(record, lane=lane, graph=graph))
        return tuple(rendered)

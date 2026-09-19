from __future__ import annotations

import re
from pathlib import Path

from .git_runner import GitCommandRunner
from .models import DiffFile, DiffHunk, DiffLine, GitCommandResult


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")


class DiffService:
    """Produces structured diffs and applies individual parsed hunks safely."""

    def __init__(self, runner: GitCommandRunner) -> None:
        self.runner = runner

    def working_tree(self, root: Path, path: str | None = None) -> tuple[DiffFile, ...]:
        return self._run(root, ["diff", "--no-ext-diff", "--binary", "--unified=3"], path)

    def staged(self, root: Path, path: str | None = None) -> tuple[DiffFile, ...]:
        return self._run(root, ["diff", "--cached", "--no-ext-diff", "--binary", "--unified=3"], path)

    def against_head(self, root: Path, path: str | None = None) -> tuple[DiffFile, ...]:
        return self._run(root, ["diff", "HEAD", "--no-ext-diff", "--binary", "--unified=3"], path)

    def compare(self, root: Path, left: str, right: str, path: str | None = None) -> tuple[DiffFile, ...]:
        return self._run(root, ["diff", left, right, "--no-ext-diff", "--binary", "--unified=3"], path)

    def stage_hunk(self, root: Path, diff_file: DiffFile, hunk: DiffHunk) -> GitCommandResult:
        return self._apply(root, diff_file, hunk, cached=True, reverse=False)

    def unstage_hunk(self, root: Path, diff_file: DiffFile, hunk: DiffHunk) -> GitCommandResult:
        return self._apply(root, diff_file, hunk, cached=True, reverse=True)

    def discard_hunk(self, root: Path, diff_file: DiffFile, hunk: DiffHunk) -> GitCommandResult:
        return self._apply(root, diff_file, hunk, cached=False, reverse=True)

    def _run(self, root: Path, command: list[str], path: str | None) -> tuple[DiffFile, ...]:
        args = [*command, "--"]
        if path:
            args.append(path)
        result = self.runner.run(args, cwd=root, timeout=30)
        return self.parse(result.stdout) if result.succeeded else ()

    def _apply(self, root: Path, diff_file: DiffFile, hunk: DiffHunk, *, cached: bool, reverse: bool) -> GitCommandResult:
        args = ["apply"]
        if cached:
            args.append("--cached")
        if reverse:
            args.append("--reverse")
        args.append("-")
        # The index header records the hash of the complete post-change file.
        # It is invalid when applying only one hunk, so retain only path and
        # mode metadata for partial patch application.
        header = tuple(line for line in diff_file.header if not line.startswith("index "))
        patch = "\n".join((*header, hunk.patch, ""))
        return self.runner.run(args, cwd=root, timeout=30, input_text=patch)

    @staticmethod
    def parse(raw: str) -> tuple[DiffFile, ...]:
        blocks = [block for block in raw.split("diff --git ") if block]
        parsed: list[DiffFile] = []
        for block in blocks:
            lines = block.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            if not lines:
                continue
            git_header = "diff --git " + lines[0].rstrip("\r")
            old_path, new_path = _paths_from_git_header(git_header)
            header: list[str] = [git_header]
            hunk_chunks: list[list[str]] = []
            current: list[str] | None = None
            binary = False
            for line in lines[1:]:
                if line.startswith("@@ "):
                    current = [line]
                    hunk_chunks.append(current)
                elif current is not None:
                    current.append(line)
                else:
                    meta = line.rstrip("\r")
                    header.append(meta)
                    binary = binary or meta.startswith("Binary files ") or meta.startswith("GIT binary patch")
                    if meta.startswith("--- "):
                        old_path = _strip_prefix(meta[4:])
                    elif meta.startswith("+++ "):
                        new_path = _strip_prefix(meta[4:])
            hunks = tuple(_parse_hunk(chunk) for chunk in hunk_chunks)
            status = "binary" if binary else _status_from_paths(old_path, new_path)
            parsed.append(DiffFile(old_path, new_path, status, hunks, tuple(header), binary))
        return tuple(parsed)


def _parse_hunk(chunk: list[str]) -> DiffHunk:
    match = _HUNK.match(chunk[0].rstrip("\r"))
    if not match:
        raise ValueError(f"Invalid diff hunk: {chunk[0]}")
    old_start, old_count, new_start, new_count, heading = match.groups()
    old_line, new_line = int(old_start), int(new_start)
    lines: list[DiffLine] = []
    for raw_line in chunk[1:]:
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            lines.append(DiffLine("addition", raw_line[1:], None, new_line))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            lines.append(DiffLine("deletion", raw_line[1:], old_line, None))
            old_line += 1
        elif raw_line.startswith(" "):
            lines.append(DiffLine("context", raw_line[1:], old_line, new_line))
            old_line += 1
            new_line += 1
        else:
            lines.append(DiffLine("meta", raw_line))
    return DiffHunk(int(old_start), int(old_count or 1), int(new_start), int(new_count or 1), heading, tuple(lines), "\n".join(chunk))


def _paths_from_git_header(header: str) -> tuple[str | None, str | None]:
    parts = header.split(" ", 3)
    if len(parts) < 4:
        return None, None
    paths = parts[3].split(" ", 1)
    return _strip_prefix(paths[0]), _strip_prefix(paths[1]) if len(paths) > 1 else None


def _strip_prefix(path: str) -> str | None:
    if path == "/dev/null":
        return None
    return path[2:] if path.startswith(("a/", "b/")) else path


def _status_from_paths(old_path: str | None, new_path: str | None) -> str:
    if old_path is None:
        return "added"
    if new_path is None:
        return "deleted"
    return "modified"

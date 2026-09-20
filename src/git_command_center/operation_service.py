from __future__ import annotations

from pathlib import Path

from .git_runner import GitCommandRunner
from .models import ConflictBlock, ConflictFile, GitCommandResult, OperationState


class OperationService:
    """History-changing operations plus conflict parsing/resolution."""
    def __init__(self, runner: GitCommandRunner) -> None: self.runner = runner
    def merge(self, root: Path, branch: str, *, no_ff: bool = False, squash: bool = False) -> GitCommandResult: return self.runner.run(["merge", *( ["--no-ff"] if no_ff else []), *( ["--squash"] if squash else []), branch], cwd=root, timeout=60)
    def cherry_pick(self, root: Path, commits: list[str]) -> GitCommandResult: return self.runner.run(["cherry-pick", *commits], cwd=root, timeout=60)
    def revert(self, root: Path, commits: list[str]) -> GitCommandResult: return self.runner.run(["revert", "--no-edit", *commits], cwd=root, timeout=60)
    def continue_operation(self, root: Path, kind: str) -> GitCommandResult: return self.runner.run([kind, "--continue"], cwd=root, timeout=60)
    def abort_operation(self, root: Path, kind: str) -> GitCommandResult: return self.runner.run([kind, "--abort"], cwd=root, timeout=60)
    def skip_operation(self, root: Path, kind: str) -> GitCommandResult: return self.runner.run([kind, "--skip"], cwd=root, timeout=60)
    def state(self, root: Path) -> OperationState:
        git_dir = self.runner.run(["rev-parse", "--git-dir"], cwd=root).stdout.strip()
        base = (root / git_dir).resolve()
        for kind, markers in {"merge": ("MERGE_HEAD",), "cherry-pick": ("CHERRY_PICK_HEAD",), "revert": ("REVERT_HEAD",), "rebase": ("rebase-merge", "rebase-apply"), "bisect": ("BISECT_LOG",)}.items():
            if any((base / marker).exists() for marker in markers): return OperationState(kind, True)
        return OperationState()
    def conflicted_files(self, root: Path) -> tuple[str, ...]:
        result = self.runner.run(["diff", "--name-only", "--diff-filter=U"], cwd=root)
        return tuple(path for path in result.stdout.splitlines() if path)
    def conflict_file(self, root: Path, path: str) -> ConflictFile:
        return ConflictFile(path, tuple(parse_conflicts((root / path).read_text(encoding="utf-8", errors="replace").splitlines())))
    def resolve(self, root: Path, path: str, block: ConflictBlock, choice: str) -> GitCommandResult:
        file = root / path; lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        replacement = {"ours": block.ours, "theirs": block.theirs, "both": (*block.ours, *block.theirs), "base": block.base}[choice]
        start = block.start_line - 1; end = start
        while end < len(lines) and not lines[end].startswith(">>>>>>>"): end += 1
        lines[start:end + 1] = replacement
        file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self.runner.run(["add", "--", path], cwd=root)


def parse_conflicts(lines: list[str]):
    index = 0
    while index < len(lines):
        if not lines[index].startswith("<<<<<<<"):
            index += 1; continue
        start, ours, base, theirs = index + 1, [], [], []
        index += 1; target = ours
        while index < len(lines) and not lines[index].startswith(">>>>>>>"):
            if lines[index].startswith("|||||||"): target = base
            elif lines[index] == "=======": target = theirs
            else: target.append(lines[index])
            index += 1
        if index < len(lines): index += 1
        yield ConflictBlock(start, tuple(ours), tuple(base), tuple(theirs))

from __future__ import annotations

from pathlib import Path

from .git_runner import GitCommandRunner
from .models import Remote, RepositoryState, WorkingTreeSummary


class RepositoryService:
    def __init__(self, runner: GitCommandRunner | None = None) -> None:
        self.runner = runner or GitCommandRunner()

    def inspect(self, directory: str | Path) -> RepositoryState:
        requested = Path(directory).expanduser().resolve()
        if not requested.exists() or not requested.is_dir():
            return RepositoryState(requested, error="Path does not exist or is not a directory.")
        root_result = self.runner.run(["rev-parse", "--show-toplevel"], cwd=requested)
        bare_result = self.runner.run(["rev-parse", "--is-bare-repository"], cwd=requested)
        bare = bare_result.succeeded and bare_result.stdout.strip() == "true"
        if not root_result.succeeded and not bare:
            detail = root_result.stderr.strip() or "Not a Git repository."
            return RepositoryState(requested, bare=False, error=detail)
        root = requested if bare else Path(root_result.stdout.strip()).resolve()
        version = self.runner.run(["--version"], cwd=root).stdout.strip().replace("git version ", "")
        branch_result = self.runner.run(["symbolic-ref", "--short", "-q", "HEAD"], cwd=root)
        detached = not branch_result.succeeded
        head_result = self.runner.run(["log", "-1", "--format=%H%x1f%s"], cwd=root)
        head, subject = self._parse_head(head_result.stdout)
        remotes = self._read_remotes(root)
        status = WorkingTreeSummary() if bare else self._read_status(root)
        return RepositoryState(
            requested_path=requested, root=root, git_version=version or None,
            branch=branch_result.stdout.strip() or None, head=head, head_subject=subject,
            detached_head=detached, bare=bare, remotes=remotes, status=status,
        )

    def _read_remotes(self, root: Path) -> tuple[Remote, ...]:
        names = self.runner.run(["remote"], cwd=root).stdout.splitlines()
        remotes: list[Remote] = []
        for name in names:
            fetch = self.runner.run(["remote", "get-url", name], cwd=root)
            push = self.runner.run(["remote", "get-url", "--push", name], cwd=root)
            remotes.append(Remote(name, fetch.stdout.strip() or None, push.stdout.strip() or None))
        return tuple(remotes)

    def _read_status(self, root: Path) -> WorkingTreeSummary:
        output = self.runner.run(["status", "--porcelain=v1", "--ignored"], cwd=root).stdout
        staged = modified = untracked = conflicted = ignored = 0
        for line in output.splitlines():
            if len(line) < 2:
                continue
            index, worktree = line[0], line[1]
            if line.startswith("??"):
                untracked += 1
            elif line.startswith("!!"):
                ignored += 1
            elif "U" in (index, worktree) or (index, worktree) in {("A", "A"), ("D", "D")}:
                conflicted += 1
            else:
                staged += int(index != " ")
                modified += int(worktree != " ")
        return WorkingTreeSummary(staged, modified, untracked, conflicted, ignored)

    @staticmethod
    def _parse_head(output: str) -> tuple[str | None, str | None]:
        if "\x1f" not in output:
            return None, None
        head, subject = output.strip().split("\x1f", 1)
        return head or None, subject or None


from __future__ import annotations

from pathlib import Path

from .git_runner import GitCommandRunner
from .models import FileChange, Remote, RepositoryState, WorkingTreeSummary


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
        files = () if bare else self._read_files(root)
        status = self._summarize(files)
        upstream, ahead, behind = self._upstream(root)
        return RepositoryState(
            requested_path=requested, root=root, git_version=version or None,
            branch=branch_result.stdout.strip() or None, head=head, head_subject=subject,
            detached_head=detached, bare=bare, remotes=remotes, status=status, files=files,
            upstream=upstream, ahead=ahead, behind=behind,
            stash_count=self._count(root, ["stash", "list"]), tag_count=self._count(root, ["tag", "list"]),
            branch_count=self._count(root, ["branch", "--all", "--no-color"]),
            commit_count=self._count(root, ["rev-list", "--all", "--count"]),
            repository_size=self._repository_size(root),
            user_name=self._config(root, "user.name"), user_email=self._config(root, "user.email"),
        )

    def _read_remotes(self, root: Path) -> tuple[Remote, ...]:
        names = self.runner.run(["remote"], cwd=root).stdout.splitlines()
        remotes: list[Remote] = []
        for name in names:
            fetch = self.runner.run(["remote", "get-url", name], cwd=root)
            push = self.runner.run(["remote", "get-url", "--push", name], cwd=root)
            remotes.append(Remote(name, fetch.stdout.strip() or None, push.stdout.strip() or None))
        return tuple(remotes)

    def _read_files(self, root: Path) -> tuple[FileChange, ...]:
        output = self.runner.run(["status", "--porcelain=v1", "-z", "--ignored"], cwd=root).stdout
        return self._parse_status(output)

    @staticmethod
    def _parse_status(output: str) -> tuple[FileChange, ...]:
        records = output.split("\0")
        changes: list[FileChange] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record or len(record) < 3:
                continue
            xy, path = record[:2], record[3:]
            original = None
            if "R" in xy or "C" in xy:
                if index < len(records):
                    original, index = records[index], index + 1
            if xy == "??":
                kind = "untracked"
            elif xy == "!!":
                kind = "ignored"
            elif "U" in xy or xy in {"AA", "DD"}:
                kind = "conflicted"
            elif "R" in xy:
                kind = "renamed"
            elif "C" in xy:
                kind = "copied"
            elif "A" in xy:
                kind = "added"
            elif "D" in xy:
                kind = "deleted"
            else:
                kind = "modified"
            changes.append(FileChange(path, xy[0], xy[1], kind, original))
        return tuple(changes)

    @staticmethod
    def _summarize(files: tuple[FileChange, ...]) -> WorkingTreeSummary:
        return WorkingTreeSummary(
            staged=sum(file.staged for file in files),
            modified=sum(file.unstaged and file.kind not in {"untracked", "ignored", "conflicted"} for file in files),
            untracked=sum(file.kind == "untracked" for file in files),
            conflicted=sum(file.kind == "conflicted" for file in files),
            ignored=sum(file.kind == "ignored" for file in files),
        )

    def _upstream(self, root: Path) -> tuple[str | None, int, int]:
        upstream = self.runner.run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=root)
        if not upstream.succeeded:
            return None, 0, 0
        counts = self.runner.run(["rev-list", "--left-right", "--count", "HEAD...@{upstream}"], cwd=root).stdout.split()
        return upstream.stdout.strip(), int(counts[0]) if counts else 0, int(counts[1]) if len(counts) > 1 else 0

    def _config(self, root: Path, key: str) -> str | None:
        value = self.runner.run(["config", "--get", key], cwd=root)
        return value.stdout.strip() or None

    def _count(self, root: Path, command: list[str]) -> int:
        result = self.runner.run(command, cwd=root)
        if not result.succeeded:
            return 0
        text = result.stdout.strip()
        return int(text) if text.isdigit() else len([line for line in text.splitlines() if line])

    def _repository_size(self, root: Path) -> int:
        result = self.runner.run(["count-objects", "-vH"], cwd=root)
        for line in result.stdout.splitlines():
            if line.startswith("size-pack: "):
                return self._parse_size(line.removeprefix("size-pack: "))
        return 0

    @staticmethod
    def _parse_size(value: str) -> int:
        unit = value.strip().lower().replace(" ", "")
        if unit.endswith("bytes"):
            unit = unit.removesuffix("bytes")
        elif unit.endswith("byte"):
            unit = unit.removesuffix("byte")
        factors = {"kib": 1024, "mib": 1024**2, "gib": 1024**3, "kb": 1000, "mb": 1000**2, "gb": 1000**3}
        for suffix, factor in factors.items():
            if unit.endswith(suffix):
                return int(float(unit.removesuffix(suffix)) * factor)
        return int(float(unit)) if unit else 0

    @staticmethod
    def _parse_head(output: str) -> tuple[str | None, str | None]:
        if "\x1f" not in output:
            return None, None
        head, subject = output.strip().split("\x1f", 1)
        return head or None, subject or None

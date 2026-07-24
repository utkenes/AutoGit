"""Tüm Git etkileşimlerini güvenli komut listeleriyle sunar."""

from __future__ import annotations

from pathlib import Path

from autogit.domain.exceptions import GitCommandError, RepositoryNotFoundError
from autogit.domain.models import ChangedFile, FileStatus, GitStatus
from autogit.infrastructure.command_runner import CommandRunner
from autogit.utils.paths import is_within_root


class GitService:
    def __init__(self, working_directory: Path, runner: CommandRunner) -> None:
        self.working_directory = working_directory.resolve()
        self.runner = runner

    def _run(self, *arguments: str, check: bool = True) -> str:
        result = self.runner.run(["git", *arguments], self.working_directory)
        if check and result.exit_code != 0:
            detail = result.output or "Bilinmeyen Git hatası"
            raise GitCommandError(f"Git komutu başarısız ({' '.join(arguments)}): {detail}")
        # Porcelain çıktısındaki ilk boşluk, index durumunun bir parçasıdır.
        return result.stdout.rstrip()

    def is_repository(self) -> bool:
        return self._run("rev-parse", "--is-inside-work-tree", check=False) == "true"

    def get_repository_root(self) -> Path:
        if not self.is_repository():
            raise RepositoryNotFoundError(f"{self.working_directory} bir Git repository değil.")
        return Path(self._run("rev-parse", "--show-toplevel")).resolve()

    def get_current_branch(self) -> str | None:
        branch = self._run("branch", "--show-current", check=False)
        return branch or None

    def get_remote_url(self) -> str | None:
        remote = self._run("remote", "get-url", "origin", check=False)
        return remote or None

    def get_upstream_branch(self) -> str | None:
        upstream = self._run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
        return upstream or None

    def get_status(self) -> GitStatus:
        lines = self._run("status", "--porcelain=v1", "-uall").splitlines()
        changed: list[ChangedFile] = []
        for line in lines:
            if len(line) < 4:
                continue
            index_status, worktree_status, raw_path = line[0], line[1], line[3:]
            path = Path(raw_path.split(" -> ")[-1])
            status = self._to_status(index_status, worktree_status)
            changed.append(ChangedFile(path, status, index_status != " "))
        return GitStatus(changed)

    @staticmethod
    def _to_status(index_status: str, worktree_status: str) -> FileStatus:
        code = index_status if index_status != " " else worktree_status
        mapping = {
            "A": FileStatus.ADDED,
            "M": FileStatus.MODIFIED,
            "D": FileStatus.DELETED,
            "R": FileStatus.RENAMED,
            "?": FileStatus.UNTRACKED,
        }
        return mapping.get(code, FileStatus.MODIFIED)

    def get_changed_files(self) -> list[ChangedFile]:
        return self.get_status().changed_files

    def get_untracked_files(self) -> list[ChangedFile]:
        return [file for file in self.get_changed_files() if file.status is FileStatus.UNTRACKED]

    def get_staged_files(self) -> list[ChangedFile]:
        return [file for file in self.get_changed_files() if file.staged]

    def get_diff(self) -> str:
        return self._run("diff", "--no-ext-diff")

    def get_staged_diff(self) -> str:
        return self._run("diff", "--cached", "--no-ext-diff")

    def get_diff_stat(self) -> str:
        return self._run("diff", "--stat") or self._run("diff", "--cached", "--stat")

    def stage_files(self, files: list[Path]) -> None:
        root = self.get_repository_root()
        safe: list[str] = []
        for relative_path in files:
            candidate = (root / relative_path)
            if not is_within_root(candidate, root):
                raise GitCommandError(f"Repository dışındaki dosya stage edilemez: {relative_path}")
            safe.append(str(relative_path))
        if safe:
            self._run("add", "--", *safe)

    def unstage_files(self, files: list[Path]) -> None:
        if files:
            self._run("restore", "--staged", "--", *(str(path) for path in files))

    def commit(self, message: str) -> str:
        self._run("commit", "-m", message)
        return self._run("rev-parse", "HEAD")

    def push(self) -> None:
        self._run("push")

    def get_last_commit(self) -> str | None:
        result = self._run("log", "-1", "--pretty=format:%h %s", check=False)
        return result or None

    def get_git_user_name(self) -> str | None:
        value = self._run("config", "--get", "user.name", check=False)
        return value or None

    def get_git_user_email(self) -> str | None:
        value = self._run("config", "--get", "user.email", check=False)
        return value or None

    def is_file_tracked(self, path: Path) -> bool:
        result = self.runner.run(["git", "ls-files", "--error-unmatch", "--", str(path)], self.working_directory)
        return result.exit_code == 0

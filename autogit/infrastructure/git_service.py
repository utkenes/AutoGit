"""Safe, shell-free Git operations used by the application services."""

from __future__ import annotations

from pathlib import Path

from autogit.domain.exceptions import GitCommandError, RepositoryNotFoundError
from autogit.domain.models import ChangedFile, FileStatus, GitStatus
from autogit.domain.repository_state import RepositoryState
from autogit.infrastructure.command_runner import CommandRunner
from autogit.infrastructure.git_lock import GitLock, GitLockInspector
from autogit.infrastructure.git_status_parser import GitStatusParser
from autogit.utils.paths import is_within_root


class GitService:
    def __init__(self, working_directory: Path, runner: CommandRunner) -> None:
        self.working_directory = working_directory.resolve()
        self.runner = runner
        self.status_parser = GitStatusParser()
        self.lock_inspector = GitLockInspector()

    def _run(self, *arguments: str, check: bool = True) -> str:
        result = self.runner.run(["git", *arguments], self.working_directory)
        if check and result.exit_code != 0:
            detail = result.output or "Bilinmeyen Git hatası"
            raise GitCommandError(f"Git komutu başarısız ({' '.join(arguments)}): {detail}")
        return result.stdout.rstrip()

    def _run_bytes(self, *arguments: str, check: bool = True) -> bytes:
        result = self.runner.run_bytes(["git", *arguments], self.working_directory)
        if check and result.exit_code != 0:
            detail = result.output or "Bilinmeyen Git hatası"
            raise GitCommandError(f"Git komutu başarısız ({' '.join(arguments)}): {detail}")
        return result.stdout.encode("utf-8", errors="surrogateescape")

    def is_repository(self) -> bool:
        return self._run("rev-parse", "--is-inside-work-tree", check=False) == "true"

    def initialize_repository(self) -> None:
        self._run("init")

    def set_main_branch(self) -> None:
        self._run("branch", "-M", "main")

    def add_remote(self, url: str) -> None:
        self.require_no_operation_locks()
        if self.get_remote_url():
            return
        self._run("remote", "add", "origin", url)

    def get_repository_root(self) -> Path:
        if not self.is_repository():
            raise RepositoryNotFoundError(f"{self.working_directory} bir Git repository değil.")
        return Path(self._run("rev-parse", "--show-toplevel")).resolve()

    def _get_git_dir(self) -> Path | None:
        value = self._run("rev-parse", "--git-dir", check=False)
        if not value:
            return None
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.working_directory / path).resolve()

    def has_index_lock(self) -> bool:
        return any(lock.kind == "index" for lock in self.get_operation_locks())

    def get_operation_locks(self) -> list[GitLock]:
        return self.lock_inspector.find(self._get_git_dir())

    def require_no_operation_locks(self) -> None:
        self.lock_inspector.require_unlocked(self._get_git_dir())

    def get_current_branch(self) -> str | None:
        branch = self._run("symbolic-ref", "--short", "-q", "HEAD", check=False)
        return branch or None

    def is_merge_in_progress(self) -> bool:
        git_dir = self._get_git_dir()
        return git_dir is not None and (git_dir / "MERGE_HEAD").exists()

    def is_rebase_in_progress(self) -> bool:
        git_dir = self._get_git_dir()
        return git_dir is not None and ((git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists())

    def is_cherry_pick_in_progress(self) -> bool:
        git_dir = self._get_git_dir()
        return git_dir is not None and (git_dir / "CHERRY_PICK_HEAD").exists()

    def is_revert_in_progress(self) -> bool:
        git_dir = self._get_git_dir()
        return git_dir is not None and (git_dir / "REVERT_HEAD").exists()

    def get_repository_state(self) -> RepositoryState:
        is_repository = self.is_repository()
        if not is_repository:
            return RepositoryState(False, False, None, False, False, False, False, False)
        has_head = bool(self._run("rev-parse", "--verify", "HEAD", check=False))
        branch_name = self.get_current_branch()
        return RepositoryState(
            is_repository=True,
            has_head=has_head,
            branch_name=branch_name,
            is_detached_head=has_head and branch_name is None,
            merge_in_progress=self.is_merge_in_progress(),
            rebase_in_progress=self.is_rebase_in_progress(),
            cherry_pick_in_progress=self.is_cherry_pick_in_progress(),
            revert_in_progress=self.is_revert_in_progress(),
        )

    def get_remote_url(self) -> str | None:
        remote = self._run("remote", "get-url", "origin", check=False)
        return remote or None

    def get_upstream_branch(self) -> str | None:
        upstream = self._run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
        return upstream or None

    def get_ahead_behind(self) -> tuple[int, int] | None:
        if not self.get_upstream_branch():
            return None
        value = self._run("rev-list", "--left-right", "--count", "@{upstream}...HEAD", check=False)
        try:
            remote_ahead, local_ahead = (int(item) for item in value.split())
        except ValueError:
            return None
        return remote_ahead, local_ahead

    def get_status(self) -> GitStatus:
        raw_status = self._run_bytes("status", "--porcelain=v1", "-z", "-uall")
        return GitStatus(self.status_parser.parse(raw_status))

    def get_changed_files(self) -> list[ChangedFile]:
        return self.get_status().changed_files

    def get_untracked_files(self) -> list[ChangedFile]:
        return [file for file in self.get_changed_files() if file.status is FileStatus.UNTRACKED]

    def get_staged_files(self) -> list[ChangedFile]:
        raw = self._run_bytes("diff", "--cached", "--name-status", "-z")
        records = raw.split(b"\0")
        files: list[ChangedFile] = []
        index = 0
        while index < len(records):
            status_record = records[index]
            index += 1
            if not status_record:
                continue
            code = chr(status_record[0])
            if index >= len(records):
                break
            first_path = Path(records[index].decode("utf-8", errors="surrogateescape"))
            index += 1
            status = self._status_from_code(code)
            if status in {FileStatus.RENAMED, FileStatus.COPIED} and index < len(records):
                second_path = Path(records[index].decode("utf-8", errors="surrogateescape"))
                index += 1
                files.append(ChangedFile(second_path, status, old_path=first_path, staged=True))
            else:
                files.append(ChangedFile(first_path, status, staged=True))
        return files

    @staticmethod
    def _status_from_code(code: str) -> FileStatus:
        return {
            "A": FileStatus.ADDED,
            "M": FileStatus.MODIFIED,
            "D": FileStatus.DELETED,
            "R": FileStatus.RENAMED,
            "C": FileStatus.COPIED,
        }.get(code, FileStatus.MODIFIED)

    def has_staged_changes(self) -> bool:
        return bool(self.get_staged_files())

    def get_diff(self) -> str:
        return self._run("diff", "--no-ext-diff")

    def get_staged_diff(self) -> str:
        return self._run("diff", "--cached", "--no-ext-diff")

    def get_diff_stat(self) -> str:
        return self._run("diff", "--stat") or self._run("diff", "--cached", "--stat")

    def get_staged_file_content(self, path: Path) -> bytes:
        return self._run_bytes("show", f":{path.as_posix()}")

    def stage_files(self, files: list[Path]) -> list[Path]:
        root = self.get_repository_root()
        safe: list[str] = []
        for relative_path in files:
            candidate = root / relative_path
            if not is_within_root(candidate, root):
                raise GitCommandError(f"Repository dışındaki dosya stage edilemez: {relative_path}")
            safe.append(str(relative_path))
        if safe:
            self._run("add", "--", *safe)
        return list(files)

    def unstage_files(self, files: list[Path]) -> None:
        if files:
            if self.get_repository_state().has_head:
                self._run("restore", "--staged", "--", *(str(path) for path in files))
            else:
                self._run("rm", "--cached", "--ignore-unmatch", "--", *(str(path) for path in files))

    def commit(self, message: str) -> str:
        self._run("commit", "-m", message)
        return self._run("rev-parse", "HEAD")

    def get_head(self) -> str | None:
        value = self._run("rev-parse", "--verify", "HEAD", check=False)
        return value or None

    def reset_mixed(self, target: str) -> None:
        self._run("reset", "--mixed", target)

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

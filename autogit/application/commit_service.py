"""The safe, transactional AutoGit commit workflow."""

from __future__ import annotations

import logging
from pathlib import Path

from autogit.application.quality_service import QualityService
from autogit.config import AutoGitConfig
from autogit.domain.exceptions import (
    CommitMessageError,
    NothingToCommitError,
    PreStagedChangesError,
    PushFailedError,
    RepositoryUnsafeError,
    SecurityViolationError,
)
from autogit.domain.models import (
    ChangedFile,
    CommitContext,
    CommitGroup,
    CommitPlan,
    CommitResult,
    FileStatus,
    PushResult,
)
from autogit.domain.protocols import CommitMessageProvider, SecretScannerProtocol
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.operation_lock import AutoGitOperationLock


class CommitService:
    def __init__(
        self,
        root: Path,
        config: AutoGitConfig,
        git: GitService,
        scanner: SecretScannerProtocol,
        quality: QualityService,
        provider: CommitMessageProvider,
        logger: logging.Logger,
    ) -> None:
        self.root = root
        self.config = config
        self.git = git
        self.scanner = scanner
        self.quality = quality
        self.provider = provider
        self.logger = logger

    def preview(self) -> CommitPlan:
        """Return the commit plan without staging, checking, or writing anything."""
        return self._prepare()

    def prepare(self, *, allow_initial_commit: bool = False) -> CommitPlan:
        """Build a safe plan for the interactive workflow."""
        return self._prepare(allow_initial_commit=allow_initial_commit)

    def execute_groups(
        self, groups: list[CommitGroup], *, allow_initial_commit: bool = False, lock_held: bool = False
    ) -> list[CommitResult]:
        """Run approved groups sequentially, without pushing."""
        if lock_held:
            return self._execute_groups(groups, allow_initial_commit=allow_initial_commit)
        with AutoGitOperationLock(self.root):
            return self._execute_groups(groups, allow_initial_commit=allow_initial_commit)

    def _execute_groups(
        self, groups: list[CommitGroup], *, allow_initial_commit: bool
    ) -> list[CommitResult]:
        plan = self._prepare(allow_initial_commit=allow_initial_commit)
        allowed_paths = {file.path for file in plan.candidates}
        planned_paths = [file.path for group in groups for file in group.files]
        if not groups or set(planned_paths) != allowed_paths or len(planned_paths) != len(allowed_paths):
            raise SecurityViolationError("Commit planı güvenli aday dosyalarla eşleşmiyor.")
        quality_results = self.quality.run()
        for quality_result in quality_results:
            self.logger.info("%s exit=%s", quality_result.check.name, quality_result.exit_code)

        results: list[CommitResult] = []
        for group in groups:
            message_error = self.provider.validation_error(group.suggested_message)
            if message_error:
                raise CommitMessageError(message_error)
            before_head = self.git.get_head()
            staged_by_autogit = self.git.stage_files([file.path for file in group.files])
            try:
                self._verify_staged_group(group, staged_by_autogit)
                self._scan_staged_files(list(group.files))
                commit_hash = self.git.commit(group.suggested_message)
                if self.git.get_head() != commit_hash or commit_hash == before_head:
                    raise RepositoryUnsafeError("Commit sonrası HEAD beklenen şekilde ilerlemedi.")
            except Exception:
                self.git.unstage_files(staged_by_autogit)
                raise
            results.append(CommitResult(group.suggested_message, commit_hash, [file.path for file in group.files]))
        return results

    def execute(self) -> tuple[CommitResult, PushResult]:
        with AutoGitOperationLock(self.root):
            return self._execute()

    def _execute(self) -> tuple[CommitResult, PushResult]:
        plan = self._prepare()
        staged_by_autogit = self.git.stage_files([file.path for file in plan.candidates])
        committed = False
        try:
            self._scan_staged_files(plan.candidates)
            quality_results = self.quality.run()
            for quality_result in quality_results:
                self.logger.info(
                    "%s exit=%s duration=%.2fs",
                    quality_result.check.name,
                    quality_result.exit_code,
                    quality_result.duration_seconds,
                )
            staged = self.git.get_staged_files()
            if not staged:
                raise NothingToCommitError("Güvenli dosyalar stage edilemedi.")
            context = CommitContext(staged, self.git.get_diff_stat(), self.git.get_staged_diff()[:4000])
            message = self.provider.generate(context)
            commit_hash = self.git.commit(message)
            committed = True
        except Exception:
            if not committed:
                self.git.unstage_files(staged_by_autogit)
            raise

        result = CommitResult(message, commit_hash, [file.path for file in staged])
        self.logger.info("Commit created hash=%s message=%s", commit_hash, message)
        return result, self._push_if_enabled()

    def _prepare(self, *, allow_initial_commit: bool = False) -> CommitPlan:
        self.git.require_no_operation_locks()
        self._ensure_repository_is_safe(allow_initial_commit=allow_initial_commit)
        pre_staged = self.git.get_staged_files()
        if pre_staged:
            raise PreStagedChangesError([str(file.path) for file in pre_staged])

        files = self.git.get_changed_files()
        if not files:
            raise NothingToCommitError("Commit oluşturulacak değişiklik bulunamadı.")
        candidates = [file for file in files if self._may_stage(file.path)]
        excluded = [file for file in files if file not in candidates]
        if not candidates:
            if all(file.path.parts and file.path.parts[0] in {".git", ".autogit"} for file in files):
                raise NothingToCommitError("Commit oluşturulacak değişiklik bulunamadı.")
            raise SecurityViolationError("Güvenli biçimde stage edilebilecek dosya bulunamadı.")
        return CommitPlan(candidates, excluded)

    def _ensure_repository_is_safe(self, *, allow_initial_commit: bool = False) -> None:
        state = self.git.get_repository_state()
        if not state.is_repository:
            raise RepositoryUnsafeError("AutoGit bir Git repository içinde çalışmalıdır.")
        if not state.has_head and not allow_initial_commit:
            raise RepositoryUnsafeError("AutoGit ilk commit oluşmadan önce çalışmaz.")
        if state.is_detached_head:
            raise RepositoryUnsafeError(
                "AutoGit detached HEAD durumunda commit oluşturmaz. Bir branch'e geçip tekrar deneyin."
            )
        if state.merge_in_progress:
            raise RepositoryUnsafeError("Repository içinde devam eden bir merge işlemi var.")
        if state.rebase_in_progress:
            raise RepositoryUnsafeError("Repository içinde devam eden bir rebase işlemi var.")
        if state.cherry_pick_in_progress:
            raise RepositoryUnsafeError("Repository içinde devam eden bir cherry-pick işlemi var.")
        if state.revert_in_progress:
            raise RepositoryUnsafeError("Repository içinde devam eden bir revert işlemi var.")

    def _scan_staged_files(self, files: list[ChangedFile]) -> None:
        if not self.config.security.scan_secrets:
            return
        findings = []
        max_size_bytes = self.config.security.max_file_size_kb * 1024
        for file in files:
            if file.status is FileStatus.DELETED:
                self.logger.info("SKIP %s — silinmiş dosya", file.path)
                continue
            content = self.git.get_staged_file_content(file.path)
            if len(content) > max_size_bytes:
                self.logger.info("SKIP %s — yapılandırılmış boyut sınırını aşıyor", file.path)
                continue
            if self.scanner.is_binary_content(content):
                self.logger.info("SKIP %s — binary içerik", file.path)
                continue
            findings.extend(self.scanner.scan_content(path=file.path, content=content))
        if findings:
            detail = "; ".join(
                f"{item.path}:{item.line_number} {item.secret_type} ({item.masked_value})" for item in findings
            )
            self.logger.warning("Secret scan blocked commit: %s", detail)
            raise SecurityViolationError(f"Gizli bilgi bulundu: {detail}. Dosyayı düzeltin veya .gitignore içine alın.")

    def _verify_staged_group(self, group: CommitGroup, staged_by_autogit: list[Path]) -> None:
        """Ensure Git staged precisely the paths that this workflow owns."""
        expected = {file.path for file in group.files}
        staged = {file.path for file in self.git.get_staged_files()}
        if set(staged_by_autogit) != expected or staged != expected:
            raise RepositoryUnsafeError(
                "Stage alanı planlanan commit grubuyla eşleşmiyor; işlem durduruldu. "
                "Partial staging v0.1'de desteklenmez."
            )

    def _may_stage(self, path: Path) -> bool:
        if path.parts and path.parts[0] in {".git", ".autogit"}:
            return False
        name = path.name.lower()
        blocked = {
            ".env", ".env.local", ".env.development", ".env.production", ".env.test",
            "credentials.json", "service-account.json", "id_rsa", "id_ed25519",
        }
        if name in blocked or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            return False
        return not (self.config.security.block_env_files and name.startswith(".env") and name != ".env.example")

    def _push_if_enabled(self) -> PushResult:
        if not self.config.auto_push:
            return PushResult(False, "Otomatik push kapalı.")
        if not self.git.get_remote_url():
            return PushResult(False, "Remote tanımlı değil; push atlandı.")
        try:
            self.git.push()
        except Exception as error:
            raise PushFailedError(f"Push başarısız: {error}") from error
        return PushResult(True, "Push tamamlandı.")

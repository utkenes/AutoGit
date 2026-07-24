"""Güvenlik, kalite ve Git commit adımlarını sıralı uygular."""

from __future__ import annotations

import logging
from pathlib import Path

from autogit.application.quality_service import QualityService
from autogit.config import AutoGitConfig
from autogit.domain.exceptions import NothingToCommitError, PushFailedError, SecurityViolationError
from autogit.domain.models import CommitContext, CommitResult, PushResult
from autogit.domain.protocols import CommitMessageProvider
from autogit.infrastructure.git_service import GitService
from autogit.infrastructure.secret_scanner import SecretScanner


class CommitService:
    def __init__(
        self,
        root: Path,
        config: AutoGitConfig,
        git: GitService,
        scanner: SecretScanner,
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

    def execute(self) -> tuple[CommitResult, PushResult]:
        files = self.git.get_changed_files()
        if not files:
            raise NothingToCommitError("Commit oluşturulacak değişiklik bulunamadı.")
        candidates = [file for file in files if self._may_stage(file.path)]
        if not candidates:
            raise SecurityViolationError("Güvenli biçimde stage edilebilecek dosya bulunamadı.")
        if self.config.security.scan_secrets:
            findings = self.scanner.scan_files(
                self.root, [file.path for file in candidates], self.config.security.max_file_size_kb
            )
            if findings:
                detail = "; ".join(
                    f"{item.path}:{item.line_number} {item.secret_type} ({item.masked_value})"
                    for item in findings
                )
                self.logger.warning("Secret taraması engelledi: %s", detail)
                raise SecurityViolationError(
                    f"Gizli bilgi bulundu: {detail}. Dosyayı düzeltin veya .gitignore içine alın."
                )
        quality_results = self.quality.run()
        for quality_result in quality_results:
            self.logger.info(
                "%s exit=%s süre=%.2fs",
                quality_result.check.name,
                quality_result.exit_code,
                quality_result.duration_seconds,
            )
        self.git.stage_files([file.path for file in candidates])
        staged = self.git.get_staged_files()
        if not staged:
            raise NothingToCommitError("Güvenli dosyalar stage edilemedi.")
        context = CommitContext(staged, self.git.get_diff_stat(), self.git.get_staged_diff()[:4000])
        message = self.provider.generate(context)
        commit_hash = self.git.commit(message)
        result = CommitResult(message, commit_hash, [file.path for file in staged])
        self.logger.info("Commit oluşturuldu hash=%s mesaj=%s", commit_hash, message)
        push = self._push_if_enabled()
        return result, push

    def _may_stage(self, path: Path) -> bool:
        name = path.name.lower()
        blocked = {
            ".env", ".env.local", ".env.development", ".env.production", ".env.test",
            "credentials.json", "service-account.json", "id_rsa", "id_ed25519",
        }
        if name in blocked or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            return False
        if self.config.security.block_env_files and name.startswith(".env") and name != ".env.example":
            return False
        return True

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

"""Kullanıcıya anlamlı hata vermeyi sağlayan özel hata sınıfları."""


class AutoGitError(Exception):
    """AutoGit kaynaklı temel hata."""


class GitCommandError(AutoGitError):
    """Bir Git komutu başarısız olduğunda oluşur."""


class RepositoryNotFoundError(AutoGitError):
    """Hedef klasör Git deposu olmadığında oluşur."""


class RepositoryUnsafeError(AutoGitError):
    """Repository is not in a safe state for an automatic commit."""


class PreStagedChangesError(AutoGitError):
    """Changes had already been staged before AutoGit started."""

    def __init__(self, files: list[str]) -> None:
        self.files = files
        super().__init__("AutoGit dışında stage edilmiş dosyalar bulundu.")


class ConfigurationError(AutoGitError):
    """Yapılandırma okunamadığında veya doğrulanamadığında oluşur."""


class NothingToCommitError(AutoGitError):
    """Commit edilecek çalışma alanı değişikliği olmadığında oluşur."""


class SecurityViolationError(AutoGitError):
    """Tarama güvenlik ihlali bulduğunda oluşur."""


class QualityCheckFailedError(AutoGitError):
    """Test, lint veya tip kontrolü başarısız olduğunda oluşur."""


class PushFailedError(AutoGitError):
    """Push işlemi başarısız olduğunda oluşur."""


class CommitMessageError(AutoGitError):
    """Commit mesajı geçerli biçimde üretilemediğinde oluşur."""


class WatcherError(AutoGitError):
    """Dosya izleyici kurulamadığında oluşur."""

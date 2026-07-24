"""Değiştirilebilir altyapı parçaları için bağımlılık sözleşmeleri."""

from typing import Protocol

from autogit.domain.models import CommitContext


class CommitMessageProvider(Protocol):
    """Commit mesajı sağlayıcılarının uyması gereken sözleşme."""

    def generate(self, context: CommitContext) -> str:
        """Conventional Commits uyumlu bir mesaj döndürür."""


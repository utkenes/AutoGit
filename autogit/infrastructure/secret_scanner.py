"""Dosya içeriklerinde sırlara benzeyen değerleri maskeli şekilde bulur."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from autogit.domain.models import SecretFinding
from autogit.utils.masking import mask_secret
from autogit.utils.paths import is_within_root


@dataclass(frozen=True)
class SecretPattern:
    name: str
    expression: re.Pattern[str]


class SecretScanner:
    """Bilinen anahtar biçimlerini tarar; değeri asla sonuçta saklamaz."""

    patterns = (
        SecretPattern("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b")),
        SecretPattern("Gemini/Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b")),
        SecretPattern("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
        SecretPattern("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        SecretPattern("Private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
        SecretPattern("Bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}")),
        SecretPattern(
            "Database password",
            re.compile(r"(?i)(?:database_url|password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
        ),
        SecretPattern(
            "JWT secret",
            re.compile(r"(?i)(?:jwt_secret|jwt-key|jwt_key)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
        ),
        SecretPattern(
            "Generic API key",
            re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._/-]{16,}"),
        ),
    )

    def scan_files(self, root: Path, files: list[Path], max_size_kb: int) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for relative_path in files:
            full_path = root / relative_path
            if not is_within_root(full_path, root) or not full_path.exists() or full_path.is_symlink():
                continue
            if full_path.stat().st_size > max_size_kb * 1024:
                continue
            findings.extend(self.scan_file(root, relative_path))
        return findings

    def scan_file(self, root: Path, relative_path: Path) -> list[SecretFinding]:
        full_path = root / relative_path
        try:
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        findings: list[SecretFinding] = []
        for number, line in enumerate(lines, start=1):
            for pattern in self.patterns:
                match = pattern.expression.search(line)
                if match:
                    findings.append(SecretFinding(relative_path, number, pattern.name, mask_secret(match.group(0))))
        return findings


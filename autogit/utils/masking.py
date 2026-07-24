"""Hassas değerleri kullanıcıya ve loglara güvenli sunmak için araçlar."""

import re


def mask_secret(value: str) -> str:
    clean = value.strip().strip("\"'")
    if len(clean) <= 8:
        return "****"
    return f"{clean[:4]}****{clean[-4:]}"


def redact_text(value: str) -> str:
    """Bilinen anahtar biçimlerini loga yazmadan önce maskeler."""
    patterns = [
        r"sk-(?:proj-)?[A-Za-z0-9_-]{12,}",
        r"AIza[A-Za-z0-9_-]{20,}",
        r"gh[pousr]_[A-Za-z0-9]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"(?i)(bearer\s+)[A-Za-z0-9._-]{12,}",
    ]
    result = value
    for pattern in patterns:
        result = re.sub(pattern, lambda match: mask_secret(match.group(0)), result)
    return result


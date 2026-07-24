from pathlib import Path

from autogit.infrastructure.secret_scanner import SecretScanner


def test_openai_key_is_found_and_masked(tmp_path: Path) -> None:
    path = tmp_path / "settings.py"
    path.write_text("API_KEY = 'sk-proj-abcdefghijklmnop12345678'\n", encoding="utf-8")
    findings = SecretScanner().scan_files(tmp_path, [Path("settings.py")], 512)
    assert findings[0].secret_type == "OpenAI API key"
    assert "abcdefghijkl" not in findings[0].masked_value


def test_private_key_is_found(tmp_path: Path) -> None:
    path = tmp_path / "key.pem"
    path.write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    assert SecretScanner().scan_files(tmp_path, [Path("key.pem")], 512)


def test_github_and_gemini_keys_are_found(tmp_path: Path) -> None:
    path = tmp_path / "secrets.txt"
    path.write_text("ghp_abcdefghijklmnopqrstuvwx\nAIzaabcdefghijklmnopqrstuvwx\n", encoding="utf-8")
    assert len(SecretScanner().scan_files(tmp_path, [Path("secrets.txt")], 512)) == 2


from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

CHECK_INTERVAL_SECONDS = 10
IDLE_TIME_BEFORE_COMMIT_SECONDS = 60
AUTO_PUSH = False


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def is_git_repository() -> bool:
    result = run_git("rev-parse", "--is-inside-work-tree")
    return result.returncode == 0


def get_status() -> str:
    result = run_git("status", "--porcelain")
    return result.stdout.strip()


def get_diff_summary() -> str:
    result = run_git("diff", "--stat")

    if result.stdout.strip():
        return result.stdout.strip()

    staged_result = run_git("diff", "--cached", "--stat")
    return staged_result.stdout.strip()


def create_commit_message() -> str:
    changed_files = get_status().splitlines()
    file_count = len(changed_files)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"chore: auto-save {file_count} changed files at {timestamp}"


def commit_changes() -> bool:
    add_result = run_git("add", ".")

    if add_result.returncode != 0:
        print("Dosyalar eklenemedi:")
        print(add_result.stderr)
        return False

    message = create_commit_message()
    commit_result = run_git("commit", "-m", message)

    if commit_result.returncode != 0:
        print("Commit oluşturulamadı:")
        print(commit_result.stdout)
        print(commit_result.stderr)
        return False

    print(f"\nCommit oluşturuldu: {message}")

    summary = get_diff_summary()
    if summary:
        print(summary)

    if AUTO_PUSH:
        push_result = run_git("push")

        if push_result.returncode != 0:
            print("Push başarısız:")
            print(push_result.stderr)
            return False

        print("GitHub'a push edildi.")

    return True


def main() -> None:
    if not is_git_repository():
        raise RuntimeError(
            f"{PROJECT_DIR} bir Git repository değil. Önce git init çalıştır."
        )

    print(f"Proje izleniyor: {PROJECT_DIR}")
    print(
        f"Son değişiklikten {IDLE_TIME_BEFORE_COMMIT_SECONDS} saniye sonra commit atılacak."
    )

    previous_status = get_status()
    last_change_time: float | None = None

    while True:
        try:
            current_status = get_status()

            if current_status != previous_status:
                previous_status = current_status
                last_change_time = time.time()

                if current_status:
                    print("\nDeğişiklik algılandı.")
                    print(current_status)
                else:
                    print("\nÇalışma alanı temiz.")

            if current_status and last_change_time is not None:
                idle_seconds = time.time() - last_change_time

                if idle_seconds >= IDLE_TIME_BEFORE_COMMIT_SECONDS:
                    commit_changes()

                    previous_status = get_status()
                    last_change_time = None

            time.sleep(CHECK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nOtomatik commit botu durduruldu.")
            break


if __name__ == "__main__":
    main()
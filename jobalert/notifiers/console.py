"""콘솔 출력 (dry-run / 로컬 확인용)."""

from __future__ import annotations


class ConsoleNotifier:
    name = "console"

    def send(self, subject: str, text: str, html: str) -> None:  # noqa: A002 - 인터페이스 고정
        print(f"\n=== {subject} ===\n")
        print(text)

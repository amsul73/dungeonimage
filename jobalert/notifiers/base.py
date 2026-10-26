"""알림 채널 공통 인터페이스."""

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    name: str

    def send(self, subject: str, text: str, html: str) -> None:
        ...

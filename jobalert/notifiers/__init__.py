"""알림 채널 레지스트리."""

from __future__ import annotations

from .base import Notifier
from .console import ConsoleNotifier
from .email import EmailNotifier

__all__ = ["Notifier", "ConsoleNotifier", "EmailNotifier", "build_notifier"]


def build_notifier(name: str) -> Notifier:
    if name == "email":
        return EmailNotifier()
    if name == "console":
        return ConsoleNotifier()
    raise KeyError(f"알 수 없는 알림 채널: {name} (가능: email, console)")

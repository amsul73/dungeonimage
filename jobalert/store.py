"""이미 알린 공고 기록 (중복 알림 방지)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


class SeenStore:
    def __init__(self, path: str | Path, keep_days: int = 120) -> None:
        self.path = Path(path)
        self.keep_days = keep_days
        self.entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, dict):
            self.entries = entries

    def is_seen(self, key: str) -> bool:
        return key in self.entries

    def mark(self, key: str, **meta: Any) -> None:
        self.entries[key] = {"notified_at": now_kst().isoformat(timespec="seconds"), **meta}

    def prune(self) -> int:
        """오래된 기록 정리. 지운 개수를 반환."""
        cutoff = now_kst() - timedelta(days=self.keep_days)
        stale = []
        for key, meta in self.entries.items():
            stamp = str(meta.get("notified_at") or "")
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=KST)
            if when < cutoff:
                stale.append(key)
        for key in stale:
            del self.entries[key]
        return len(stale)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": now_kst().isoformat(timespec="seconds"),
            "entries": self.entries,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

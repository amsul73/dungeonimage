"""profile.yaml / 환경변수 설정 로딩."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .keywords import KeywordDictionary

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = ROOT / "profile.yaml"
DEFAULT_KEYWORDS = ROOT / "keywords.yaml"
DEFAULT_STATE = ROOT / "state" / "seen.json"


@dataclass
class Highlight:
    title: str
    summary: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass
class Profile:
    """이력서/포트폴리오에서 뽑은 내 역량 + 검색 조건."""

    raw: dict[str, Any]
    dictionary: KeywordDictionary

    # 역량 id → 보유 레벨(1~5)
    levels: dict[str, int] = field(default_factory=dict)
    highlights: list[Highlight] = field(default_factory=list)
    unknown_tokens: list[str] = field(default_factory=list)

    @property
    def me(self) -> dict[str, Any]:
        return self.raw.get("me") or {}

    @property
    def search(self) -> dict[str, Any]:
        return self.raw.get("search") or {}

    @property
    def filters(self) -> dict[str, Any]:
        return self.raw.get("filters") or {}

    @property
    def scoring(self) -> dict[str, Any]:
        return self.raw.get("scoring") or {}

    @property
    def notify(self) -> dict[str, Any]:
        return self.raw.get("notify") or {}

    @property
    def threshold(self) -> float:
        env = os.getenv("MATCH_THRESHOLD")
        if env:
            try:
                return float(env)
            except ValueError:
                pass
        return float(self.notify.get("threshold", 65))

    def level_of(self, keyword_id: str) -> int:
        return int(self.levels.get(keyword_id, 0))

    def has(self, keyword_id: str) -> bool:
        return self.level_of(keyword_id) > 0

    @classmethod
    def load(
        cls,
        profile_path: str | Path = DEFAULT_PROFILE,
        keywords_path: str | Path = DEFAULT_KEYWORDS,
    ) -> Profile:
        raw = yaml.safe_load(Path(profile_path).read_text(encoding="utf-8")) or {}
        dictionary = KeywordDictionary.load(keywords_path)

        levels: dict[str, int] = {}
        unknown: list[str] = []
        have = raw.get("have") or {}
        if isinstance(have, dict):
            pairs = list(have.items())
        else:  # 리스트로 적었으면 전부 레벨 3으로 간주
            pairs = [(token, 3) for token in have]
        for token, level in pairs:
            keyword_id = dictionary.resolve(str(token))
            if keyword_id is None:
                unknown.append(str(token))
                continue
            try:
                parsed = int(level)
            except (TypeError, ValueError):
                parsed = 3
            levels[keyword_id] = max(1, min(5, parsed))

        highlights: list[Highlight] = []
        for item in raw.get("highlights") or []:
            resolved: list[str] = []
            for token in item.get("keywords") or []:
                keyword_id = dictionary.resolve(str(token))
                if keyword_id is None:
                    unknown.append(str(token))
                else:
                    resolved.append(keyword_id)
            highlights.append(
                Highlight(
                    title=str(item.get("title") or "(제목 없음)"),
                    summary=str(item.get("summary") or ""),
                    keywords=resolved,
                )
            )

        return cls(
            raw=raw,
            dictionary=dictionary,
            levels=levels,
            highlights=highlights,
            unknown_tokens=unknown,
        )


@dataclass
class MailConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str
    recipients: list[str]

    @classmethod
    def from_env(cls) -> MailConfig:
        host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
        port = int(os.getenv("SMTP_PORT", "465").strip() or 465)
        user = os.getenv("SMTP_USER", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        sender = os.getenv("MAIL_FROM", "").strip() or user
        raw_to = os.getenv("MAIL_TO", "").strip() or user
        recipients = [addr.strip() for addr in raw_to.replace(";", ",").split(",") if addr.strip()]
        missing = [
            name
            for name, value in (("SMTP_USER", user), ("SMTP_PASSWORD", password), ("MAIL_TO", raw_to))
            if not value
        ]
        if missing:
            raise RuntimeError(
                "메일 설정이 비어 있습니다: " + ", ".join(missing) +
                " (.env 또는 GitHub Secrets 를 확인하세요)"
            )
        return cls(host, port, user, password, sender, recipients)


def load_dotenv(path: str | Path = ROOT / ".env") -> None:
    """의존성 없이 .env 를 읽어 환경변수로 넣는다(이미 있는 값은 유지)."""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

"""역량 사전 로딩과 JD 본문에서의 역량 추출."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .text import contains_token, match_forms


@dataclass
class Keyword:
    id: str
    label: str
    weight: float = 1.0
    aliases: list[str] = field(default_factory=list)

    def all_tokens(self) -> list[str]:
        return [self.id, self.label, *self.aliases]


@dataclass
class KeywordDictionary:
    keywords: list[Keyword]

    def __post_init__(self) -> None:
        self._by_id = {kw.id: kw for kw in self.keywords}
        # 표기 → id 역색인 (profile.yaml 에 한글 표기를 써도 되게)
        self._by_token: dict[str, str] = {}
        for kw in self.keywords:
            for token in kw.all_tokens():
                self._by_token.setdefault(_norm_key(token), kw.id)

    def get(self, keyword_id: str) -> Keyword | None:
        return self._by_id.get(keyword_id)

    def resolve(self, token: str) -> str | None:
        """id, label, alias 중 아무 표기로든 역량 id 를 찾는다."""
        return self._by_token.get(_norm_key(token))

    def extract(self, text: str) -> list[Keyword]:
        """본문에 등장하는 역량들을 사전 순서대로 반환."""
        if not text.strip():
            return []
        forms = match_forms(text)
        found: list[Keyword] = []
        for kw in self.keywords:
            if any(contains_token(forms, token) for token in kw.all_tokens()):
                found.append(kw)
        return found

    @classmethod
    def load(cls, path: str | Path) -> KeywordDictionary:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        items = data.get("keywords") or []
        keywords = [
            Keyword(
                id=str(item["id"]),
                label=str(item.get("label") or item["id"]),
                weight=float(item.get("weight", 1.0)),
                aliases=[str(a) for a in (item.get("aliases") or [])],
            )
            for item in items
        ]
        if not keywords:
            raise ValueError(f"{path} 에 keywords 항목이 없습니다")
        return cls(keywords)


def _norm_key(token: str) -> str:
    return "".join(token.lower().split())

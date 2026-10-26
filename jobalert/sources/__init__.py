"""수집기 레지스트리. 새 사이트는 여기에 등록만 하면 파이프라인에 붙는다."""

from __future__ import annotations

from typing import Any, Callable

from .base import HttpClient, Source, pick
from .wanted import WantedSource

SourceFactory = Callable[[dict[str, Any]], Source]

REGISTRY: dict[str, SourceFactory] = {
    "wanted": lambda search: WantedSource(search),
}


def build_sources(names: list[str], search: dict[str, Any]) -> list[Source]:
    sources: list[Source] = []
    for name in names:
        factory = REGISTRY.get(name)
        if factory is None:
            raise KeyError(f"알 수 없는 수집기: {name} (가능: {', '.join(REGISTRY)})")
        sources.append(factory(search))
    return sources


__all__ = ["HttpClient", "Source", "WantedSource", "REGISTRY", "build_sources", "pick"]

"""수집기 공통 인터페이스."""

from __future__ import annotations

import time
from typing import Any, Iterable, Protocol

import requests

from ..models import JobPosting

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class Source(Protocol):
    """공고 수집기. 새 사이트를 붙일 때 이 모양만 맞추면 된다."""

    name: str

    def fetch(self) -> Iterable[JobPosting]:
        ...


class HttpClient:
    """재시도와 간단한 레이트리밋이 붙은 JSON 클라이언트."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        retries: int = 3,
        delay: float = 0.3,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                **(headers or {}),
            }
        )

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        last_error: Exception | None = None
        detail = ""
        for attempt in range(self.retries):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code >= 400:
                    detail = _body_snippet(response)
                response.raise_for_status()
                return response.json()
            except Exception as error:  # 네트워크/파싱 오류 모두 재시도
                last_error = error
                if attempt < self.retries - 1:
                    time.sleep(2 ** attempt)
        message = f"요청 실패: {url} ({last_error})"
        if detail:
            # 원인 파악에 꼭 필요한 응답 본문 일부를 로그에 남긴다
            message += f"\n  응답 내용: {detail}"
        raise RuntimeError(message) from last_error

    def pause(self) -> None:
        if self.delay:
            time.sleep(self.delay)


def _body_snippet(response: Any, limit: int = 300) -> str:
    """오류 응답 본문 앞부분을 한 줄로 정리해 돌려준다."""
    try:
        body = response.text or ""
    except Exception:
        return ""
    body = " ".join(body.split())
    return body[:limit] + ("…" if len(body) > limit else "")


def pick(data: Any, *paths: str, default: Any = None) -> Any:
    """'job.detail.requirements' 같은 경로를 순서대로 시도해 첫 값을 반환.

    사이트가 응답 구조를 바꿔도 다른 경로로 살아남게 하기 위한 헬퍼.
    """
    for path in paths:
        cursor: Any = data
        ok = True
        for part in path.split("."):
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            else:
                ok = False
                break
        if ok and cursor not in (None, ""):
            return cursor
    return default

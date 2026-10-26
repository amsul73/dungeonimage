"""사람인 공개 채용정보 API 수집기.

사람인 개발자센터에서 무료로 발급받는 access-key 로 호출하는 공식 API다.
(https://oapi.saramin.co.kr/guide/job-search)

이 API 는 공고의 JD 본문(자격요건·우대사항 전문)을 제공하지 않는다.
따라서 제목·직무 분류·공고 키워드를 모아 1차 스크리닝 점수를 내고,
`detail_level="summary"` 로 표시해 알림에서 "링크에서 본문 확인" 안내를 띄운다.
"""

from __future__ import annotations

import os
from typing import Any, Iterator

from ..models import JobPosting
from ..text import strip_html
from .base import HttpClient, pick

API_URL = "https://oapi.saramin.co.kr/job-search"
MAX_COUNT = 110  # API 가 허용하는 페이지당 최대 건수


class SaraminSource:
    name = "saramin"

    def __init__(
        self,
        search: dict[str, Any],
        client: HttpClient | None = None,
        access_key: str | None = None,
    ) -> None:
        self.search = search or {}
        self.client = client or HttpClient()
        self.access_key = access_key or os.getenv("SARAMIN_API_KEY", "").strip()

    # ── 요청 ────────────────────────────────────────────────────────────
    def list_params(self, page: int) -> dict[str, Any]:
        search = self.search
        count = min(int(search.get("limit_per_page", 100)), MAX_COUNT)
        params: dict[str, Any] = {
            "access-key": self.access_key,
            "start": page,
            "count": count,
            "sort": str(search.get("saramin_sort", "pd")),  # pd = 등록일 최신순
            "fields": "posting-date,expiration-date,keyword-code",
        }
        for key, param in (
            ("saramin_loc_mcd", "loc_mcd"),      # 근무지 대분류 (서울 = 101)
            ("saramin_loc_cd", "loc_cd"),        # 근무지 소분류
            ("saramin_job_mid_cd", "job_mid_cd"),  # 직무 중분류 (기획·전략 = 2)
            ("saramin_job_cd", "job_cd"),        # 직무 소분류
            ("saramin_edu_lv", "edu_lv"),
            ("saramin_job_type", "job_type"),
        ):
            value = search.get(key)
            if value in (None, "", []):
                continue
            params[param] = ",".join(str(v) for v in value) if isinstance(value, list) else str(value)

        keywords = search.get("saramin_keywords")
        if keywords:
            params["keywords"] = (
                ",".join(str(k) for k in keywords) if isinstance(keywords, list) else str(keywords)
            )
        return params

    def iter_items(self) -> Iterator[dict[str, Any]]:
        if not self.access_key:
            raise RuntimeError(
                "SARAMIN_API_KEY 가 없습니다. 사람인 개발자센터에서 발급한 키를 "
                ".env 또는 GitHub Secrets 에 넣어주세요."
            )
        max_pages = int(self.search.get("max_pages", 4))
        count = min(int(self.search.get("limit_per_page", 100)), MAX_COUNT)
        for page in range(max_pages):
            payload = self.client.get_json(API_URL, self.list_params(page))
            items = pick(payload, "jobs.job", "job", "jobs", default=[]) or []
            if isinstance(items, dict):   # 결과가 1건이면 리스트가 아닌 객체로 오는 경우 방어
                items = [items]
            if not isinstance(items, list) or not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            if len(items) < count:
                return
            self.client.pause()

    def fetch(self) -> Iterator[JobPosting]:
        limit = int(self.search.get("fetch_detail_limit", 200))
        seen: set[str] = set()
        for index, item in enumerate(self.iter_items()):
            if index >= limit:
                return
            job_id = str(pick(item, "id", "job_id", default="") or "").strip()
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            yield self.to_posting(job_id, item)

    # ── 매핑 ────────────────────────────────────────────────────────────
    def to_posting(self, job_id: str, item: dict[str, Any]) -> JobPosting:
        text = lambda value: strip_html(str(value)).strip() if value else ""  # noqa: E731

        title = text(pick(item, "position.title", "title", default=""))
        location = text(pick(item, "position.location.name", "location.name", default=""))
        # "서울 &gt; 강남구" → "서울 > 강남구"
        location = location.replace(" > ", " ").replace(">", " ").strip()

        tags = _split_tags(
            [
                pick(item, "position.job-code.name", default=""),
                pick(item, "position.job-mid-code.name", default=""),
                pick(item, "position.industry.name", default=""),
                pick(item, "keyword", default=""),
            ]
        )
        experience = pick(item, "position.experience-level", default={}) or {}

        return JobPosting(
            source=self.name,
            job_id=job_id,
            title=title,
            company=text(pick(item, "company.detail.name", "company.name", default="")),
            url=str(pick(item, "url", "company.detail.href", default="") or ""),
            location=location,
            posted_at=str(pick(item, "posting-date", "posting-timestamp", default="") or ""),
            annual_from=_min_years(experience),
            annual_to=_as_int(experience.get("max")) if isinstance(experience, dict) else None,
            # JD 본문이 없으므로 제목·직무분류·키워드를 자격요건 자리에 모아 채점한다
            requirements="\n".join(tags),
            detail_level="summary",
            tags=tags,
            raw_text=text(pick(item, "position.experience-level.name", default="")),
        )


def _split_tags(values: list[Any]) -> list[str]:
    tags: list[str] = []
    for value in values:
        if not value:
            continue
        for token in strip_html(str(value)).replace("·", ",").split(","):
            token = token.strip()
            if token and token not in tags:
                tags.append(token)
    return tags


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _min_years(experience: Any) -> int | None:
    """경력 조건에서 최소 요구 연차를 뽑는다. 신입/경력무관이면 0."""
    if not isinstance(experience, dict):
        return None
    name = strip_html(str(experience.get("name") or "")).strip()
    if any(token in name for token in ("신입", "경력무관", "무관")):
        return 0
    minimum = _as_int(experience.get("min"))
    if minimum is not None:
        return minimum
    return _as_int(experience.get("code"))

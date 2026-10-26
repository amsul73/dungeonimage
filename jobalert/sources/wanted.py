"""원티드(wanted.co.kr) 공고 수집기.

공식 공개 API 가 아니라 웹 프론트엔드가 쓰는 JSON 엔드포인트를 이용한다.
응답 구조가 바뀔 수 있으므로 모든 필드는 여러 경로를 시도해서 읽고,
`python main.py probe` 로 실제 응답을 눈으로 확인할 수 있게 해뒀다.
"""

from __future__ import annotations

from typing import Any, Iterator

from ..models import JobPosting
from ..text import strip_html
from .base import HttpClient, pick

API_LIST = "https://www.wanted.co.kr/api/v4/jobs"
API_DETAIL = "https://www.wanted.co.kr/api/v4/jobs/{job_id}"
JOB_URL = "https://www.wanted.co.kr/wd/{job_id}"


class WantedSource:
    name = "wanted"

    def __init__(self, search: dict[str, Any], client: HttpClient | None = None) -> None:
        self.search = search or {}
        self.client = client or HttpClient()

    # ── 목록 ────────────────────────────────────────────────────────────
    def list_params(self, offset: int) -> dict[str, Any]:
        search = self.search
        params: dict[str, Any] = {
            "country": "kr",
            "job_sort": "job.latest_order",
            "limit": int(search.get("limit_per_page", 50)),
            "offset": offset,
        }
        years = search.get("years")
        if years is not None:
            params["years"] = int(years)
        locations = search.get("locations") or []
        if locations:
            params["locations"] = ",".join(str(loc) for loc in locations)
        tag_ids = search.get("wanted_tag_ids") or []
        if tag_ids:
            params["tag_type_ids"] = ",".join(str(tag) for tag in tag_ids)
        group_ids = search.get("wanted_group_ids") or []
        if group_ids:
            params["job_group_id"] = ",".join(str(gid) for gid in group_ids)
        return params

    def iter_summaries(self) -> Iterator[dict[str, Any]]:
        limit = int(self.search.get("limit_per_page", 50))
        max_pages = int(self.search.get("max_pages", 4))
        for page in range(max_pages):
            payload = self.client.get_json(API_LIST, self.list_params(page * limit))
            items = pick(payload, "data", "jobs", "results", default=[]) or []
            if not isinstance(items, list) or not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            if len(items) < limit:
                return
            self.client.pause()

    # ── 상세 ────────────────────────────────────────────────────────────
    def fetch_detail(self, job_id: str) -> dict[str, Any]:
        payload = self.client.get_json(API_DETAIL.format(job_id=job_id))
        job = pick(payload, "job", "data", default=payload)
        return job if isinstance(job, dict) else {}

    def fetch(self) -> Iterator[JobPosting]:
        detail_limit = int(self.search.get("fetch_detail_limit", 80))
        seen: set[str] = set()
        for index, summary in enumerate(self.iter_summaries()):
            if index >= detail_limit:
                return
            raw_id = pick(summary, "id", "job_id", default=None)
            job_id = "" if raw_id is None else str(raw_id).strip()
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            try:
                detail = self.fetch_detail(job_id)
            except RuntimeError:
                detail = {}
            self.client.pause()
            yield self.to_posting(job_id, summary, detail)

    # ── 매핑 ────────────────────────────────────────────────────────────
    def to_posting(
        self,
        job_id: str,
        summary: dict[str, Any],
        detail: dict[str, Any],
    ) -> JobPosting:
        merged: dict[str, Any] = {**summary, **detail}
        text = lambda value: strip_html(str(value)).strip() if value else ""  # noqa: E731

        annual_from = pick(merged, "annual_from", "annual.from")
        annual_to = pick(merged, "annual_to", "annual.to")
        return JobPosting(
            source=self.name,
            job_id=job_id,
            title=text(pick(merged, "position", "title", "name", default="")),
            company=text(
                pick(merged, "company.name", "company_name", "company.title", default="")
            ),
            url=JOB_URL.format(job_id=job_id),
            location=text(
                pick(
                    merged,
                    "address.location",
                    "address.full_location",
                    "company_location",
                    "location",
                    default="",
                )
            ),
            posted_at=str(pick(merged, "confirm_time", "published_at", "created_at", default="")),
            annual_from=_as_int(annual_from),
            annual_to=_as_int(annual_to),
            intro=text(pick(merged, "detail.intro", "intro", "company.detail", default="")),
            main_tasks=text(pick(merged, "detail.main_tasks", "main_tasks", default="")),
            requirements=text(
                pick(merged, "detail.requirements", "requirements", "qualifications", default="")
            ),
            preferred=text(
                pick(
                    merged,
                    "detail.preferred_points",
                    "preferred_points",
                    "preferred",
                    "detail.preferred",
                    default="",
                )
            ),
            benefits=text(pick(merged, "detail.benefits", "benefits", default="")),
        )


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

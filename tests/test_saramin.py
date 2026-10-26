import pytest

from jobalert.matcher import check_filters, score_job
from jobalert.sources.saramin import SaraminSource

SEARCH = {
    "saramin_loc_mcd": "101",
    "saramin_job_mid_cd": [2],
    "saramin_keywords": ["서비스기획", "PM"],
    "limit_per_page": 100,
    "max_pages": 2,
    "fetch_detail_limit": 5,
}


def make_item(job_id="51234", **overrides):
    item = {
        "id": job_id,
        "url": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={job_id}",
        "company": {"detail": {"name": "테스트컴퍼니"}},
        "position": {
            "title": "[신입] 서비스기획자 모집",
            "location": {"name": "서울 &gt; 강남구"},
            "job-code": {"name": "서비스기획,웹기획,PM·PO"},
            "job-mid-code": {"name": "기획·전략"},
            "industry": {"name": "솔루션·SI"},
            "experience-level": {"code": 1, "min": 0, "max": 0, "name": "신입"},
        },
        "keyword": "서비스기획,와이어프레임,피그마,요구사항정의서",
        "posting-date": "2026-10-26",
    }
    item.update(overrides)
    return item


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append(params)
        index = (params or {}).get("start", 0)
        items = self.pages[index] if index < len(self.pages) else []
        return {"jobs": {"count": len(items), "start": index, "job": items}}

    def pause(self):
        pass


def source(**kwargs) -> SaraminSource:
    return SaraminSource(SEARCH, access_key="TESTKEY", **kwargs)


# ── 파라미터 ───────────────────────────────────────────────────────────────
def test_list_params_map_config_to_api_names():
    params = source().list_params(0)
    assert params["access-key"] == "TESTKEY"
    assert params["loc_mcd"] == "101"           # 서울
    assert params["job_mid_cd"] == "2"          # 기획·전략
    assert params["keywords"] == "서비스기획,PM"
    assert params["count"] == 100


def test_count_is_capped_at_api_limit():
    params = SaraminSource({**SEARCH, "limit_per_page": 500}, access_key="K").list_params(0)
    assert params["count"] == 110


def test_missing_key_raises_readable_error():
    with pytest.raises(RuntimeError, match="SARAMIN_API_KEY"):
        list(SaraminSource(SEARCH, access_key="").fetch())


# ── 매핑 ───────────────────────────────────────────────────────────────────
def test_to_posting_maps_saramin_shape():
    job = source().to_posting("51234", make_item())
    assert job.key == "saramin:51234"
    assert job.company == "테스트컴퍼니"
    assert job.location == "서울 강남구"          # &gt; 복원 후 정리
    assert job.annual_from == 0                   # 신입
    assert job.detail_level == "summary"          # JD 본문 없음
    assert "피그마" in job.tags and "PO" in job.tags


def test_experience_name_takes_priority_over_min():
    item = make_item()
    item["position"]["experience-level"] = {"code": 0, "min": 3, "name": "경력무관"}
    assert source().to_posting("1", item).annual_from == 0


def test_experience_min_used_when_name_is_career():
    item = make_item()
    item["position"]["experience-level"] = {"code": 2, "min": 3, "max": 7, "name": "경력 3~7년"}
    job = source().to_posting("1", item)
    assert job.annual_from == 3 and job.annual_to == 7


def test_single_result_object_is_handled():
    client = FakeClient([])
    client.get_json = lambda url, params=None: {"jobs": {"job": make_item()}}
    jobs = list(SaraminSource({**SEARCH, "max_pages": 1}, client=client, access_key="K").fetch())
    assert len(jobs) == 1


def test_fetch_skips_duplicates_and_respects_limit():
    pages = {0: [make_item("1"), make_item("1"), make_item("2")]}
    jobs = list(SaraminSource({**SEARCH, "max_pages": 1}, client=FakeClient(pages), access_key="K").fetch())
    assert [job.job_id for job in jobs] == ["1", "2"]


# ── 채점 ───────────────────────────────────────────────────────────────────
def test_summary_job_scores_on_available_section_only(profile):
    """우대사항이 없는 소스라도 중립값 50%로 깎이지 않아야 한다."""
    job = source().to_posting("51234", make_item())
    assert check_filters(job, profile) is None
    result = score_job(job, profile)
    assert result.requirement.available is True
    assert result.preferred.available is False       # 섹션 자체가 없음
    assert result.score > 50


def test_career_job_is_filtered_out(profile):
    item = make_item()
    item["position"]["title"] = "서비스기획 경력직 채용"
    item["position"]["experience-level"] = {"code": 2, "min": 5, "name": "경력 5년 이상"}
    assert check_filters(source().to_posting("9", item), profile) is not None


def test_non_seoul_job_is_filtered_out(profile):
    item = make_item()
    item["position"]["location"] = {"name": "경기 &gt; 성남시 분당구"}
    assert "서울" in (check_filters(source().to_posting("9", item), profile) or "")

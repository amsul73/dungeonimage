from jobalert.sources.base import pick
from jobalert.sources.wanted import WantedSource

SEARCH = {
    "wanted_tag_ids": [10110, 10231],
    "locations": ["seoul"],
    "years": 0,
    "limit_per_page": 20,
    "max_pages": 2,
    "fetch_detail_limit": 5,
}


class FakeClient:
    """목록 2페이지 + 상세를 흉내내는 테스트용 클라이언트."""

    def __init__(self, pages, details):
        self.pages = pages
        self.details = details
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("/jobs"):
            offset = (params or {}).get("offset", 0)
            index = offset // SEARCH["limit_per_page"]
            return {"data": self.pages[index] if index < len(self.pages) else []}
        job_id = url.rstrip("/").split("/")[-1]
        return {"job": self.details[job_id]}

    def pause(self):
        pass


def test_list_params_include_filters():
    params = WantedSource(SEARCH).list_params(40)
    assert params["locations"] == "seoul"
    assert params["tag_type_ids"] == "10110,10231"
    assert params["years"] == 0
    assert params["offset"] == 40


def test_pick_tries_paths_in_order():
    data = {"detail": {"preferred_points": "SQL"}}
    assert pick(data, "detail.preferred", "detail.preferred_points") == "SQL"
    assert pick(data, "nope", default="fallback") == "fallback"


def test_to_posting_maps_nested_wanted_shape():
    source = WantedSource(SEARCH)
    summary = {"id": 777, "position": "서비스 기획자", "company": {"name": "원티드랩"},
               "address": {"location": "서울 강남구"}, "annual_from": 0, "annual_to": 3}
    detail = {"detail": {"intro": "<p>소개</p>", "main_tasks": "주요 업무",
                         "requirements": "<li>요구사항 정의</li>",
                         "preferred_points": "SQL 활용", "benefits": "복지"}}
    job = source.to_posting("777", summary, detail)

    assert job.key == "wanted:777"
    assert job.url == "https://www.wanted.co.kr/wd/777"
    assert job.company == "원티드랩"
    assert job.location == "서울 강남구"
    assert job.requirements == "요구사항 정의"      # 태그 제거
    assert job.preferred == "SQL 활용"
    assert job.annual_from == 0 and job.annual_to == 3


def test_to_posting_survives_flat_shape():
    """상세 응답이 평평한 구조로 바뀌어도 필드를 찾아낸다."""
    job = WantedSource(SEARCH).to_posting(
        "1",
        {"job_id": 1, "title": "PM", "company_name": "회사", "location": "서울"},
        {"requirements": "기획", "preferred": "SQL"},
    )
    assert job.title == "PM" and job.company == "회사"
    assert job.requirements == "기획" and job.preferred == "SQL"


def test_to_posting_tolerates_missing_fields():
    job = WantedSource(SEARCH).to_posting("2", {}, {})
    assert job.job_id == "2" and job.title == "" and job.annual_from is None


def test_fetch_pages_and_stops_at_detail_limit():
    pages = [[{"id": i} for i in range(SEARCH["limit_per_page"])], [{"id": 100}]]
    details = {str(i): {"position": f"기획자 {i}"} for i in list(range(20)) + [100]}
    source = WantedSource(SEARCH, client=FakeClient(pages, details))
    jobs = list(source.fetch())
    assert len(jobs) == SEARCH["fetch_detail_limit"]
    assert jobs[0].title == "기획자 0"


def test_fetch_skips_duplicate_ids():
    pages = [[{"id": 5}, {"id": 5}, {"id": 6}]]
    details = {"5": {"position": "A"}, "6": {"position": "B"}}
    source = WantedSource({**SEARCH, "limit_per_page": 20}, client=FakeClient(pages, details))
    assert [job.job_id for job in source.fetch()] == ["5", "6"]

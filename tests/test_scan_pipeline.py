"""scan 명령의 전 과정(수집 → 필터 → 빈도 집계 → 출력) 검증.

원티드 수집은 네트워크를 타므로 응답 형태를 흉내낸 가짜 클라이언트를 끼운다.
실제 공고 데이터가 아니라 '코드 경로가 끝까지 돌아가는지'를 보는 테스트다.
"""

from __future__ import annotations

import json

import pytest

from jobalert import cli, sources
from jobalert.sources.wanted import WantedSource
from tests.conftest import TEST_PROFILE

SEARCH = {
    "locations": ["seoul"],
    "years": 0,
    "limit_per_page": 10,
    "max_pages": 1,
    "fetch_detail_limit": 10,
}

# 원티드 상세 응답 모양 그대로: detail 아래 섹션이 필드로 분리돼 온다
DETAILS = {
    "1": {
        "position": "서비스 기획자",
        "company": {"name": "가가"},
        "address": {"location": "서울 강남구"},
        "annual_from": 0,
        "detail": {
            "main_tasks": "<li>핵심 지표를 정의하고 퍼널을 분석합니다</li>",
            "requirements": "<li>SQL 로 직접 데이터를 추출할 수 있는 분</li><li>화면설계서 작성 경험</li>",
            "preferred_points": "<li>A/B 테스트 설계 경험</li>",
        },
    },
    "2": {
        "position": "프로덕트 매니저",
        "company": {"name": "나나"},
        "address": {"location": "서울 성동구"},
        "annual_from": 0,
        "detail": {
            "main_tasks": "<li>프로덕트 로드맵을 수립합니다</li>",
            "requirements": "<li>SQL 쿼리 작성 가능</li><li>요구사항 정의서 작성 경험</li>",
            "preferred_points": "<li>앰플리튜드 등 프로덕트 분석 툴 경험</li>",
        },
    },
    # 하드 필터에 걸려야 하는 공고 (서울 아님 + 제목이 개발자)
    "3": {
        "position": "백엔드 개발자",
        "company": {"name": "다다"},
        "address": {"location": "부산 해운대구"},
        "annual_from": 5,
        "detail": {"requirements": "<li>Java 5년 이상</li>"},
    },
}


class FakeClient:
    def __init__(self) -> None:
        self.detail_calls: list[str] = []

    def get_json(self, url, params=None):
        if url.endswith("/jobs"):
            offset = (params or {}).get("offset", 0)
            return {"data": [{"id": int(k)} for k in DETAILS] if offset == 0 else []}
        job_id = url.rstrip("/").split("/")[-1]
        self.detail_calls.append(job_id)
        return {"job": DETAILS[job_id]}

    def pause(self) -> None:
        pass


@pytest.fixture()
def fake_wanted(monkeypatch):
    client = FakeClient()
    monkeypatch.setitem(
        sources.REGISTRY,
        "wanted",
        # SEARCH 는 기본값이고 profile.yaml / --limit 에서 온 값이 이겨야 한다
        lambda search: WantedSource({**SEARCH, **search}, client=client),
    )
    return client


def test_scan_명령이_원티드_수집부터_리포트까지_끝까지_돈다(fake_wanted, tmp_path, capsys):
    markdown = tmp_path / "요구역량.md"
    payload = tmp_path / "요구역량.json"

    exit_code = cli.main(
        [
            "--profile", str(TEST_PROFILE),
            "scan", "--source", "wanted",
            "--markdown", str(markdown),
            "--json", str(payload),
        ]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    # 부산/개발자 공고는 하드 필터에서 빠지고 2건만 집계된다
    assert "하드 필터로 1건 제외" in out
    assert "JD 본문 확보 2건" in out
    # 두 공고 모두 자격요건에 SQL 을 요구 → 등장률 100%
    assert "SQL" in out

    data = json.loads(payload.read_text(encoding="utf-8"))
    assert data["analyzed"] == 2
    sql = next(d for d in data["demands"] if d["id"] == "sql")
    assert sql["coverage"] == 1.0
    assert sql["required"] == 2 and sql["preferred"] == 0
    # 근거 문장이 원티드 HTML 에서 태그가 벗겨진 상태로 들어온다
    assert any("추출" in line for line in sql["evidence"])
    assert "<li>" not in json.dumps(data, ensure_ascii=False)

    assert "## 1. 공통 요구 역량" in markdown.read_text(encoding="utf-8")


def test_scan_은_jd폴더와_수집을_함께_집계한다(fake_wanted, tmp_path, capsys):
    (tmp_path / "라라_기획자.txt").write_text(
        "자격요건\n- 사용성 테스트 진행 경험\n", encoding="utf-8"
    )

    cli.main(
        ["--profile", str(TEST_PROFILE), "scan", "--jd-dir", str(tmp_path), "--source", "wanted"]
    )
    out = capsys.readouterr().out

    assert "JD 본문 확보 3건" in out          # jd 파일 1건 + 원티드 2건
    assert "사용성 테스트" in out


def test_no_filters_면_걸러질_공고도_집계한다(fake_wanted, capsys):
    cli.main(["--profile", str(TEST_PROFILE), "scan", "--source", "wanted", "--no-filters"])
    out = capsys.readouterr().out

    assert "하드 필터로" not in out
    assert "JD 본문 확보 3건" in out


def test_limit_옵션이_수집_상한을_덮어쓴다(fake_wanted, capsys):
    cli.main(["--profile", str(TEST_PROFILE), "scan", "--source", "wanted", "--limit", "1"])
    out = capsys.readouterr().out

    assert fake_wanted.detail_calls == ["1"]   # 상세 조회를 1건만 한다
    assert "수집 1건" in out

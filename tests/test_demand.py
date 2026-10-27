"""요구 역량 빈도 분석 테스트."""

from __future__ import annotations

from jobalert import demand
from jobalert.models import JobPosting


def _job(job_id: str, *, requirements: str = "", preferred: str = "", main_tasks: str = "") -> JobPosting:
    return JobPosting(
        source="test",
        job_id=job_id,
        title="서비스 기획자",
        company="테스트",
        url="",
        location="서울",
        requirements=requirements,
        preferred=preferred,
        main_tasks=main_tasks,
    )


def test_등장률은_역량을_언급한_공고_비율이다(profile):
    postings = [
        _job("1", requirements="SQL 쿼리 작성 가능"),
        _job("2", requirements="SQL 활용 경험"),
        _job("3", requirements="화면설계서 작성 경험"),
        _job("4", requirements="화면설계서 작성 경험"),
    ]
    report = demand.analyze(postings, profile)

    assert report.analyzed == 4
    assert report.coverage_of("sql") == 0.5
    assert report.coverage_of("wireframe") == 0.5


def test_같은_공고에서_여러_섹션에_나와도_공고_수는_한_번만_센다(profile):
    postings = [
        _job("1", requirements="SQL 활용", preferred="SQL 고급 쿼리", main_tasks="SQL 로 지표 추출"),
    ]
    report = demand.analyze(postings, profile)
    sql = next(d for d in report.demands if d.keyword_id == "sql")

    assert sql.postings == 1
    assert (sql.required, sql.preferred, sql.tasks) == (1, 1, 1)


def test_필수비중은_자격요건에_등장한_비율이다(profile):
    postings = [
        _job("1", requirements="SQL 활용 경험"),
        _job("2", preferred="SQL 활용 경험"),
        _job("3", preferred="SQL 활용 경험"),
        _job("4", requirements="A/B 테스트 경험"),
    ]
    report = demand.analyze(postings, profile)
    sql = next(d for d in report.demands if d.keyword_id == "sql")

    assert sql.postings == 3
    assert sql.required == 1
    assert sql.essential_ratio == 1 / 3


def test_본문이_없는_요약_공고는_기본적으로_집계에서_빠진다(profile):
    summary = _job("1", requirements="기획·전략, 서비스기획")
    summary.detail_level = "summary"
    summary.tags = ["기획·전략", "서비스기획"]
    full = _job("2", requirements="SQL 활용 경험")

    report = demand.analyze([summary, full], profile)

    assert (report.analyzed, report.summary_only) == (1, 1)
    # 집계에서 빠져도 직무 태그는 참고용으로 남는다
    assert ("기획·전략", 1) in report.tag_counts


def test_include_summary_면_요약_공고도_집계한다(profile):
    summary = _job("1", requirements="SQL 활용 경험")
    summary.detail_level = "summary"

    report = demand.analyze([summary], profile, include_summary=True)

    assert report.analyzed == 1
    assert report.coverage_of("sql") == 1.0


def test_이미_보유한_역량은_갭이_아니라_강점으로_분류된다(profile):
    # test_profile.yaml 기준: wireframe 은 보유(레벨 3+), sql 은 미보유/저레벨
    postings = [_job("1", requirements="화면설계서 작성, SQL 쿼리 작성")]
    report = demand.analyze(postings, profile)

    strengths = {d.keyword_id for d in report.strengths}
    gaps = {g.demand.keyword_id for g in report.gaps}

    assert "wireframe" in strengths
    assert "sql" in gaps
    assert not (strengths & gaps)


def test_우선순위는_등장률과_결핍도가_클수록_높다(profile):
    흔한것 = "SQL 쿼리 작성 가능"
    드문것 = "앰플리튜드 활용 경험"
    postings = [_job(str(i), requirements=흔한것) for i in range(9)]
    postings.append(_job("9", requirements=f"{흔한것}\n{드문것}"))

    report = demand.analyze(postings, profile)
    ranked = [g.demand.keyword_id for g in report.gaps]

    assert ranked.index("sql") < ranked.index("product_analytics")


def test_근거_문장은_원문에서_가져온다(profile):
    postings = [
        _job("1", requirements="- SQL을 활용해 직접 데이터를 추출할 수 있는 분\n- 협업 경험"),
    ]
    report = demand.analyze(postings, profile)
    sql = next(d for d in report.demands if d.keyword_id == "sql")

    assert sql.evidence == ["SQL을 활용해 직접 데이터를 추출할 수 있는 분"]


def test_근거_문장은_역량당_상한을_넘지_않는다(profile):
    postings = [
        _job(str(i), requirements=f"SQL 쿼리 작성 경험 {i}번 공고") for i in range(10)
    ]
    report = demand.analyze(postings, profile)
    sql = next(d for d in report.demands if d.keyword_id == "sql")

    assert len(sql.evidence) == demand.MAX_EVIDENCE


def test_사전에_있는_표현은_미등록_표현으로_보고하지_않는다(profile):
    postings = [_job(str(i), requirements="SQL 쿼리 작성 가능") for i in range(5)]
    report = demand.analyze(postings, profile, min_phrase_df=2)
    phrases = {phrase for phrase, _ in report.unknown_phrases}

    assert "sql" not in phrases
    assert not any("쿼리" in phrase for phrase in phrases)


def test_미등록_빈출_표현을_찾아낸다(profile):
    postings = [
        _job(str(i), requirements="옴니채널 리테일 도메인 이해가 필요합니다") for i in range(5)
    ]
    report = demand.analyze(postings, profile, min_phrase_df=3)
    phrases = {phrase for phrase, _ in report.unknown_phrases}

    assert any("옴니채널" in phrase for phrase in phrases)


def test_양끝의_범용어는_잘려_나간다():
    assert demand._trim_stopwords(["설계", "경험"]) == ["설계"]
    assert demand._trim_stopwords(["관련", "업무", "경험"]) == []
    assert demand._trim_stopwords(["옴니채널", "리테일"]) == ["옴니채널", "리테일"]


def test_공고가_없으면_안내_문구를_낸다(profile):
    report = demand.analyze([], profile)
    text = demand.to_text(report, profile)

    assert report.analyzed == 0
    assert "jd/" in text


def test_마크다운과_json_을_렌더링한다(profile):
    postings = [_job("1", requirements="SQL 쿼리 작성", preferred="A/B 테스트 경험")]
    report = demand.analyze(postings, profile)

    markdown = demand.to_markdown(report, profile)
    assert "## 1. 공통 요구 역량" in markdown
    assert "| SQL |" in markdown

    payload = demand.to_dict(report, profile)
    assert payload["analyzed"] == 1
    assert {d["id"] for d in payload["demands"]} >= {"sql", "ab_test"}
    assert payload["gaps"][0]["evidence"]

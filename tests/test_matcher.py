from jobalert.matcher import check_filters, required_years, score_job, score_section
from jobalert.models import JobPosting


def make_job(**kwargs) -> JobPosting:
    base = dict(
        source="test",
        job_id="1",
        title="서비스 기획자",
        company="테스트",
        url="https://example.com/1",
        location="서울 강남구",
    )
    base.update(kwargs)
    return JobPosting(**base)


# ── 요구 경력 파싱 ──────────────────────────────────────────────────────────
def test_required_years_reads_experience_phrase():
    assert required_years(make_job(requirements="경력 3년 이상")) == 3
    assert required_years(make_job(requirements="5년 이상의 PM 경험")) == 5
    assert required_years(make_job(requirements="3+ years of experience")) == 3


def test_newcomer_phrase_wins_over_years():
    job = make_job(requirements="신입 지원 가능, 경력 3년 이상도 환영")
    assert required_years(job) == 0


def test_required_years_falls_back_to_annual_from():
    assert required_years(make_job(requirements="기획 역량", annual_from=4)) == 4


def test_required_years_unknown_returns_none():
    assert required_years(make_job(requirements="기획 역량")) is None


def test_preferred_section_years_do_not_block(profile):
    job = make_job(requirements="기획 커뮤니케이션 역량", preferred="관련 경력 3년 이상 우대")
    assert check_filters(job, profile) is None


# ── 하드 필터 ──────────────────────────────────────────────────────────────
def test_filters_reject_non_seoul(profile):
    job = make_job(location="경기 성남시 분당구")
    assert "서울" in (check_filters(job, profile) or "")


def test_filters_reject_senior_title(profile):
    assert check_filters(make_job(title="시니어 프로덕트 매니저"), profile) is not None


def test_filters_keep_newcomer_title_with_excluded_word(profile):
    # '신입/경력' 처럼 신입도 받는 공고는 제외하지 않는다
    assert check_filters(make_job(title="[신입] 서비스 기획자 (경력 무관)"), profile) is None


def test_filters_reject_experience_over_limit(profile):
    assert "요구 경력" in (check_filters(make_job(requirements="경력 4년 이상"), profile) or "")


def test_filters_allow_unknown_location_when_empty(profile):
    assert check_filters(make_job(location=""), profile) is None


# ── 섹션 채점 ──────────────────────────────────────────────────────────────
def test_section_score_full_match(profile):
    section = score_section("자격요건", "요구사항 정의서 작성, 화면설계서, 피그마 활용", profile)
    assert section.ratio == 1.0
    assert not section.partial and not section.missing


def test_section_score_partial_for_low_level(profile):
    # A/B 테스트는 프로필에서 level 1 → 부분 점수만
    section = score_section("우대사항", "A/B 테스트 설계 경험", profile)
    assert 0 < section.ratio < 1
    assert "A/B 테스트" in section.partial


def test_section_score_missing_keyword(profile):
    for keyword_id in ("sql", "ga"):
        profile.levels.pop(keyword_id, None)
    section = score_section("자격요건", "SQL 쿼리 작성 능력, GA4 분석 경험", profile)
    assert section.ratio == 0.0
    assert "SQL" in section.missing


def test_section_with_single_keyword_is_held_neutral(profile):
    """역량이 하나만 잡히면 0%/100% 로 튀므로 판단을 보류한다."""
    section = score_section("자격요건", "Figma 활용 가능", profile)
    assert section.inferred is True
    assert section.ratio == profile.scoring["unknown_section_score"]
    assert "Figma" in section.matched


def test_section_score_is_neutral_when_nothing_detected(profile):
    section = score_section("자격요건", "열정과 책임감", profile)
    assert section.inferred is True
    assert section.ratio == profile.scoring["unknown_section_score"]


# ── 총점 ───────────────────────────────────────────────────────────────────
def test_score_job_combines_sections_and_bonuses(profile):
    job = make_job(
        title="[신입] 서비스 기획자",
        requirements="요구사항 정의서, 화면설계서, 피그마",
        preferred="A/B 테스트 경험",
    )
    result = score_job(job, profile)
    assert result.score > profile.threshold
    assert any("신입" in bonus for bonus in result.bonuses)
    assert any("서비스 기획" in bonus for bonus in result.bonuses)


def test_score_job_low_when_requirements_unmet(profile):
    for keyword_id in ("sql", "metrics", "ab_test", "product_analytics", "data_driven"):
        profile.levels.pop(keyword_id, None)
    job = make_job(
        title="데이터 프로덕트 기획자",
        requirements="SQL 분석, 지표 설계, A/B 테스트, Amplitude 활용",
        preferred="데이터 기반 의사결정",
    )
    result = score_job(job, profile)
    assert result.score < profile.threshold


def test_score_is_bounded(profile):
    job = make_job(
        title="신입 서비스 기획자 PM",
        requirements="피그마",
        preferred="노션",
    )
    assert 0 <= score_job(job, profile).score <= 100


def test_highlights_follow_job_keywords(profile):
    job = make_job(requirements="사용자 리서치와 퍼소나 도출 경험")
    result = score_job(job, profile)
    assert result.highlights
    assert "리서치" in result.highlights[0]

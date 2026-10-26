"""실제 profile.yaml 을 고칠 때의 안전망: 오타·구조 오류를 잡는다."""

from jobalert.config import DEFAULT_KEYWORDS, DEFAULT_PROFILE, Profile
from jobalert.matcher import check_filters, score_job
from jobalert.models import JobPosting


def real_profile() -> Profile:
    return Profile.load(DEFAULT_PROFILE, DEFAULT_KEYWORDS)


def test_real_profile_loads_without_unknown_keywords():
    profile = real_profile()
    assert not profile.unknown_tokens, (
        f"keywords.yaml 에 없는 표기: {profile.unknown_tokens}"
    )


def test_real_profile_has_required_sections():
    profile = real_profile()
    assert profile.levels, "have 가 비어 있습니다"
    assert profile.highlights, "highlights 가 비어 있습니다"
    for key in ("requirement_weight", "preferred_weight", "partial_level_factor"):
        assert key in profile.scoring
    assert 0 < profile.threshold <= 100


def test_real_profile_highlights_all_link_to_known_keywords():
    for highlight in real_profile().highlights:
        assert highlight.keywords, f"'{highlight.title}' 에 연결된 역량이 없습니다"


def test_real_profile_scores_a_typical_planner_job_above_threshold():
    """대표적인 신입 기획 공고는 알림 기준을 넘어야 한다."""
    profile = real_profile()
    job = JobPosting(
        source="test", job_id="1", title="[신입] 서비스 기획자", company="회사",
        url="https://example.com", location="서울 강남구",
        requirements="요구사항 정의서 및 화면설계서 작성\n개발자와 협업 경험\nFigma 활용",
        preferred="사용자 리서치 경험\nAI 서비스 기획 관심",
    )
    assert check_filters(job, profile) is None
    assert score_job(job, profile).score >= profile.threshold

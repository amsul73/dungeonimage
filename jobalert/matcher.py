"""자격요건/우대사항 충족도 기반 매칭 점수 계산."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Profile
from .keywords import Keyword
from .models import JobPosting, MatchResult, SectionScore
from .text import contains_token, match_forms, normalize

# "경력 3년", "3년 이상", "3+ years" 같은 요구 경력 표현
_YEARS_PATTERNS = (
    re.compile(r"경력\s*(\d{1,2})\s*년"),
    re.compile(r"(\d{1,2})\s*년\s*(?:이상|차|부터|\+)"),
    re.compile(r"(\d{1,2})\s*\+?\s*years?"),
)
_NEWCOMER_TOKENS = ("신입", "주니어", "junior", "entry level", "경력 무관", "경력무관", "신입 가능")
_SENIORITY_SAFE = ("신입", "주니어", "junior", "entry")


@dataclass
class Rejection:
    """하드 필터에서 걸러진 이유."""

    job: JobPosting
    reason: str


def required_years(job: JobPosting) -> int | None:
    """공고가 요구하는 최소 경력(년). 판단 불가면 None.

    제목과 자격요건만 본다. 우대사항의 'N년 경험 우대'는 신입 지원을 막지 않으므로 제외.
    """
    scope = "\n".join([job.title, job.requirements])
    text = normalize(scope)
    if any(token in text for token in _NEWCOMER_TOKENS):
        return 0
    found: list[int] = []
    for pattern in _YEARS_PATTERNS:
        found.extend(int(m.group(1)) for m in pattern.finditer(text))
    if not found:
        if job.annual_from is not None:
            return int(job.annual_from)
        return None
    return min(found)


def is_in_seoul(job: JobPosting, tokens: list[str]) -> bool:
    forms = match_forms(" ".join([job.location, job.title]))
    return any(contains_token(forms, token) for token in tokens)


def mentions_newcomer(job: JobPosting) -> bool:
    text = normalize(job.full_text())
    return any(token in text for token in _NEWCOMER_TOKENS)


def check_filters(job: JobPosting, profile: Profile) -> str | None:
    """하드 필터 통과 여부. 통과하면 None, 걸리면 사유 문자열."""
    filters = profile.filters
    title_forms = match_forms(job.title)

    excludes = [str(t) for t in (filters.get("exclude_title_keywords") or [])]
    title_norm = normalize(job.title)
    seniority_exempt = any(safe in title_norm for safe in _SENIORITY_SAFE)
    if not seniority_exempt:
        for token in excludes:
            if contains_token(title_forms, token):
                return f"제목 제외 키워드 '{token}'"

    if filters.get("require_seoul", True):
        tokens = [str(t) for t in (filters.get("seoul_tokens") or ["서울"])]
        if job.location and not is_in_seoul(job, tokens):
            return f"근무지가 서울이 아님 ({job.location})"

    max_years = int(filters.get("max_required_years", 1))
    years = required_years(job)
    if years is None:
        if not filters.get("allow_experience_unknown", True):
            return "요구 경력을 판단할 수 없음"
    elif years > max_years:
        return f"요구 경력 {years}년 (신입 지원 불가)"

    return None


def _level_factor(profile: Profile, keyword_id: str) -> float:
    table = profile.scoring.get("partial_level_factor") or {}
    level = profile.level_of(keyword_id)
    if level <= 0:
        return 0.0
    try:
        return float(table.get(level, table.get(str(level), 1.0)))
    except (TypeError, ValueError):
        return 1.0


def score_section(
    name: str,
    text: str,
    profile: Profile,
) -> SectionScore:
    """섹션에서 요구하는 역량 대비 내 보유 역량의 가중 충족도."""
    required: list[Keyword] = profile.dictionary.extract(text)
    if not required:
        neutral = float(profile.scoring.get("unknown_section_score", 0.5))
        return SectionScore(name=name, ratio=neutral, inferred=True)

    total = 0.0
    earned = 0.0
    matched: list[str] = []
    partial: list[str] = []
    missing: list[str] = []
    for keyword in required:
        total += keyword.weight
        factor = _level_factor(profile, keyword.id)
        earned += keyword.weight * factor
        if factor >= 1.0:
            matched.append(keyword.label)
        elif factor > 0.0:
            partial.append(keyword.label)
        else:
            missing.append(keyword.label)

    ratio = earned / total if total else 0.0
    return SectionScore(
        name=name,
        ratio=max(0.0, min(1.0, ratio)),
        matched=matched,
        partial=partial,
        missing=missing,
    )


def pick_highlights(job: JobPosting, profile: Profile, limit: int = 2) -> list[str]:
    """공고에서 요구한 역량과 겹치는 내 포트폴리오를 고른다."""
    wanted_ids = {
        kw.id
        for kw in profile.dictionary.extract("\n".join([job.requirements, job.preferred, job.main_tasks]))
    }
    if not wanted_ids:
        return []
    ranked = sorted(
        ((len(wanted_ids & set(h.keywords)), h) for h in profile.highlights),
        key=lambda pair: pair[0],
        reverse=True,
    )
    picked: list[str] = []
    for overlap, highlight in ranked:
        if overlap <= 0 or len(picked) >= limit:
            break
        text = highlight.title
        if highlight.summary:
            text = f"{highlight.title} — {highlight.summary}"
        picked.append(text)
    return picked


def score_job(job: JobPosting, profile: Profile) -> MatchResult:
    """공고 하나의 최종 점수(0~100)를 계산."""
    scoring = profile.scoring
    req = score_section("자격요건", job.requirements, profile)
    pref = score_section("우대사항", job.preferred, profile)

    req_w = float(scoring.get("requirement_weight", 0.65))
    pref_w = float(scoring.get("preferred_weight", 0.35))
    denom = req_w + pref_w or 1.0
    base = (req.ratio * req_w + pref.ratio * pref_w) / denom * 100.0

    bonuses: list[str] = []
    title_forms = match_forms(job.title)
    targets = [str(t) for t in (profile.filters.get("target_title_keywords") or [])]
    hit = next((t for t in targets if contains_token(title_forms, t)), None)
    if hit:
        bonus = float(scoring.get("title_bonus", 8))
        base += bonus
        bonuses.append(f"직무 적합 제목 '{hit}' (+{bonus:g})")
    if mentions_newcomer(job):
        bonus = float(scoring.get("newcomer_bonus", 5))
        base += bonus
        bonuses.append(f"신입/주니어 명시 (+{bonus:g})")

    return MatchResult(
        job=job,
        score=round(max(0.0, min(100.0, base)), 1),
        requirement=req,
        preferred=pref,
        bonuses=bonuses,
        highlights=pick_highlights(job, profile),
    )

"""도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JobPosting:
    """수집한 공고 하나."""

    source: str
    job_id: str
    title: str
    company: str
    url: str
    location: str = ""
    posted_at: str = ""
    annual_from: int | None = None
    annual_to: int | None = None
    # JD 본문 섹션별 원문
    intro: str = ""
    main_tasks: str = ""
    requirements: str = ""
    preferred: str = ""
    benefits: str = ""
    raw_text: str = ""
    # "full" = JD 본문까지 확보, "summary" = 제목·직무키워드 등 요약 정보만
    detail_level: str = "full"
    tags: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.job_id}"

    def full_text(self) -> str:
        parts = [
            self.title,
            self.intro,
            self.main_tasks,
            self.requirements,
            self.preferred,
            self.benefits,
            self.raw_text,
        ]
        return "\n".join(p for p in parts if p)


@dataclass
class SectionScore:
    """한 섹션(자격요건 또는 우대사항)의 충족도."""

    name: str
    ratio: float                      # 0.0 ~ 1.0
    available: bool = True            # 해당 섹션 텍스트가 공고에 있었는지
    matched: list[str] = field(default_factory=list)   # 충족한 역량 label
    missing: list[str] = field(default_factory=list)   # 부족한 역량 label
    partial: list[str] = field(default_factory=list)   # 레벨이 낮아 부분 점수인 역량
    inferred: bool = False            # 텍스트는 있으나 아는 역량을 못 찾아 중립값을 쓴 경우


@dataclass
class MatchResult:
    """공고 하나에 대한 매칭 결과."""

    job: JobPosting
    score: float                      # 0 ~ 100
    requirement: SectionScore
    preferred: SectionScore
    bonuses: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)   # 어필할 내 포트폴리오

    @property
    def passed_threshold(self) -> bool:  # pragma: no cover - 호출부에서 비교
        return True

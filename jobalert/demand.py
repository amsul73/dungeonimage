"""직무 요구 역량 빈도 분석.

matcher 가 "이 공고가 나에게 맞는가"를 보는 반면, 여기서는 방향을 뒤집어
"이 직무는 보통 무엇을 요구하는가"를 공고 묶음 전체에서 집계한다.

산출물 4가지:
  1. 공통 요구 역량 — 등장률(몇 %의 공고에 나오는가)과 필수 비중(자격요건에 나온 비율)
  2. 내가 비어 있는 고빈도 역량 — 등장률 x 중요도 x 결핍도 로 우선순위를 매긴 목록
  3. 근거 문장 — 그 역량을 공고가 실제로 어떻게 요구했는지 원문 그대로
  4. 사전 미등록 빈출 표현 — keywords.yaml 에 아직 없는데 자주 나오는 말
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .config import Profile
from .models import JobPosting
from .text import contains_token, match_forms, normalize_loose, strip_html

# 집계 대상 섹션 (필드명, 표시명)
SECTIONS: tuple[tuple[str, str], ...] = (
    ("requirements", "자격요건"),
    ("preferred", "우대사항"),
    ("main_tasks", "주요업무"),
)

MAX_EVIDENCE = 3            # 역량 하나당 보관할 근거 문장 수
EVIDENCE_MAX_CHARS = 160
_WORD = re.compile(r"[0-9a-z가-힣]+")
_BULLET = re.compile(r"^[\s\-•·*▪●◦o·•\d.)\]]+")

# n-gram 마이닝에서 버릴 말 — JD에 흔하지만 역량이 아닌 단어들
STOPWORDS = frozenset(
    """
    경험 경력 능력 역량 우대 사항 자격 요건 필수 조건 업무 주요 담당 내용 이상 이하 가능 관련
    대한 대해 통해 함께 있는 있으신 있으면 있다면 하는 하실 하고 또는 그리고 및 등 이런 저런
    우리 저희 회사 조직 팀 팀원 분 사람 인재 지원 채용 전형 절차 복지 혜택 근무 신입 주니어
    좋아요 찾아요 원해요 수 것 때 중 더 잘 안 년 개월 이해 지식 활용 사용 작성 수행 진행 보유
    필요 중심 기반 다양한 새로운 적극적 원활 원활한 꼼꼼 책임감 열정 역할 기회 성장 문화 소개
    아래 위 모든 각 해당 이를 또 즉 정도 이용 기본 전반 과정 결과 내외 여부 경우 관리
    and or the a an to of in with for you we your our us is are be on as at by will have has
    who that this able strong plus about from able work working job role team
    """.split()
)


@dataclass
class KeywordDemand:
    """역량 하나가 공고 묶음에서 얼마나 요구되었는지."""

    keyword_id: str
    label: str
    weight: float
    my_level: int = 0
    postings: int = 0        # 이 역량이 등장한 공고 수
    required: int = 0        # 그중 자격요건 섹션에 등장한 공고 수
    preferred: int = 0       # 우대사항에 등장한 공고 수
    tasks: int = 0           # 주요업무에 등장한 공고 수
    evidence: list[str] = field(default_factory=list)

    def coverage(self, analyzed: int) -> float:
        """등장률 0.0~1.0."""
        return self.postings / analyzed if analyzed else 0.0

    @property
    def essential_ratio(self) -> float:
        """등장한 공고 중 '우대'가 아니라 '자격요건'으로 요구한 비율."""
        return self.required / self.postings if self.postings else 0.0

    def add_evidence(self, line: str) -> None:
        line = line.strip()
        if not line or len(self.evidence) >= MAX_EVIDENCE or line in self.evidence:
            return
        if len(line) > EVIDENCE_MAX_CHARS:
            line = line[:EVIDENCE_MAX_CHARS].rstrip() + "…"
        self.evidence.append(line)


@dataclass
class Gap:
    """자주 요구되는데 내가 못 채우는 역량."""

    demand: KeywordDemand
    gap_factor: float        # 1.0 = 전혀 없음, 0에 가까울수록 이미 보유
    # 등장률 x 중요도(weight) x 필수가중 x 결핍도. 절대값이 아니라 항목 간 비교용 상대 점수다.
    priority: float


@dataclass
class DemandReport:
    analyzed: int = 0                 # JD 전문을 확보해 집계에 쓴 공고 수
    summary_only: int = 0             # 본문이 없어 집계에서 빠진 공고 수
    total_collected: int = 0
    demands: list[KeywordDemand] = field(default_factory=list)   # 등장률 내림차순
    gaps: list[Gap] = field(default_factory=list)                # 우선순위 내림차순
    strengths: list[KeywordDemand] = field(default_factory=list)  # 고빈도 + 이미 보유
    unknown_phrases: list[tuple[str, int]] = field(default_factory=list)
    tag_counts: list[tuple[str, int]] = field(default_factory=list)  # 요약 공고의 직무 태그
    sources: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    def coverage_of(self, keyword_id: str) -> float:
        for demand in self.demands:
            if demand.keyword_id == keyword_id:
                return demand.coverage(self.analyzed)
        return 0.0


# ── 집계 ────────────────────────────────────────────────────────────────────

def _gap_factor(profile: Profile, keyword_id: str) -> float:
    """0.0(이미 충분) ~ 1.0(전혀 없음). matcher 와 같은 레벨 환산표를 뒤집어 쓴다."""
    table = profile.scoring.get("partial_level_factor") or {}
    level = profile.level_of(keyword_id)
    if level <= 0:
        return 1.0
    try:
        held = float(table.get(level, table.get(str(level), 1.0)))
    except (TypeError, ValueError):
        held = 1.0
    return max(0.0, min(1.0, 1.0 - held))


def _lines(text: str) -> list[str]:
    """JD 섹션을 문장/불릿 단위로 쪼갠다."""
    out: list[str] = []
    for raw in strip_html(text).replace("\r", "\n").split("\n"):
        for chunk in re.split(r"(?<=[.!?。])\s+", raw):
            cleaned = _BULLET.sub("", chunk).strip()
            if len(cleaned) >= 4:
                out.append(cleaned)
    return out


def _is_analyzable(job: JobPosting) -> bool:
    """JD 본문을 확보한 공고인지. 요약 소스(태그만 있는 공고)는 빈도를 왜곡한다."""
    if job.detail_level != "full":
        return False
    return any(getattr(job, field_name, "").strip() for field_name, _ in SECTIONS)


def analyze(
    postings: list[JobPosting],
    profile: Profile,
    *,
    include_summary: bool = False,
    min_phrase_df: int | None = None,
) -> DemandReport:
    """공고 묶음에서 요구 역량 빈도를 집계한다."""
    report = DemandReport(total_collected=len(postings))
    covered = _covered_forms(profile)
    table: dict[str, KeywordDemand] = {}
    phrase_docs: Counter[str] = Counter()
    tags: Counter[str] = Counter()

    for job in postings:
        report.sources[job.source] += 1
        if not (_is_analyzable(job) or (include_summary and job.full_text().strip())):
            report.summary_only += 1
            for tag in job.tags:
                tags[tag] += 1
            continue
        report.analyzed += 1
        for tag in job.tags:
            tags[tag] += 1

        hit_in_job: set[str] = set()
        for field_name, _label in SECTIONS:
            text = getattr(job, field_name, "") or ""
            if not text.strip():
                continue
            found = profile.dictionary.extract(text)
            if not found:
                continue
            section_lines = _lines(text)
            for keyword in found:
                demand = table.get(keyword.id)
                if demand is None:
                    demand = KeywordDemand(
                        keyword_id=keyword.id,
                        label=keyword.label,
                        weight=keyword.weight,
                        my_level=profile.level_of(keyword.id),
                    )
                    table[keyword.id] = demand
                if keyword.id not in hit_in_job:
                    demand.postings += 1
                    hit_in_job.add(keyword.id)
                if field_name == "requirements":
                    demand.required += 1
                elif field_name == "preferred":
                    demand.preferred += 1
                else:
                    demand.tasks += 1
                # 자격요건/우대사항의 문장을 근거로 남긴다 (주요업무는 보조)
                for line in section_lines:
                    forms = match_forms(line)
                    if any(contains_token(forms, token) for token in keyword.all_tokens()):
                        demand.add_evidence(line)
                        break

        for phrase in _mine_phrases(job, covered):
            phrase_docs[phrase] += 1

    report.demands = sorted(
        table.values(),
        key=lambda d: (d.postings, d.weight, d.required),
        reverse=True,
    )

    gaps: list[Gap] = []
    strengths: list[KeywordDemand] = []
    for demand in report.demands:
        coverage = demand.coverage(report.analyzed)
        factor = _gap_factor(profile, demand.keyword_id)
        if factor <= 0.0:
            strengths.append(demand)
            continue
        # 자격요건으로 요구될수록 최대 2배까지 가중
        priority = coverage * demand.weight * (1.0 + demand.essential_ratio) * factor * 100.0
        gaps.append(Gap(demand=demand, gap_factor=factor, priority=round(priority, 1)))
    gaps.sort(key=lambda g: g.priority, reverse=True)
    report.gaps = gaps
    report.strengths = strengths

    threshold = min_phrase_df if min_phrase_df is not None else max(2, round(report.analyzed * 0.1))
    report.unknown_phrases = [
        (phrase, count)
        for phrase, count in phrase_docs.most_common(200)
        if count >= threshold
    ][:40]
    report.tag_counts = tags.most_common(25)
    return report


# ── 사전 미등록 표현 마이닝 ──────────────────────────────────────────────────

def _covered_forms(profile: Profile) -> list[str]:
    forms: set[str] = set()
    for keyword in profile.dictionary.keywords:
        for token in keyword.all_tokens():
            normalized = normalize_loose(token)
            if normalized:
                forms.add(normalized)
    return sorted(forms, key=len, reverse=True)


def _mine_phrases(job: JobPosting, covered: list[str]) -> set[str]:
    """공고 하나에 등장한, 사전에 없는 1~3그램 집합(문서빈도 집계용)."""
    phrases: set[str] = set()
    for field_name in ("requirements", "preferred"):
        text = getattr(job, field_name, "") or ""
        for line in _lines(text):
            tokens = [t for t in _WORD.findall(normalize_loose(line)) if len(t) > 1]
            for size in (1, 2, 3):
                for index in range(len(tokens) - size + 1):
                    window = _trim_stopwords(tokens[index : index + size])
                    if not window or any(token.isdigit() for token in window):
                        continue
                    phrase = " ".join(window)
                    if _already_covered(phrase, covered):
                        continue
                    phrases.add(phrase)
    return phrases


def _trim_stopwords(window: list[str]) -> list[str]:
    """n-gram 양끝의 범용어를 잘라낸다.

    '설계 경험' 처럼 뒤에 '경험/능력/가능' 이 붙은 표현은 역량 이름이 아니라
    서술이므로, 끝을 잘라 '설계' 로 만든 뒤 사전 포함 여부를 다시 본다.
    """
    start, end = 0, len(window)
    while start < end and window[start] in STOPWORDS:
        start += 1
    while end > start and window[end - 1] in STOPWORDS:
        end -= 1
    return window[start:end]


def _already_covered(phrase: str, covered: list[str]) -> bool:
    """사전의 어떤 표기와 겹치면(포함하거나 포함되면) 새 표현이 아니다."""
    for form in covered:
        if phrase == form or phrase in form or form in phrase:
            return True
    return False


# ── 출력 ────────────────────────────────────────────────────────────────────

def _bar(ratio: float, width: int = 12) -> str:
    filled = int(round(max(0.0, min(1.0, ratio)) * width))
    return "█" * filled + "·" * (width - filled)


def to_text(report: DemandReport, profile: Profile, *, top: int = 25) -> str:
    role = profile.me.get("target_role") or "(직무 미지정)"
    lines = [
        f"■ 요구 역량 스캔 — {role}",
        f"  수집 {report.total_collected}건 중 JD 본문 확보 {report.analyzed}건"
        f" (본문 없음 {report.summary_only}건)",
    ]
    if report.sources:
        lines.append("  소스: " + ", ".join(f"{k} {v}건" for k, v in report.sources.items()))
    if report.analyzed == 0:
        lines.append("")
        lines.append("  JD 본문이 있는 공고가 없어 빈도를 낼 수 없습니다.")
        lines.append("  관심 공고 본문을 jd/ 폴더에 .txt 로 저장한 뒤 --jd-dir jd 로 다시 실행하세요.")
        return "\n".join(lines)
    if report.analyzed < 10:
        lines.append(f"  ※ 표본 {report.analyzed}건은 적습니다. 30건 이상이면 빈도가 안정됩니다.")

    lines += ["", "── 공통 요구 역량 (등장률 순) ────────────────────────────────"]
    lines.append("  등장률  필수  내레벨  역량")
    for demand in report.demands[:top]:
        coverage = demand.coverage(report.analyzed)
        lines.append(
            f"  {coverage * 100:4.0f}%  {_bar(coverage)}  "
            f"{demand.essential_ratio * 100:3.0f}%  "
            f"{demand.my_level if demand.my_level else '-':>3}  {demand.label}"
        )

    lines += ["", "── 내가 비어 있는 고빈도 역량 (채울 우선순위) ────────────────"]
    if not report.gaps:
        lines.append("  비어 있는 고빈도 역량이 없습니다.")
    for index, gap in enumerate(report.gaps[:10], start=1):
        demand = gap.demand
        held = f"내 레벨 {demand.my_level}" if demand.my_level else "미보유"
        lines.append(
            f"  {index}. {demand.label}  "
            f"[우선순위 {gap.priority:g}]  "
            f"등장률 {demand.coverage(report.analyzed) * 100:.0f}% / "
            f"필수 {demand.essential_ratio * 100:.0f}% / {held}"
        )
        for evidence in demand.evidence:
            lines.append(f"       └ \"{evidence}\"")

    if report.strengths:
        lines += ["", "── 이미 가진 고빈도 역량 (이력서에서 앞에 두세요) ────────────"]
        for demand in report.strengths[:10]:
            lines.append(
                f"  · {demand.label} — 등장률 {demand.coverage(report.analyzed) * 100:.0f}% "
                f"(내 레벨 {demand.my_level})"
            )

    if report.unknown_phrases:
        lines += ["", "── 사전에 없는 빈출 표현 (keywords.yaml 보강 후보) ───────────"]
        chunk = ", ".join(f"{phrase}({count})" for phrase, count in report.unknown_phrases[:30])
        lines.append("  " + chunk)

    if report.tag_counts and report.summary_only:
        lines += ["", "── 요약 공고의 직무 태그 빈도 (참고) ────────────────────────"]
        lines.append("  " + ", ".join(f"{tag}({count})" for tag, count in report.tag_counts[:15]))

    for error in report.errors:
        lines.append(f"[오류] {error}")
    return "\n".join(lines)


def to_markdown(report: DemandReport, profile: Profile, *, top: int = 40) -> str:
    role = profile.me.get("target_role") or "(직무 미지정)"
    out = [
        f"# 요구 역량 스캔 — {role}",
        "",
        f"- 수집 공고: **{report.total_collected}건**",
        f"- JD 본문 확보(집계 대상): **{report.analyzed}건**",
        f"- 본문 없음(집계 제외): {report.summary_only}건",
    ]
    if report.sources:
        out.append("- 소스: " + ", ".join(f"{k} {v}건" for k, v in report.sources.items()))
    if report.analyzed == 0:
        out += ["", "> JD 본문이 있는 공고가 없어 빈도를 낼 수 없습니다."]
        return "\n".join(out) + "\n"

    out += [
        "",
        "## 1. 공통 요구 역량",
        "",
        "`등장률` = 집계 대상 공고 중 이 역량을 언급한 비율 · "
        "`필수 비중` = 그중 우대가 아니라 자격요건으로 요구한 비율",
        "",
        "| 역량 | 등장률 | 필수 비중 | 자격요건 | 우대사항 | 주요업무 | 내 레벨 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for demand in report.demands[:top]:
        out.append(
            f"| {demand.label} | {demand.coverage(report.analyzed) * 100:.0f}% "
            f"| {demand.essential_ratio * 100:.0f}% | {demand.required} "
            f"| {demand.preferred} | {demand.tasks} | {demand.my_level or '-'} |"
        )

    out += ["", "## 2. 채울 우선순위 (고빈도 x 미보유)", ""]
    if not report.gaps:
        out.append("비어 있는 고빈도 역량이 없습니다.")
    for index, gap in enumerate(report.gaps[:15], start=1):
        demand = gap.demand
        held = f"내 레벨 {demand.my_level}" if demand.my_level else "미보유"
        out.append(
            f"### {index}. {demand.label} — 우선순위 {gap.priority:g}"
        )
        out.append("")
        out.append(
            f"등장률 {demand.coverage(report.analyzed) * 100:.0f}% · "
            f"필수 비중 {demand.essential_ratio * 100:.0f}% · {held}"
        )
        if demand.evidence:
            out.append("")
            out.append("공고 원문이 요구한 방식:")
            out.append("")
            for evidence in demand.evidence:
                out.append(f"> {evidence}")
                out.append("")
        out.append("")

    if report.strengths:
        out += ["## 3. 이미 가진 고빈도 역량", "", "| 역량 | 등장률 | 내 레벨 |", "| --- | ---: | ---: |"]
        for demand in report.strengths[:20]:
            out.append(
                f"| {demand.label} | {demand.coverage(report.analyzed) * 100:.0f}% | {demand.my_level} |"
            )
        out.append("")

    if report.unknown_phrases:
        out += [
            "## 4. 사전 미등록 빈출 표현",
            "",
            "`keywords.yaml` 에 추가할 만한 후보입니다 (괄호 = 등장 공고 수).",
            "",
        ]
        out.append(", ".join(f"`{phrase}`({count})" for phrase, count in report.unknown_phrases))
        out.append("")

    if report.tag_counts and report.summary_only:
        out += ["## 5. 요약 공고 직무 태그 빈도 (참고)", ""]
        out.append(", ".join(f"`{tag}`({count})" for tag, count in report.tag_counts))
        out.append("")
    return "\n".join(out) + "\n"


def to_dict(report: DemandReport, profile: Profile) -> dict:
    return {
        "target_role": profile.me.get("target_role") or "",
        "total_collected": report.total_collected,
        "analyzed": report.analyzed,
        "summary_only": report.summary_only,
        "sources": dict(report.sources),
        "demands": [
            {
                "id": d.keyword_id,
                "label": d.label,
                "weight": d.weight,
                "coverage": round(d.coverage(report.analyzed), 4),
                "postings": d.postings,
                "required": d.required,
                "preferred": d.preferred,
                "main_tasks": d.tasks,
                "essential_ratio": round(d.essential_ratio, 4),
                "my_level": d.my_level,
                "evidence": d.evidence,
            }
            for d in report.demands
        ],
        "gaps": [
            {
                "id": g.demand.keyword_id,
                "label": g.demand.label,
                "priority": g.priority,
                "coverage": round(g.demand.coverage(report.analyzed), 4),
                "essential_ratio": round(g.demand.essential_ratio, 4),
                "my_level": g.demand.my_level,
                "evidence": g.demand.evidence,
            }
            for g in report.gaps
        ],
        "strengths": [
            {
                "id": d.keyword_id,
                "label": d.label,
                "coverage": round(d.coverage(report.analyzed), 4),
                "my_level": d.my_level,
            }
            for d in report.strengths
        ],
        "unknown_phrases": [{"phrase": p, "postings": c} for p, c in report.unknown_phrases],
        "tags": [{"tag": t, "postings": c} for t, c in report.tag_counts],
        "errors": report.errors,
    }

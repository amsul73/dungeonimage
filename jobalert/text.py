"""JD 텍스트 정규화와 섹션 분리."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^0-9a-z가-힣]+")
_TAG = re.compile(r"<[^>]+>")

# 섹션 헤더 표기 → 정규화된 섹션 이름
SECTION_HEADERS: dict[str, tuple[str, ...]] = {
    "requirements": (
        "자격요건", "자격 요건", "지원자격", "지원 자격", "필수요건", "필수 요건",
        "필수역량", "필수 역량", "필수조건", "자격조건", "이런 분을 찾아요",
        "이런 분과 함께하고 싶어요", "이런분을 찾습니다", "required", "requirements",
        "qualification", "qualifications", "경력 및 자격요건",
    ),
    "preferred": (
        "우대사항", "우대 사항", "우대조건", "우대 조건", "우대요건", "우대역량",
        "이런 경험이 있다면", "이런 경험이 있으면", "이런 분이면 더 좋아요",
        "이런 경험을 가진 분이라면", "더 좋아요", "preferred", "nice to have",
        "plus", "preferred qualifications", "있으면 좋은 경험",
    ),
    "main_tasks": (
        "주요업무", "주요 업무", "담당업무", "담당 업무", "업무내용", "업무 내용",
        "이런 일을 해요", "합류하면 함께할 업무", "responsibilities", "what you will do",
        "주요 역할", "job description",
    ),
    "benefits": (
        "혜택 및 복지", "복지", "혜택", "benefit", "benefits", "perks",
        "채용절차", "채용 절차", "전형절차", "전형 절차", "근무조건", "제출서류",
    ),
}


def strip_html(value: str) -> str:
    """태그를 공백으로 바꾸고 흔한 엔티티를 되돌린다."""
    if not value:
        return ""
    out = _TAG.sub(" ", value)
    for entity, char in (
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"),
    ):
        out = out.replace(entity, char)
    return out


def normalize(value: str) -> str:
    """소문자 + 공백 정리. 구두점은 보존(예: 'a/b 테스트')."""
    if not value:
        return ""
    out = unicodedata.normalize("NFKC", value).lower()
    out = out.replace("​", " ").replace("·", " ")
    return _WS.sub(" ", out).strip()


def normalize_loose(value: str) -> str:
    """구두점까지 공백으로 바꾼 형태 ('ux/ui' → 'ux ui')."""
    return _WS.sub(" ", _PUNCT.sub(" ", normalize(value))).strip()


def match_forms(value: str) -> tuple[str, str]:
    """부분일치 검사용 두 가지 형태를 앞뒤 공백과 함께 반환."""
    return f" {normalize(value)} ", f" {normalize_loose(value)} "


def contains_token(haystacks: tuple[str, str], needle: str) -> bool:
    """needle(표기)이 본문에 있는지 검사. 앞뒤 공백이 있는 표기는 단어 경계를 요구."""
    strict, loose = haystacks
    raw = needle.lower()
    padded = raw.startswith(" ") or raw.endswith(" ")
    n_strict = normalize(needle)
    n_loose = normalize_loose(needle)
    if padded:
        return f" {n_strict} " in strict or f" {n_loose} " in loose
    return n_strict in strict or (bool(n_loose) and n_loose in loose)


def _header_lookup() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for section, headers in SECTION_HEADERS.items():
        for header in headers:
            pairs.append((normalize_loose(header), section))
    # 긴 헤더부터 검사해야 '우대사항'이 '우대'보다 먼저 잡힌다
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


_HEADERS = _header_lookup()


def _header_of(line: str) -> str | None:
    """줄이 섹션 헤더처럼 보이면 섹션 이름을 돌려준다."""
    probe = normalize_loose(line)
    if not probe or len(probe) > 40:
        return None
    for header, section in _HEADERS:
        if not header:
            continue
        if probe == header or probe.startswith(header) or probe.endswith(header):
            return section
    return None


def split_sections(text: str) -> dict[str, str]:
    """자유 형식 JD 본문을 섹션별로 쪼갠다.

    원티드처럼 섹션이 필드로 분리된 소스에서는 쓰이지 않고,
    붙여넣은 JD(`score` 명령)나 섹션이 한 덩어리로 오는 소스에서 쓰인다.
    """
    sections: dict[str, list[str]] = {}
    current = "intro"
    for line in strip_html(text).splitlines():
        header = _header_of(line)
        if header:
            current = header
            continue
        if line.strip():
            sections.setdefault(current, []).append(line.strip())
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}

"""로컬에 저장해 둔 JD 텍스트 파일을 공고로 읽어들인다.

사람인 공개 API 는 JD 본문(자격요건·우대사항 전문)을 주지 않는다.
요구 역량 빈도를 내려면 본문이 필요하므로, 관심 공고 본문을 복사해
`jd/` 폴더에 텍스트 파일로 모아두고 이 모듈로 읽는다.

파일 이름 규칙 (선택):
    회사명_직무명.txt  →  company="회사명", title="직무명"
    아무이름.txt       →  title="아무이름"
확장자는 .txt / .md / .text 를 읽는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .models import JobPosting
from .text import split_sections

EXTENSIONS = (".txt", ".md", ".text")


def _title_and_company(stem: str) -> tuple[str, str]:
    """'토스_서비스기획자' → ('서비스기획자', '토스')."""
    if "_" in stem:
        company, _, title = stem.partition("_")
        company, title = company.strip(), title.strip()
        if company and title:
            return title, company
    return stem.strip() or "(제목 없음)", "(회사 미기재)"


def load_file(path: str | Path) -> JobPosting:
    """JD 텍스트 파일 하나를 공고로 변환."""
    file = Path(path)
    raw = file.read_text(encoding="utf-8", errors="replace")
    sections = split_sections(raw)
    title, company = _title_and_company(file.stem)
    return JobPosting(
        source="jdfile",
        job_id=file.stem,
        title=title,
        company=company,
        url=str(file),
        intro=sections.get("intro", ""),
        main_tasks=sections.get("main_tasks", ""),
        requirements=sections.get("requirements", ""),
        preferred=sections.get("preferred", ""),
        benefits=sections.get("benefits", ""),
        detail_level="full",
    )


def iter_dir(directory: str | Path) -> Iterator[JobPosting]:
    """폴더 안의 JD 파일을 모두 읽는다(하위 폴더 포함, 이름 순)."""
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"JD 폴더가 없습니다: {root}")
    if root.is_file():
        yield load_file(root)
        return
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in EXTENSIONS and not path.name.startswith(".")
        and path.name.lower() != "readme.md"
    )
    for path in files:
        yield load_file(path)


def load_dir(directory: str | Path) -> list[JobPosting]:
    return list(iter_dir(directory))

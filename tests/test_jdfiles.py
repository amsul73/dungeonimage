"""로컬 JD 텍스트 파일 로더 테스트."""

from __future__ import annotations

import pytest

from jobalert import jdfiles

SAMPLE = """주요 업무
- 지표를 정의하고 퍼널을 분석합니다

자격 요건
- SQL 활용 가능

우대 사항
- A/B 테스트 경험
"""


def test_파일_하나를_섹션별로_읽는다(tmp_path):
    path = tmp_path / "토스_프로덕트오너.txt"
    path.write_text(SAMPLE, encoding="utf-8")

    job = jdfiles.load_file(path)

    assert (job.title, job.company) == ("프로덕트오너", "토스")
    assert job.detail_level == "full"
    assert "SQL" in job.requirements
    assert "A/B 테스트" in job.preferred
    assert "퍼널" in job.main_tasks


def test_밑줄이_없는_파일명은_전체를_제목으로_쓴다(tmp_path):
    path = tmp_path / "어딘가의공고.txt"
    path.write_text(SAMPLE, encoding="utf-8")

    job = jdfiles.load_file(path)

    assert job.title == "어딘가의공고"
    assert job.company == "(회사 미기재)"


def test_폴더를_읽을_때_readme_와_다른_확장자는_건너뛴다(tmp_path):
    (tmp_path / "A_기획자.txt").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "B_PM.md").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "README.md").write_text("설명 문서", encoding="utf-8")
    (tmp_path / "메모.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".숨김.txt").write_text(SAMPLE, encoding="utf-8")

    jobs = jdfiles.load_dir(tmp_path)

    assert sorted(job.job_id for job in jobs) == ["A_기획자", "B_PM"]


def test_하위_폴더까지_읽는다(tmp_path):
    nested = tmp_path / "2026" / "1월"
    nested.mkdir(parents=True)
    (nested / "C_PO.txt").write_text(SAMPLE, encoding="utf-8")

    assert [job.job_id for job in jdfiles.load_dir(tmp_path)] == ["C_PO"]


def test_없는_폴더는_분명한_오류를_낸다(tmp_path):
    with pytest.raises(FileNotFoundError):
        jdfiles.load_dir(tmp_path / "없음")

import json
from pathlib import Path

from jobalert import render
from jobalert.cli import main
from jobalert.models import JobPosting
from jobalert.pipeline import evaluate
from jobalert.store import SeenStore

FIXTURE = Path(__file__).parent / "fixtures" / "sample_jobs.json"


def load_fixture() -> list[JobPosting]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fields = JobPosting.__dataclass_fields__.keys()
    return [JobPosting(**{k: v for k, v in item.items() if k in fields}) for item in data["jobs"]]


def test_evaluate_splits_jobs_into_buckets(profile, tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    report = evaluate(load_fixture(), profile, store)

    assert report.collected == 5
    reasons = {r.job.job_id: r.reason for r in report.rejected}
    assert "1002" in reasons and "시니어" in reasons["1002"]     # 시니어 공고
    assert "1003" in reasons and "서울" in reasons["1003"]        # 분당
    assert "1005" in reasons                                      # 개발자 공고
    assert [m.job.job_id for m in report.matches] == ["1001"]
    assert [r.job.job_id for r in report.below_threshold] == ["1004"]


def test_matches_sorted_by_score_desc(profile, tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    profile.raw["notify"]["threshold"] = 0
    report = evaluate(load_fixture(), profile, store)
    scores = [m.score for m in report.matches]
    assert scores == sorted(scores, reverse=True)


def test_seen_jobs_are_not_renotified(profile, tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    store.mark("fixture:1001", score=100)
    report = evaluate(load_fixture(), profile, store)
    assert not report.matches
    assert [m.job.job_id for m in report.already_seen] == ["1001"]


def test_cli_run_with_fixture_is_idempotent(tmp_path, capsys):
    state = tmp_path / "seen.json"
    args = [
        "run", "--fixture", str(FIXTURE), "--notifier", "console", "--state", str(state),
    ]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert "새 알림 1건" in first

    assert main(args) == 0
    second = capsys.readouterr().out
    assert "새 알림 0건" in second
    assert "이미 알림 1건" in second


def test_cli_dry_run_does_not_write_state(tmp_path, capsys):
    state = tmp_path / "seen.json"
    main(["run", "--fixture", str(FIXTURE), "--notifier", "console",
          "--state", str(state), "--dry-run"])
    capsys.readouterr()
    assert not state.exists()


def test_cli_threshold_override_changes_matches(tmp_path, capsys):
    state = tmp_path / "seen.json"
    main(["run", "--fixture", str(FIXTURE), "--notifier", "console",
          "--state", str(state), "--dry-run", "--threshold", "30"])
    out = capsys.readouterr().out
    assert "새 알림 2건" in out


def test_cli_score_reads_stdin(monkeypatch, capsys):
    jd = """자격요건
- 요구사항 정의서 작성 경험
- 피그마 활용 가능
우대사항
- SQL 활용 경험
"""
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(jd))
    assert main(["score", "-", "--title", "서비스 기획자"]) == 0
    out = capsys.readouterr().out
    assert "총점" in out and "자격요건 100%" in out


def test_render_html_contains_links_and_scores(profile, tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    report = evaluate(load_fixture(), profile, store)
    html = render.to_html(report.matches, profile)
    assert "https://www.wanted.co.kr/wd/1001" in html
    assert "100점" in html
    assert "오픈마켓 스타트업" in html


def test_render_escapes_html_in_job_fields(profile):
    from jobalert.matcher import score_job

    job = JobPosting(
        source="t", job_id="x", title="<script>alert(1)</script> 기획자",
        company="A & B", url="https://example.com", location="서울",
        requirements="피그마",
    )
    html = render.to_html([score_job(job, profile)], profile)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "A &amp; B" in html


def test_subject_mentions_top_job(profile, tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    profile.raw["notify"]["threshold"] = 0
    report = evaluate(load_fixture(), profile, store)
    subject = render.subject(report.matches, profile)
    assert "기획 공고 알림" in subject
    assert "외" in subject

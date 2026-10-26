"""수집 → 필터 → 점수 → 알림 파이프라인."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Profile
from .matcher import Rejection, check_filters, score_job
from .models import JobPosting, MatchResult
from .sources import build_sources
from .store import SeenStore


@dataclass
class RunReport:
    collected: int = 0
    rejected: list[Rejection] = field(default_factory=list)
    below_threshold: list[MatchResult] = field(default_factory=list)
    already_seen: list[MatchResult] = field(default_factory=list)
    matches: list[MatchResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"수집 {self.collected}건 / 필터 제외 {len(self.rejected)}건 / "
            f"점수 미달 {len(self.below_threshold)}건 / 이미 알림 {len(self.already_seen)}건 / "
            f"새 알림 {len(self.matches)}건"
        )


def collect(profile: Profile, source_names: list[str]) -> tuple[list[JobPosting], list[str]]:
    postings: list[JobPosting] = []
    errors: list[str] = []
    for source in build_sources(source_names, profile.search):
        try:
            postings.extend(source.fetch())
        except Exception as error:  # 한 소스가 죽어도 나머지는 진행
            errors.append(f"{getattr(source, 'name', source)}: {error}")
    return postings, errors


def evaluate(
    postings: list[JobPosting],
    profile: Profile,
    store: SeenStore | None = None,
) -> RunReport:
    report = RunReport(collected=len(postings))
    threshold = profile.threshold
    for job in postings:
        reason = check_filters(job, profile)
        if reason:
            report.rejected.append(Rejection(job=job, reason=reason))
            continue
        result = score_job(job, profile)
        if result.score < threshold:
            report.below_threshold.append(result)
            continue
        if store is not None and store.is_seen(job.key):
            report.already_seen.append(result)
            continue
        report.matches.append(result)
    report.matches.sort(key=lambda item: item.score, reverse=True)
    report.below_threshold.sort(key=lambda item: item.score, reverse=True)
    return report


def run(
    profile: Profile,
    *,
    source_names: list[str],
    store: SeenStore,
    notifier=None,
    dry_run: bool = False,
) -> RunReport:
    postings, errors = collect(profile, source_names)
    report = evaluate(postings, profile, store)
    report.errors.extend(errors)

    if not report.matches:
        return report

    from . import render  # 지연 import: 렌더링은 알릴 게 있을 때만 필요

    limit = int(profile.notify.get("max_jobs_per_mail", 10))
    picked = report.matches[:limit]
    subject = render.subject(picked, profile)
    text = render.to_text(picked, profile)
    html = render.to_html(picked, profile)

    if notifier is not None:
        notifier.send(subject, text, html)

    if not dry_run:
        for result in picked:
            store.mark(
                result.job.key,
                score=result.score,
                title=result.job.title,
                company=result.job.company,
                url=result.job.url,
            )
        store.prune()
        store.save()
    return report

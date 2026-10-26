"""알림 본문 렌더링 (메일 HTML / 콘솔 텍스트)."""

from __future__ import annotations

import html

from .config import Profile
from .models import MatchResult
from .store import now_kst


def subject(results: list[MatchResult], profile: Profile) -> str:
    prefix = str(profile.notify.get("subject_prefix") or "[기획 공고 알림]")
    date = now_kst().strftime("%m/%d")
    if not results:
        return f"{prefix} {date} 새 공고 없음"
    top = results[0]
    extra = f" 외 {len(results) - 1}건" if len(results) > 1 else ""
    return f"{prefix} {date} {top.job.company} {top.job.title} {top.score:g}점{extra}"


def _section_lines(result: MatchResult) -> list[str]:
    lines = []
    for section in (result.requirement, result.preferred):
        if section.inferred:
            lines.append(f"{section.name}: 본문에서 항목을 찾지 못해 중립 처리 ({section.ratio * 100:.0f}%)")
            continue
        detail = []
        if section.matched:
            detail.append("충족 " + ", ".join(section.matched))
        if section.partial:
            detail.append("부분 " + ", ".join(section.partial))
        if section.missing:
            detail.append("부족 " + ", ".join(section.missing))
        lines.append(f"{section.name} {section.ratio * 100:.0f}% — " + " / ".join(detail))
    return lines


def to_text(results: list[MatchResult], profile: Profile) -> str:
    out = [f"매칭 점수 {profile.threshold:g}점 이상 공고 {len(results)}건", ""]
    for index, result in enumerate(results, start=1):
        job = result.job
        out.append(f"{index}. [{result.score:g}점] {job.company} — {job.title}")
        out.append(f"   {job.url}")
        if job.location:
            out.append(f"   근무지: {job.location}")
        for line in _section_lines(result):
            out.append(f"   {line}")
        for bonus in result.bonuses:
            out.append(f"   가점: {bonus}")
        for highlight in result.highlights:
            out.append(f"   어필 포인트: {highlight}")
        out.append("")
    return "\n".join(out)


def _bar(ratio: float) -> str:
    width = max(0, min(100, round(ratio * 100)))
    return (
        '<div style="background:#eceff3;border-radius:6px;height:8px;width:160px;display:inline-block;'
        'vertical-align:middle;overflow:hidden">'
        f'<div style="background:#2f6fed;height:8px;width:{width}%"></div></div>'
    )


def _chips(labels: list[str], color: str, background: str) -> str:
    return "".join(
        f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;border-radius:10px;'
        f'font-size:12px;color:{color};background:{background}">{html.escape(label)}</span>'
        for label in labels
    )


def to_html(results: list[MatchResult], profile: Profile) -> str:
    name = html.escape(str(profile.me.get("name") or ""))
    stamp = now_kst().strftime("%Y-%m-%d %H:%M")
    cards: list[str] = []
    for result in results:
        job = result.job
        rows: list[str] = []
        for section in (result.requirement, result.preferred):
            if section.inferred:
                body = '<span style="color:#8a94a6;font-size:13px">본문에서 항목을 찾지 못해 중립 처리</span>'
            else:
                body = (
                    _chips(section.matched, "#0b6b3a", "#e3f5ea")
                    + _chips(section.partial, "#8a5a00", "#fdf0d5")
                    + _chips(section.missing, "#8a2b2b", "#fbe6e6")
                )
            rows.append(
                '<tr><td style="padding:6px 10px 6px 0;white-space:nowrap;color:#42506b;font-size:13px">'
                f"{html.escape(section.name)} <b>{section.ratio * 100:.0f}%</b></td>"
                f'<td style="padding:6px 0">{_bar(section.ratio)}</td></tr>'
                f'<tr><td colspan="2" style="padding:0 0 8px 0">{body}</td></tr>'
            )
        bonus = (
            '<div style="font-size:12px;color:#42506b;margin-top:6px">가점: '
            + html.escape(" · ".join(result.bonuses))
            + "</div>"
            if result.bonuses
            else ""
        )
        highlight = (
            '<div style="margin-top:10px;padding:10px 12px;background:#f5f7fb;border-radius:8px;font-size:13px;color:#2b3550">'
            "<b>이 공고엔 이 경험을 쓰세요</b><br>"
            + "<br>".join(html.escape(item) for item in result.highlights)
            + "</div>"
            if result.highlights
            else ""
        )
        location = (
            f'<span style="color:#8a94a6;font-size:13px"> · {html.escape(job.location)}</span>'
            if job.location
            else ""
        )
        cards.append(
            f"""
<div style="border:1px solid #e3e7ee;border-radius:12px;padding:16px;margin:0 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:baseline">
    <div style="font-size:16px;font-weight:700;color:#121826">{html.escape(job.title)}</div>
    <div style="font-size:18px;font-weight:700;color:#2f6fed">{result.score:g}점</div>
  </div>
  <div style="margin:2px 0 12px 0;color:#42506b;font-size:14px">{html.escape(job.company)}{location}</div>
  <table style="border-collapse:collapse;width:100%">{''.join(rows)}</table>
  {bonus}
  {highlight}
  <div style="margin-top:12px">
    <a href="{html.escape(job.url)}" style="display:inline-block;padding:8px 14px;background:#2f6fed;color:#fff;
       border-radius:8px;text-decoration:none;font-size:13px">공고 보기</a>
  </div>
</div>"""
        )

    return f"""<!doctype html>
<html lang="ko"><body style="margin:0;padding:24px;background:#f7f8fa;
  font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif">
<div style="max-width:640px;margin:0 auto">
  <div style="font-size:20px;font-weight:700;color:#121826">
    {name}님께 맞는 공고 {len(results)}건</div>
  <div style="color:#8a94a6;font-size:13px;margin:4px 0 18px 0">
    {stamp} 기준 · 매칭 {profile.threshold:g}점 이상 · 서울 · 신입</div>
  {''.join(cards)}
  <div style="color:#8a94a6;font-size:12px;margin-top:18px;line-height:1.6">
    점수는 profile.yaml 의 보유 역량과 공고의 자격요건·우대사항을 비교해 계산했습니다.
    기준을 바꾸려면 profile.yaml 의 <code>have</code> / <code>notify.threshold</code> 를 수정하세요.
  </div>
</div></body></html>"""

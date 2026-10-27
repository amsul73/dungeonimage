"""명령줄 인터페이스."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import demand as demand_mod
from . import render
from .config import DEFAULT_KEYWORDS, DEFAULT_PROFILE, DEFAULT_STATE, Profile, load_dotenv
from .matcher import check_filters, required_years, score_job
from .models import JobPosting
from .notifiers import build_notifier
from .pipeline import collect, evaluate, run
from .store import SeenStore
from .text import split_sections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobalert",
        description="이력서/포트폴리오 기반으로 채용공고를 수집·채점하고 알림을 보냅니다.",
    )
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE), help="profile.yaml 경로")
    parser.add_argument("--keywords", default=str(DEFAULT_KEYWORDS), help="keywords.yaml 경로")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="공고 수집 → 채점 → 알림")
    run_cmd.add_argument(
        "--source", action="append", default=None,
        help="수집기 (기본: profile.yaml 의 search.sources, 없으면 saramin)",
    )
    run_cmd.add_argument("--notifier", default="email", choices=["email", "console"])
    run_cmd.add_argument("--state", default=str(DEFAULT_STATE), help="알림 기록 파일")
    run_cmd.add_argument("--threshold", type=float, default=None, help="알림 최소 점수 덮어쓰기")
    run_cmd.add_argument("--dry-run", action="store_true", help="기록 저장 없이 결과만 확인")
    run_cmd.add_argument("--fixture", default=None, help="네트워크 대신 JSON 파일에서 공고 읽기")
    run_cmd.add_argument("--verbose", action="store_true", help="제외된 공고까지 출력")

    scan_cmd = sub.add_parser(
        "scan", help="공고 묶음을 훑어 직무가 공통적으로 요구하는 역량 빈도를 집계",
    )
    scan_cmd.add_argument(
        "--jd-dir", default=None,
        help="JD 본문 텍스트 파일 폴더 (예: jd). 빈도 분석은 본문이 있어야 의미가 있습니다",
    )
    scan_cmd.add_argument(
        "--source", action="append", default=None,
        help="추가로 수집할 소스 (기본: --jd-dir 만 주면 수집 생략)",
    )
    scan_cmd.add_argument("--fixture", default=None, help="네트워크 대신 JSON 파일에서 공고 읽기")
    scan_cmd.add_argument("--no-filters", action="store_true",
                          help="하드 필터(서울/경력)를 끄고 모든 공고를 집계")
    scan_cmd.add_argument("--include-summary", action="store_true",
                          help="JD 본문이 없는 요약 공고도 집계에 포함(빈도가 왜곡될 수 있음)")
    scan_cmd.add_argument("--top", type=int, default=25, help="콘솔에 출력할 역량 수")
    scan_cmd.add_argument("--min-phrase-df", type=int, default=None,
                          help="미등록 표현을 보고할 최소 등장 공고 수 (기본: 표본의 10%%)")
    scan_cmd.add_argument("--markdown", default=None, help="마크다운 리포트 저장 경로")
    scan_cmd.add_argument("--json", dest="json_out", default=None, help="JSON 저장 경로")

    score_cmd = sub.add_parser("score", help="붙여넣은 JD 텍스트 파일 하나를 채점")
    score_cmd.add_argument("path", help="JD 텍스트 파일 경로 ('-' 는 표준입력)")
    score_cmd.add_argument("--title", default="(제목 미입력)")
    score_cmd.add_argument("--company", default="(회사 미입력)")
    score_cmd.add_argument("--location", default="서울")

    probe_cmd = sub.add_parser("probe", help="채용 API 응답 구조를 눈으로 확인")
    probe_cmd.add_argument("--source", default="saramin", choices=["saramin", "wanted"])
    probe_cmd.add_argument("--job-id", default=None, help="상세 조회할 공고 id (원티드만)")
    probe_cmd.add_argument("--save", default=None, help="응답 JSON 저장 경로")

    sub.add_parser("profile", help="profile.yaml 파싱 결과 확인")
    sub.add_parser("test-mail", help="샘플 공고로 메일 발송 테스트")
    return parser


def _load_profile(args: argparse.Namespace) -> Profile:
    return Profile.load(args.profile, args.keywords)


def _postings_from_fixture(path: str) -> list[JobPosting]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["jobs"] if isinstance(data, dict) else data
    fields = JobPosting.__dataclass_fields__.keys()
    return [JobPosting(**{k: v for k, v in item.items() if k in fields}) for item in items]


def cmd_run(args: argparse.Namespace) -> int:
    profile = _load_profile(args)
    if args.threshold is not None:
        profile.raw.setdefault("notify", {})["threshold"] = args.threshold
        import os

        os.environ.pop("MATCH_THRESHOLD", None)
    store = SeenStore(args.state)

    if args.fixture:
        postings = _postings_from_fixture(args.fixture)
        report = evaluate(postings, profile, store)
        if report.matches:
            picked = report.matches[: int(profile.notify.get("max_jobs_per_mail", 10))]
            notifier = build_notifier(args.notifier)
            notifier.send(
                render.subject(picked, profile),
                render.to_text(picked, profile),
                render.to_html(picked, profile),
            )
            if not args.dry_run:
                for result in picked:
                    store.mark(result.job.key, score=result.score, title=result.job.title,
                               company=result.job.company, url=result.job.url)
                store.save()
    else:
        notifier = build_notifier(args.notifier) if args.notifier else None
        source_names = args.source or [str(s) for s in (profile.search.get("sources") or ["saramin"])]
        report = run(
            profile,
            source_names=source_names,
            store=store,
            notifier=notifier,
            dry_run=args.dry_run,
        )

    print(report.summary())
    for error in report.errors:
        print(f"[오류] {error}", file=sys.stderr)
    if args.verbose:
        for rejection in report.rejected:
            print(f"  - 제외: {rejection.job.title} ({rejection.reason})")
        for result in report.below_threshold[:20]:
            print(f"  - 미달 {result.score:g}점: {result.job.company} {result.job.title}")
    for result in report.matches:
        print(f"  + {result.score:g}점 {result.job.company} {result.job.title} {result.job.url}")
    return 1 if report.errors and not report.matches else 0


def cmd_scan(args: argparse.Namespace) -> int:
    profile = _load_profile(args)
    postings: list[JobPosting] = []
    errors: list[str] = []

    if args.jd_dir:
        from .jdfiles import load_dir

        postings.extend(load_dir(args.jd_dir))
    if args.fixture:
        postings.extend(_postings_from_fixture(args.fixture))
    if args.source or (not args.jd_dir and not args.fixture):
        names = args.source or [str(s) for s in (profile.search.get("sources") or ["saramin"])]
        fetched, fetch_errors = collect(profile, names)
        postings.extend(fetched)
        errors.extend(fetch_errors)

    if not args.no_filters:
        kept: list[JobPosting] = []
        dropped = 0
        for job in postings:
            # 직접 모아둔 JD 파일은 이미 관심 공고이므로 필터를 적용하지 않는다
            if job.source == "jdfile" or check_filters(job, profile) is None:
                kept.append(job)
            else:
                dropped += 1
        if dropped:
            print(f"하드 필터로 {dropped}건 제외 (--no-filters 로 끌 수 있습니다)")
        postings = kept

    report = demand_mod.analyze(
        postings,
        profile,
        include_summary=args.include_summary,
        min_phrase_df=args.min_phrase_df,
    )
    report.errors.extend(errors)
    print(demand_mod.to_text(report, profile, top=args.top))

    if args.markdown:
        Path(args.markdown).write_text(
            demand_mod.to_markdown(report, profile), encoding="utf-8"
        )
        print(f"\n마크다운 리포트 저장: {args.markdown}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(demand_mod.to_dict(report, profile), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"JSON 저장: {args.json_out}")

    for error in errors:
        print(f"[오류] {error}", file=sys.stderr)
    return 1 if (errors and report.analyzed == 0) else 0


def cmd_score(args: argparse.Namespace) -> int:
    profile = _load_profile(args)
    raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    sections = split_sections(raw)
    job = JobPosting(
        source="manual",
        job_id="manual",
        title=args.title,
        company=args.company,
        url="",
        location=args.location,
        intro=sections.get("intro", ""),
        main_tasks=sections.get("main_tasks", ""),
        requirements=sections.get("requirements", ""),
        preferred=sections.get("preferred", ""),
        benefits=sections.get("benefits", ""),
    )
    reason = check_filters(job, profile)
    result = score_job(job, profile)
    print(f"요구 경력 판단: {required_years(job)}")
    print(f"하드 필터: {'통과' if reason is None else '제외 — ' + reason}")
    print(f"총점: {result.score:g}점 (알림 기준 {profile.threshold:g}점)")
    print(render.to_text([result], profile))
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    profile = _load_profile(args)
    if args.source == "saramin":
        from .sources.saramin import API_URL, SaraminSource

        source = SaraminSource(profile.search)
        if not source.access_key:
            print("SARAMIN_API_KEY 가 설정되지 않았습니다 (.env 또는 환경변수).", file=sys.stderr)
            return 1
        payload = source.client.get_json(API_URL, source.list_params(0))
    else:
        from .sources.wanted import API_LIST, WantedSource

        wanted = WantedSource(profile.search)
        payload = (
            wanted.fetch_detail(args.job_id)
            if args.job_id
            else wanted.client.get_json(API_LIST, wanted.list_params(0))
        )
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.save:
        Path(args.save).write_text(text + "\n", encoding="utf-8")
        print(f"저장: {args.save}")
    print(text[:4000])
    if isinstance(payload, dict):
        print("\n최상위 키:", list(payload))
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    profile = _load_profile(args)
    print(f"이름: {profile.me.get('name')} / 목표: {profile.me.get('target_role')}")
    print(f"알림 기준: {profile.threshold:g}점")
    print(f"보유 역량 {len(profile.levels)}개:")
    for keyword_id, level in sorted(profile.levels.items(), key=lambda kv: -kv[1]):
        keyword = profile.dictionary.get(keyword_id)
        label = keyword.label if keyword else keyword_id
        print(f"  level {level}  {label} ({keyword_id})")
    if profile.unknown_tokens:
        print("\n사전에 없어 무시된 표기 (keywords.yaml 에 추가하세요):")
        for token in profile.unknown_tokens:
            print(f"  ? {token}")
    print("\n포트폴리오 하이라이트:")
    for highlight in profile.highlights:
        print(f"  · {highlight.title} → {', '.join(highlight.keywords) or '(연결된 역량 없음)'}")
    return 0


def cmd_test_mail(args: argparse.Namespace) -> int:
    profile = _load_profile(args)
    sample = JobPosting(
        source="sample",
        job_id="0",
        title="[신입] 서비스 기획자 (PM)",
        company="메일 발송 테스트",
        url="https://www.wanted.co.kr/",
        location="서울 강남구",
        requirements="요구사항 정의서 및 화면설계서 작성\n개발자와의 협업 경험\nFigma 활용",
        preferred="SQL 쿼리 작성 가능\nA/B 테스트 경험\nGA4 활용 경험",
    )
    result = score_job(sample, profile)
    notifier = build_notifier("email")
    notifier.send(
        render.subject([result], profile),
        render.to_text([result], profile),
        render.to_html([result], profile),
    )
    print("테스트 메일을 보냈습니다. 받은 편지함을 확인하세요.")
    return 0


COMMANDS = {
    "run": cmd_run,
    "scan": cmd_scan,
    "score": cmd_score,
    "probe": cmd_probe,
    "profile": cmd_profile,
    "test-mail": cmd_test_mail,
}


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)

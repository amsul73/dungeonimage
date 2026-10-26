# 기획 공고 매칭 알림

내 이력서/포트폴리오(= `profile.yaml`)와 채용공고의 **자격요건·우대사항**을 비교해
일치도가 높은 공고가 올라오면 **이메일로 알려주는** 프로그램입니다.

- 대상 직무: 서비스 기획자 / PM·PO **신입**
- 근무지: **서울**만
- 수집: **사람인 공개 API**(공식, 무료 키) — 다른 사이트는 수집기만 추가하면 붙습니다
- 실행: GitHub Actions 로 하루 2회 자동 실행 (내 PC 꺼져 있어도 동작)

```
공고 수집 → 하드 필터(서울/신입/직무) → 자격요건·우대사항 채점 → 기준점 이상만 → 메일 → 중복 기록
```

---

## 1. 점수는 이렇게 계산됩니다

공고 본문에서 `keywords.yaml` 에 정의된 역량(예: 요구사항 정의서, 피그마, SQL, A/B 테스트…)을
찾아내고, **그 공고가 요구한 역량 중 내가 가진 비율**을 섹션별로 계산합니다.

| 항목 | 계산 |
|---|---|
| 자격요건 충족도 | 자격요건에서 찾은 역량의 가중치 합 중, 내가 보유한 비율 (0~100%) |
| 우대사항 충족도 | 우대사항에서 찾은 역량의 가중치 합 중, 내가 보유한 비율 (0~100%) |
| 총점 | 자격요건 × 0.65 + 우대사항 × 0.35 (+ 제목 적합 +8 / 신입 명시 +5) |

- 공고에 **아예 없는 섹션**(예: 우대사항 미기재)은 중립값으로 깎지 않고 **가중평균에서 제외**합니다.
- 섹션에서 잡힌 역량이 `min_keywords_for_confidence`(기본 2개)보다 적으면 0%/100%로 튀므로 **판단 보류(중립 50%)** 로 둡니다.

- 보유 레벨이 낮으면(1~2) **부분 점수**만 반영됩니다 (`scoring.partial_level_factor`).
- 자격요건/우대사항에서 아는 역량을 하나도 못 찾으면 그 섹션은 중립값 50%로 둡니다
  (JD가 "열정 있는 분" 처럼만 쓰여 있는 경우).
- 비중·가점·중립값은 모두 `profile.yaml` 의 `scoring` 에서 조절할 수 있습니다.

알림 메일에는 공고별로 **충족 / 부분 / 부족** 역량과,
"이 공고엔 이 경험을 쓰세요"로 내 포트폴리오 하이라이트가 함께 표시됩니다.

---

## 2. `profile.yaml` — 점수의 기준

이력서(.docx)와 포트폴리오(.pptx) 내용을 반영해 이미 채워져 있습니다.
루미코드·픽포유·Shorts AI 워크플로·AI 게임 에셋 워크플로 4개 프로젝트가
`highlights` 로 들어가 있고, 역량 레벨은 아래처럼 잡혀 있습니다.

| 레벨 | 역량 |
|---|---|
| 5 | AI 서비스 기획, 프롬프트 설계, 업무 자동화 |
| 4 | 요구사항 정의서·PRD·와이어프레임·IA, Figma, 핸드오프, 운영 정책, MVP 스코프, 사용자 리서치, 개발 협업, 프로젝트 관리, API/기술 이해, 양면 플랫폼, Notion |
| 3 | 퍼소나, UX/UI, Python, QA, 지표·KPI 설계, 데이터 기반 의사결정, 웹/앱 기획, 게임·콘텐츠 도메인, 운영/GTM |
| 2 | UT, 애자일, 이커머스 |
| 1 | SQL, A/B 테스트, Jira |
| 미보유 | GA/GA4, 앰플리튜드 등 프로덕트 분석 툴 |

레벨 1~2는 부분 점수만 받으므로, **SQL·GA·A/B 테스트를 배우면 데이터 요구가 강한 공고의 점수가 바로 올라갑니다.**
새 역량이 생기면 `have` 에 한 줄 추가하거나 레벨만 올리면 됩니다.

```yaml
have:
  sql: 3          # 1=들어본 수준  2=학습/과제  3=프로젝트에서 직접  4=익숙  5=가르칠 수 있음
  ga: 2
```

`keywords.yaml` 에 없는 역량은 그 파일에 항목을 추가하세요(별칭에 JD에서 쓰이는 표기를 넣어주세요).

수정 후 확인:

```bash
python main.py profile       # 인식된 역량/레벨, 사전에 없는 표기 확인
python -m pytest tests -q    # profile.yaml 오타·구조 오류까지 검사
```

## 3. 로컬에서 먼저 돌려보기

```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# (1) 샘플 공고로 점수 로직만 확인 — 네트워크/메일 불필요
python main.py run --fixture tests/fixtures/sample_jobs.json --notifier console --dry-run --verbose

# (2) 관심 있는 공고 JD를 복사해 파일로 저장한 뒤 점수 확인
python main.py score jd.txt --title "서비스 기획자" --company "OO"

# (3) 실제 수집 (메일 없이 콘솔로만)
python main.py run --notifier console --dry-run --verbose

# (4) 메일 발송까지
cp .env.example .env     # SMTP 값 입력 후
python main.py test-mail
python main.py run
```

### 명령 요약

| 명령 | 설명 |
|---|---|
| `run` | 수집 → 채점 → 알림. `--dry-run`(기록 안 남김), `--verbose`(제외/미달 공고도 출력), `--threshold 70`, `--notifier console`, `--fixture <json>` |
| `score <파일>` | JD 텍스트 하나를 채점 (`-` 는 표준입력) |
| `profile` | `profile.yaml` 파싱 결과 확인 |
| `probe` | API 응답 원본 확인 (`--source saramin|wanted`, `--save out.json`) |
| `test-mail` | 샘플 공고로 메일 발송 테스트 |

---

## 4-0. 사람인 API 키 발급

1. https://oapi.saramin.co.kr 접속 → 사람인 계정으로 로그인
2. API 이용 신청 → 발급된 **access-key** 복사
3. 로컬은 `.env` 의 `SARAMIN_API_KEY`, 자동 실행은 GitHub Secrets 의 `SARAMIN_API_KEY` 에 넣습니다

키가 제대로 동작하는지 확인:

```bash
python main.py probe --source saramin --save out.json   # 응답 원본 확인
```

### 원티드를 쓰지 않는 이유

원티드는 서버에서의 API 자동 호출을 차단합니다(GitHub Actions 에서 `403 Forbidden`).
차단을 우회하지 않고 공식 API 를 제공하는 사람인을 기본 수집기로 씁니다.
`jobalert/sources/wanted.py` 는 접근이 허용된 환경을 위해 남겨두었고,
`profile.yaml` 의 `search.sources` 에 `wanted` 를 넣으면 다시 사용됩니다.

### 사람인 API 의 한계

이 API 는 **JD 본문(자격요건·우대사항 전문)을 제공하지 않습니다.** 제목·직무 분류·공고 키워드만 옵니다.
그래서 이 소스의 공고는 `summary` 로 표시되고, 메일에도 "본문은 링크에서 확인" 안내가 붙습니다.
자격요건·우대사항을 정밀하게 채점하려면 관심 공고의 JD를 복사해 아래처럼 돌리세요.

```bash
python main.py score jd.txt --title "서비스 기획자" --company "OO"
```

---

## 4. 이메일 설정 (Gmail 기준)

1. Google 계정 → **보안** → 2단계 인증을 켭니다.
2. **앱 비밀번호**를 발급합니다(16자리). 평소 쓰는 비밀번호가 아닙니다.
3. `.env` (로컬) 또는 GitHub Secrets (자동 실행)에 입력합니다.

| 키 | 값 예시 |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `nansin5373@gmail.com` |
| `SMTP_PASSWORD` | 앱 비밀번호 16자리 |
| `MAIL_FROM` | `nansin5373@gmail.com` |
| `MAIL_TO` | 받을 주소(쉼표로 여러 개 가능) |
| `SARAMIN_API_KEY` | 사람인 access-key (4-0 참고) |

---

## 5. GitHub Actions 자동 실행

1. 이 저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서
   위 표의 7개 키를 등록합니다(하나씩 따로 등록).
   **Settings → Actions → General → Workflow permissions** 는 `Read and write permissions` 여야
   알림 기록 커밋이 성공합니다.
2. **Actions** 탭에서 워크플로를 활성화합니다.
3. `.github/workflows/job-alert.yml` 이 매일 **09:17 / 18:17 (KST)** 에 실행됩니다.
   `Run workflow` 버튼으로 즉시 실행도 됩니다(`dry_run`, `threshold` 입력 가능).

- 알림 보낸 공고는 `state/seen.json` 에 기록되고 워크플로가 저장소에 커밋합니다
  → **같은 공고로 두 번 알림이 오지 않습니다**.
- 실행이 실패하면 GitHub가 알림 메일을 보냅니다. Actions 로그에서 원인을 확인하세요.
- 시간을 바꾸려면 워크플로의 `cron` 값을 수정하세요(UTC 기준, KST = UTC+9).

---

## 6. 알림이 너무 많거나 적을 때

| 증상 | 조치 |
|---|---|
| 알림이 너무 많다 | `notify.threshold` 를 70~80으로 올리기 |
| 알림이 거의 없다 | `threshold` 를 55~60으로 낮추기 / `have` 에 빠진 역량 추가 |
| 관심 없는 직무가 섞인다 | `filters.exclude_title_keywords` 에 단어 추가 |
| 판교·분당도 보고 싶다 | `filters.seoul_tokens` 에 `"판교"`, `"분당"` 추가 또는 `require_seoul: false` |
| 경력 1~2년 공고도 보고 싶다 | `filters.max_required_years` 올리기 |
| 수집량을 늘리고 싶다 | `search.max_pages`, `search.fetch_detail_limit` 올리기 |
| 기획 외 직무가 섞인다 | `search.saramin_job_mid_cd` / `saramin_keywords` 로 직무를 좁히기 |

`--verbose` 로 돌리면 **왜 제외됐는지 / 몇 점이었는지**가 전부 출력되니 기준 조정에 쓰세요.

---

## 7. 구조

```
main.py                  진입점
profile.yaml             내 역량 + 검색 조건 + 점수 기준  ← 주로 고치는 파일
keywords.yaml            역량 사전(별칭/가중치)
jobalert/
  config.py              profile/keywords/.env 로딩
  keywords.py            사전 로딩 + JD에서 역량 추출
  text.py                HTML 제거, 정규화, 자격요건/우대사항 섹션 분리
  matcher.py             하드 필터 + 섹션별 충족도 + 총점
  pipeline.py            수집 → 채점 → 알림 흐름
  store.py               알림 보낸 공고 기록(중복 방지)
  render.py              메일 제목/본문(HTML·텍스트)
  sources/               공고 수집기 (base.py, saramin.py, wanted.py, 레지스트리)
  notifiers/             알림 채널 (email.py, console.py)
state/seen.json          알림 기록
tests/                   pytest (63개, 테스트용 프로필 분리)
```

### 수집 사이트 추가하기

`jobalert/sources/` 에 `fetch()` 가 `JobPosting` 을 돌려주는 클래스를 만들고
`sources/__init__.py` 의 `REGISTRY` 에 등록하면 `--source <이름>` 으로 쓸 수 있습니다.
사람인은 공개 API 키(개발자센터 발급)가 필요하고, 잡코리아·점핏은 HTML 파싱이 필요합니다.

### 테스트

```bash
pip install pytest && python -m pytest tests -q
```

---

## 알아둘 점

- 사람인 공개 API 는 공식 API 이지만 공고 **본문**을 주지 않습니다(위 4-0 참고).
  넓게 거르는 것은 자동, 정밀 채점은 `score` 명령으로 반자동이라고 생각하시면 됩니다.
- `search.saramin_loc_mcd`(서울=101), `saramin_job_mid_cd`(기획·전략=2) 는 사람인 분류 코드입니다.
  수집 결과가 이상하면 `python main.py probe --source saramin --save out.json` 으로
  실제 응답을 확인한 뒤 코드를 조정하세요.
- 사람인 공고에는 이미지로만 올라온 공고가 많아, 그런 공고는 키워드가 적게 잡혀
  "판단 보류(중립)" 로 처리됩니다. 점수가 63점 근처에 몰려 있으면 대부분 이 경우입니다.

# 변경 이력 (Changelog)

PR 단위로 기록한 변경 이력과 의사결정 메모입니다. 최신이 위쪽.

> 이 파일은 git log 의 단순 복사가 아니라, **왜 그렇게 결정했는지** 와
> **어디에 영향이 있는지** 를 함께 적습니다. 새 합류자/LLM 에이전트가 의사결정
> 맥락을 빠르게 파악하기 위함.

---

## PR #14 (작업 중) — 일평균(마지막 제외) 통계 + MA 색 재조정 + DataTables 툴바 재배치

**브랜치**: `genspark_ai_developer`
**대상**: docs 8종 신규 + UI 정돈

### 변경 사항

1. **헤더 통계: "합계" → "일평균(마지막 제외)"**
   - 그동안 우측에 표시되던 `합계 1,234` 가 *기간이 길어질수록 단조 증가* 해 비교 의미가 약했음.
   - PRODUCT 마다 `values[0..n-2]` (마지막 인덱스 제외) 의 `null` 제외 평균을 별도 표기.
     예: `일평균(마지막 제외) · LAM 12.3 / TEL 4.5`
   - 유효 일자가 0개면 `—`. 소수 1자리 반올림 후 `_fmtNum()` 으로 한국식 천단위 콤마.
   - MA 계산 정책(마지막 제외) 과 동일한 기준을 적용 → 미완 데이터로 인한 왜곡 방지.

2. **MA 색 재조정** (PR #13 의 후속 톤 튜닝)
   - PR #13 의 `#a5b4fc` 등 너무 옅은 톤이 *식별성 부족* 한 피드백 → 한 단계 진하게.
   - 새 팔레트: LAM `#818cf8 / #c4b5fd`, TEL `#38bdf8 / #a5f3fc`, AMAT `#34d399 / #86efac`.
   - 막대와 라인이 *명확히 구별* 되면서도 *같은 PRODUCT 임을 색 계열로 인지* 가능한 균형점.

3. **DataTables 툴바 재배치**
   - 이전 `dom`: `<"dt-top"<"dt-top-left"lB><"dt-top-right"f>>rt<"dt-bottom"<"dt-bottom-left"i><"dt-bottom-right"p>>`
   - 이후 `dom`: `<"dt-top"<"dt-top-right"i>>rt<"dt-bottom"<"dt-tools"lBf><"dt-bottom-right"p>>`
   - 결과: 표 *위* 에는 건수 info 만 우측 정렬, 표 *아래* 에 [길이][CSV][검색] 한 줄 + 페이지네이션.
   - 의도: 도구가 "결과 표 아래" 에 모이도록 통일해, 표 첫 행이 화면 위쪽에 더 빨리 나타나도록.

4. **개발자 문서 8종 신규 (`docs/`)**
   - `README.md`, `ARCHITECTURE.md`, `DASHBOARD.md`, `FRONTEND.md`, `QUERY_SYSTEM.md`,
     `AUTH.md`, `DEVELOPMENT.md`, `CHANGELOG.md`.
   - 사람과 LLM 에이전트(Claude 4.7 Sonnet 등) 양쪽이 한 번에 코드베이스 의사결정 맥락을
     읽고 다음 작업을 이어갈 수 있도록 작성.

### 수정 파일
- `app/static/js/app.js` — 일평균 통계 로직, `_maColorFor()` 팔레트 재조정, DataTables `dom` 변경
- `app/static/css/app.css` — `.dt-top`/`.dt-tools`/`.dt-bottom` 레이아웃 재정의
- `docs/*.md` (8개 신규)

---

## PR #13 — 이동평균선 톤다운 + MA 윈도 7→4

**커밋**: `0833cf8 feat(home): 이동평균선 톤 다운(막대와 유사·연하게) + MA7 → MA4`
**머지**: `2026-04-28`

### 변경 사항

1. **MA 윈도 7일 → 4일** (`MOVING_AVG_WINDOW = 4`)
   - 단기 추세 변화를 더 민감하게 반영. 7일 윈도는 반응이 느려 보였음.
   - 자체 범례의 텍스트도 `~MA7` → `~MA4` 로 자동 갱신 (값을 `${this.movingAvgWindow}` 로 사용 중).

2. **MA 라인 색을 톤다운** (1차 시도, PR #14 에서 재조정됨)
   - 이전: 막대보다 *진한* 톤 (예: LAM `#3730a3` indigo-800)
   - 이후: 막대와 *유사하되 더 연한* 톤 (예: LAM REGULAR `#a5b4fc` indigo-300)
   - 의도: 점선 라인이 너무 강조되어 막대 절댓값 비교를 방해하던 문제 해소.
   - ※ 너무 옅어 식별성이 떨어진다는 후속 피드백 → PR #14 에서 한 단계 진하게 재조정.

### 수정 파일
- `app/static/js/app.js` — `MOVING_AVG_WINDOW = 4`, `_maColorFor()` 팔레트 변경

---

## PR #12 — 라벨/집계 변경 + DataTables 툴바 정리 + 로그인/세션 인증

**커밋**: `a3951ed feat(ui+auth): 통합대시보드 라벨/집계 변경, DataTables 툴바 정리, 로그인/세션 인증 추가`
**머지**: `2026-04-28`

### 변경 사항

1. **차트 라벨 변경**
   - REGULAR 섹션 → "초벌파싱 파일 수 (REGULAR + COMPLETE)"
   - COMPLETE 섹션 → "본 파싱 파일 수 (COMPLETE)"
   - REGULAR 차트가 사용하는 값을 `REGULAR` raw 가 아니라 `REGULAR + COMPLETE` 합산으로 변경.
   - 의도: "초벌파싱 = 그 날 파싱 시도된 모든 파일", "본 파싱 = 완전 완료된 파일" 의 의미를
     라벨과 데이터 양쪽에서 일관성 있게 표현.

2. **DataTables 툴바 정돈**
   - `dom: '<"dt-top"<"dt-top-left"lB><"dt-top-right"f>>rt<"dt-bottom"<"dt-bottom-left"i><"dt-bottom-right"p>>'`
   - 길이 셀렉터 + CSV 버튼은 좌측, 검색은 우측. 하단은 건수정보 좌, 페이지네이션 우.
   - "갱신 중..." 워터마크 텍스트 제거 — 스피너 아이콘과 중복되어 시각 노이즈 발생했음.

3. **로그인/세션 인증 추가**
   - 단일 비밀번호 (`APP_PASSWORD`) + Starlette `SessionMiddleware` (서명 쿠키).
   - 신규 라우터 `app/routers/auth.py`, 신규 템플릿 `app/templates/login.html`.
   - 미들웨어 `require_auth_middleware` 가 미인증 HTML→303 `/login`, XHR→401.
   - 사이드바 하단에 로그아웃 form 추가.
   - `hmac.compare_digest()` 로 타이밍 공격 방어, `next` 파라미터의 open redirect 차단.

### 수정 파일
- `app/config.py` — auth 관련 4개 키 추가
- `app/main.py` — SessionMiddleware + require_auth_middleware
- `app/routers/auth.py` (신규)
- `app/templates/login.html` (신규)
- `app/templates/_sidebar.html` — 로그아웃 폼
- `app/templates/home.html` — 메트릭 라벨 텍스트
- `app/static/js/app.js` — REGULAR 합산 로직, DataTables dom 정돈
- `app/static/css/app.css` — DataTables 툴바 좌/우 분리, 워터마크 제거, 로그인 페이지 스타일
- `pyproject.toml` / `uv.lock` — `itsdangerous` 의존성

### 검증
- `/`, `/vnand`, `/dram`, `/es`, `/files` — 미인증 303, 인증 후 200
- `/api/logs` — 미인증 XHR 401, 인증 후 200
- 잘못된 비밀번호 401, 올바른 비밀번호 303 + Set-Cookie

### 운영 시 주의
- `.env` 의 `APP_PASSWORD`, `SESSION_SECRET_KEY` 는 반드시 교체.
- HTTPS 환경이면 `SessionMiddleware(https_only=True)` 로 변경 검토.

---

## PR #11 — 차트 그룹화 변경 (메트릭 단위) + 이동평균선 추가

**커밋**: `b06125c feat(home): 통합 대시보드 차트 그룹화 변경 (metric별) + 이동평균선 추가`

### 변경 사항

- 카드 내부 그룹화 방식을 **PRODUCT 단위 → METRIC(REGULAR/COMPLETE) 단위** 로 변경.
  - 이전: VNAND 카드 = `LAM[REGULAR/COMPLETE] · TEL[REGULAR/COMPLETE]` (PRODUCT 가 묶음)
  - 이후: VNAND 카드 = `REGULAR[LAM,TEL] / COMPLETE[LAM,TEL]` (METRIC 이 묶음)
  - 의도: 같은 의미의 지표(REGULAR끼리, COMPLETE끼리) 를 한 차트에서 비교 가능.
- 각 PRODUCT series 에 **이동평균선** (Line series) 추가.
  - 윈도 7일, **마지막 데이터 제외**.
  - 마지막 시점은 데이터가 아직 들어오는 중이라 평균을 왜곡시킬 수 있어 의도적으로 제외.
- 자체 범례 도입 — 막대색 ▮ + PRODUCT 이름 + `~MA7` 컬러 텍스트 한 줄.
- 새 마크업: `metric-section-regular`, `metric-section-complete`, `chart-canvas-wrap`,
  `[data-role="chart-regular"]`, `[data-role="legend-regular"]`, etc.
- 새 JS 심볼: `MOVING_AVG_WINDOW`, `_initMetricSlots`, `_renderCharts`,
  `_movingAverageExcludingLast`, `_upsertMetricChart`, `_maColorFor`.

### 수정 파일
- `app/templates/home.html` — 마크업을 metric-section 구조로 재설계
- `app/static/js/app.js` — `ChartCard` 내부를 METRIC 슬롯 + MA 라인 + 자체 범례로 재구성
- `app/static/css/app.css` — `.metric-section-*`, `.legend-item`, `.legend-bar`, `.legend-ma`

---

## PR #10 — 통합 대시보드 차트 카드 리뉴얼 (PRODUCT × REGULAR/COMPLETE)

**커밋**: `6536010 feat(home): 통합 대시보드 차트 카드 리뉴얼 (PRODUCT별 REGULAR/COMPLETE 분리 차트)`

### 변경 사항

- 통합 대시보드 (`/`) 를 *카드 = 데이터 소스* 단위로 재정의.
  - VNAND 카드 (LAM/TEL), DRAM 카드 (AMAT/LAM/TEL).
  - 데이터 소스: `recent_parsing_results` 쿼리 (사용자가 환경별로 정의).
- 신규 클래스 `ChartCard` (Chart.js v4 기반) — 카드별 데이터 fetch + race UI + bar 차트.
- Chart.js v4.4.4 UMD 를 `app/static/vendor/chartjs/chart.umd.min.js` 로 로컬 번들 추가
  (CDN 의존 X).
- `_groupByProduct` 가 PRODUCT/TKIN_TIME/REGULAR/COMPLETE 컬럼을 대소문자/하이픈 변형
  허용하며 매칭.

### 의사결정
- **클라이언트 사이드 그룹핑**: 같은 raw 응답을 여러 차트가 재사용 가능 + 쿼리 정의 단순화.
  행 수가 만 단위 이상 되면 서버 사이드 집계로 옮길 것.
- **로컬 번들**: 사내 오프라인 환경 대응 + 버전 고정.
- **race-UI**: `QueryRunner` 와 동일 패턴 (`_runToken`, `_abortCtrl`, 상태 배지, 토스트).

### 수정 파일
- `app/routers/home.py` — `DASHBOARD_CARDS` 리스트
- `app/templates/home.html` — 카드 마크업
- `app/templates/base.html` — Chart.js 스크립트 로드
- `app/static/js/app.js` — `class ChartCard`
- `app/static/css/app.css` — `.chart-card`, `.dashboard-grid-charts` 등
- `app/static/vendor/chartjs/chart.umd.min.js` (신규 벤더)

---

## PR #9 — 사이드바 브랜드 클릭 → 통합 대시보드 + Log File Download 페이지

**커밋**: `4c3fea4 feat: 사이드바 브랜드 클릭 시 통합 대시보드 이동 + Log File Download 페이지 추가`

### 변경 사항
- `_sidebar.html` 의 브랜드 영역(`Recipe Advisor / Site Reliability Dashboard`) 을
  `<a href="/">` 로 감싸 통합 대시보드로 이동 가능하게.
- 새 페이지 `/files` (Log File Download)
  - 서버 로컬 디스크의 임의 경로 입력 → 존재 확인(`/files/check`) + 다운로드(`/files/download`).
  - RFC 5987 으로 한글 파일명 안전 처리 (`Content-Disposition: filename*=UTF-8''...`).
  - 인하우스 도구 가정으로 경로 화이트리스트는 두지 않음 (필요 시 `ALLOWED_ROOTS` 추가 가능).

### 수정 파일
- `app/templates/_sidebar.html`
- `app/routers/files.py` (신규)
- `app/templates/files.html` (신규)
- `app/main.py` — `include_router(files.router)`
- `app/routers/_templating.py` — `NAV_ITEMS` 에 Log File Download 추가

---

## PR #8 — race 상태 가시화 UI

**커밋**: `b37c800 feat(ui): race 상태(이전 요청 취소) 가시적 표시 UI 추가`

### 변경 사항
- 자동 갱신/탭 전환으로 인한 race 발생을 사용자가 *알 수 있도록* UI 강화.
  - 상태 배지 `이전 요청 취소 · 재실행` (1.5초 후 자동 idle/loading 전환).
  - 누적 카운터 `취소 ×N` + 펄스 애니메이션 (`_bumpCancelCount`).
  - 우측 상단 토스트 (`Toast.show`) — `showRaceToast` 옵션으로 비활성화 가능.
- 의도: 사용자가 "왜 결과가 살짝 깜빡였지?" 를 미궁에 두지 않고 명시적으로 인지하게 함.

### 수정 파일
- `app/static/js/app.js` — `Toast`, `_setStatusBadge('superseded')`, `_bumpCancelCount`
- `app/static/css/app.css` — `.status-badge[data-state="superseded"]`, `.toast-*`,
  `.cancel-count.pulse` 애니메이션

---

## PR #7 — 탭 전환 race 해결 + UI 전면 모던화

**커밋**: `7fe6ffe fix: 탭 전환 race condition 해결 + UI 전면 모던화`

### 변경 사항
- `QueryRunner` 에 `_runToken` + `AbortController` 도입 — 이전 fetch 가 늦게 도착해도 폐기.
- `QueryRunner.destroy()` 로 in-flight 안전 종료, DataTables `destroy(false)` 로
  `<table>` 노드는 보존.
- 디자인 시스템 도입 — 색상/간격/그림자/border-radius 를 CSS 커스텀 프로퍼티로 통일.
- 토글 스위치 컴포넌트(`.toggle-switch`), 상태 배지(`.status-badge`) 등 추가.

---

## PR #6 — 파라미터 입력 UI 제거 + 탭 UI 개선 + 자동 실행

**커밋**: `98c4179 feat(ui): 파라미터 입력 제거, 탭 UI 개선, 브랜드명 줄바꿈, 탭 전환 자동 실행`

### 변경 사항
- 쿼리 파라미터 입력 폼을 UI 에서 제거. 파라미터가 필요한 쿼리는 SQL 의 `COALESCE(:p, 기본값)`
  로 자체 처리.
  - 의도: 일상 운영 패턴이 "기본값 그대로 보기" 가 압도적이라 입력 UI 가 마찰을 만들었음.
- 탭 전환 시 자동으로 `runner.init({runOnLoad: true})` 호출 → 별도 [실행] 클릭 불필요.
- 사이드바 브랜드 두 줄로 줄바꿈 (`Recipe Advisor` / `Site Reliability Dashboard`).
- 키보드 좌/우 화살표로 탭 이동 (`source_page.html` 인라인 스크립트).

---

## PR #4 — sys.path 자동 보정 + 쿼리 셀렉터 → 탭 페이지

**커밋**: `e49f667 feat: sys.path 자동 보정 + 쿼리 셀렉터를 탭 페이지로 변경`

### 변경 사항
- `app/main.py` 의 `_ensure_project_root_on_path()` — IDE Run 등 cwd 가 webapp 루트가
  아닌 환경에서도 `from app.xxx` 가 동작하도록 sys.path 보정.
- 쿼리 선택 UI 를 select 박스 → 탭(`role="tablist"`) 으로 교체.

---

## PR #3 — Recipe Advisor SR Dashboard 리브랜딩 + 실행 버튼 가독성

**커밋**: `ced158a feat(ui): Recipe Advisor SR Dashboard 리브랜딩 및 실행 버튼 가독성 개선`

### 변경 사항
- 페이지 타이틀/사이드바 브랜드를 "Recipe Advisor / Site Reliability Dashboard" 로 통일.
- favicon — inline SVG (📊) 로 외부 요청 제거.
- 실행 버튼(`btn-run`) 디자인을 그라디언트 + 아이콘 분리로 가독성 개선.

---

## PR #1 — 사내 대시보드 초기 구현 (VNAND/DRAM/ES)

**커밋**: `28dd9e0 feat: 사내 대시보드 초기 구현 (VNAND/DRAM/ES)`

### 변경 사항
- FastAPI + Jinja2 SSR + Bootstrap + DataTables 기반 인하우스 대시보드 초안.
- VNAND/DRAM (MariaDB), Elasticsearch 3가지 데이터 소스.
- 라우터/서비스/리포지토리/쿼리 4계층 분리.
- 쿼리 추가는 `app/queries/<source>_queries.py` 의 `QUERIES` 딕셔너리 한 곳에서만.
- 인메모리 로그 버퍼 + UI 로그 패널.
- nohup 운영 스크립트 `run.sh`.

---

## 결정 메모 — 시간순 의사결정 정리

| 시점 | 결정 | 배경 |
|------|------|------|
| PR #1 | 4계층 분리 (router/service/repo/queries) | 사내 인하우스에서도 새 쿼리 추가가 빈번 — 한 곳만 수정으로 끝나는 패턴 필요 |
| PR #4 | 파라미터 입력 UI 제거 | 일상 사용 99% 가 기본값 — UI 마찰 제거. SQL `COALESCE` 로 옵션 처리 |
| PR #4 | 탭 페이지 + 자동 실행 | "실행 버튼 누르기" 의 1단계를 줄여 즉시 결과 확인 |
| PR #7 | `_runToken` + `AbortController` | 자동갱신/탭전환 race 로 이전 결과가 새 결과를 덮는 버그 |
| PR #8 | race 가시화 (배지/카운터/토스트) | 사용자가 race 발생을 인지하지 못하면 "버그처럼 깜빡인다" 는 인상만 남음 |
| PR #10 | 통합 대시보드 차트 카드 + Chart.js 로컬 번들 | 사내 오프라인 + 버전 고정. CDN 의존 X |
| PR #10 | 클라이언트 사이드 그룹핑 | 같은 raw 응답을 여러 차트가 재사용. 데이터 양이 늘면 서버 집계로 이행 예정 |
| PR #11 | 메트릭 단위 묶음으로 그룹화 변경 | "REGULAR끼리 비교" 가 PRODUCT 비교보다 의사결정에 직접 도움 |
| PR #11 | 이동평균선 + 마지막 데이터 제외 | 당일 데이터는 아직 흘러오는 중 → 평균을 왜곡 → 마지막 시점 제외해 trend 신뢰성 유지 |
| PR #12 | 라벨을 "초벌파싱/본 파싱" 한국어 의미어로 변경 | "REGULAR/COMPLETE" 영어 키워드보다 비즈니스 의미가 직관적 |
| PR #12 | 단일 비밀번호 + 서명 쿠키 인증 | 사내 도구 + 사용자 식별 불필요. 추후 SSO 로 갈 때 `is_authenticated()` 만 교체하면 됨 |
| PR #13 | MA 윈도 7→4 + 라인 톤다운 | 단기 추세 민감도 ↑, 라인이 막대 절댓값 비교를 방해하지 않도록 시각 위계 조정 |

---

## 향후 후보 (TBD)

- [ ] `pytest` + `httpx.AsyncClient` 기반 자동 테스트 추가
- [ ] 다중 사용자 / 사용자명 표시
- [ ] SSO (Google/Azure AD) — `Authlib` 도입
- [ ] 카드/PRODUCT 동적 추가/삭제 UI
- [ ] 서버 사이드 집계로 데이터 양 폭증 대응
- [ ] 90일 이상 데이터 시 Chart.js zoom 플러그인 도입
- [ ] systemd 서비스 단위 운영 매뉴얼 보강

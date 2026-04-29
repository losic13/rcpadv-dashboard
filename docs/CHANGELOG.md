# 변경 이력 (Changelog)

PR 단위로 기록한 변경 이력과 의사결정 메모입니다. 최신이 위쪽.

> 이 파일은 git log 의 단순 복사가 아니라, **왜 그렇게 결정했는지** 와
> **어디에 영향이 있는지** 를 함께 적습니다. 새 합류자/LLM 에이전트가 의사결정
> 맥락을 빠르게 파악하기 위함.
>
> 📌 **다른 Claude Code 에게 말 거는 메모**:
>   - 입문은 [AGENTS.md](./AGENTS.md) 를 먼저 읽으세요.
>   - 통합 대시보드 구조는 [DASHBOARD.md](./DASHBOARD.md), JS 클래스는
>     [FRONTEND.md](./FRONTEND.md), Client 접속 이력 페이지는
>     [LOGIN_HISTORY.md](./LOGIN_HISTORY.md), Log Search 는
>     [LOG_SEARCH.md](./LOG_SEARCH.md), EQP I/F 는 [EQP_IF.md](./EQP_IF.md)
>     를 참고하세요.

---

## PR #33 — AMAT 카드 부제 단순화 + 일평균 정수화·X축 아래 이동 + 오늘접속자 라벨 / 메뉴명 'Client 접속 이력'

**커밋**: `043ccb3 feat(home): AMAT 카드 부제 단순화 + 일평균 정수화·X축 아래 이동 + 오늘접속자 라벨 변경 / refactor(nav): '사용자 접속 이력' → 'Client 접속 이력'`
**머지**: `2026-04-29` (Merge: `615317b`)

### 변경 사항

1. **AMAT 비정상 스텝 카드 부제 단순화**
   - 기존: `{query_id} · 결과 행 수` (내부 식별자 노출)
   - 변경: `결과 행 수` 만 표시. count 카드의 부제에서 query_id 노출은 비기술 사용자에게 잡음.

2. **VNAND/DRAM 차트 카드 — '일평균(마지막 제외)' 재배치 + 정수화**
   - 위치: 헤더 우측 → **차트 X축 아래** (`.metric-section-foot`).
   - 표기: 소수점 제거 (`Math.round`) — 정수만 표기. (예: `12.4 → 12`, `12.6 → 13`)
   - 가독성: PRODUCT 별 chip(`이름 + 큰 값`) 컴포넌트로 재구성. REGULAR(인디고)/COMPLETE(시안) 톤 차별화. dashed top-border 로 캔버스와 분리.
   - 데이터 슬롯(`data-role="stat-regular"`, `stat-complete`) 은 유지 → JS 영향 최소화.

3. **'사용자 접속 이력' → 'Client 접속 이력' 리네이밍**
   - 사이드바 메뉴 라벨 / 페이지 타이틀(`<title>` + h1) / 라우터 docstring 일괄 변경.
   - URL `/login-history` 와 내부 키 `login_history` 는 유지 → 라우팅/북마크 영향 0.

4. **오늘 접속자수 카드 — 1차 라벨 변경**
   - 전체 컬럼: `접속자` → **`총`**, 고객 컬럼: `접속자` → **`고객`**.
   - 글자 수가 달라도 시각적 폭이 같도록 `.login-today-label` 에 `min-width: 3.4em; text-align: center` 적용.

### 수정 파일
- `app/templates/home.html` — AMAT 부제, 차트 푸터 추가, 라벨 텍스트
- `app/templates/login_history.html` — docstring
- `app/routers/_templating.py` — `NAV_ITEMS` 라벨
- `app/routers/login_history.py` — `page_title` / docstring
- `app/static/css/app.css` — 푸터 chip 스타일, 라벨 pill 폭
- `app/static/js/app.js` — `Math.round` 정수화 + chip DOM 조립

---

## PR #32 — 오늘 접속자수 카드: ?커서/기본 툴팁 제거 + 접속자 ID Top 10 hover 패널

**커밋**: `3dfa853 feat(home): 오늘 접속자수 카드 - ?커서/기본 툴팁 제거 + 접속자 ID Top 10 hover 패널 / chore(home): 설명문구 '(개발자 포함/제외 두 가지)' 제거`
**머지**: `2026-04-29` (Merge: `9df7346`)

### 변경 사항

1. **`?` 커서 + 브라우저 기본 툴팁 제거**
   - 기존: `.login-today-secondary` 에 `cursor: help` + `title="같은 사용자의 중복 로그인까지 합산한 총 로그인 횟수"`.
   - 변경: 둘 다 제거. cursor 는 기본값으로 복귀.

2. **접속자 ID Top 10 hover 패널로 대체**
   - `.login-today-primary` 에 hover/focus 시 `.login-today-tip` 박스가 떠서 오늘 로그인한 사용자 ID 상위 10명을 칩 형태로 보여 준다 (count 내림차순).
   - 데이터 출처: `/login-history/today` 응답에 `users[]` (Top N) + `extra_users` (초과 인원) 추가.
   - 서버: `app/routers/login_history.py::today_snapshot` 가 기존 `/run` 의 `tooltip[0]` 에서 `users` / `extra_users` 를 추출해 카드 응답에 포함.
   - JS: `LoginTodayCard._setUsersForScope(scope, users, extra, topN)` 신규. mouseenter/mouseleave/focusin/focusout 핸들러로 토글 (CSS hover 도 안전망).
   - XSS 방어: `textContent` 로만 user_id 삽입.

3. **카드 하단 설명문 정리**
   - `오늘 0시 ~ 현재까지의 로그인 통계입니다. (개발자 포함/제외 두 가지)`
   - → `오늘 0시 ~ 현재까지의 로그인 통계입니다.`
   - 이미 컬럼 head 의 `개발자 포함 / 개발자 제외` sub 텍스트로 충분히 의도 전달.

### 수정 파일
- `app/templates/home.html` — `.login-today-tip` 마크업 추가, `title=` 제거, primary 영역에 `login-today-hover` 클래스
- `app/static/css/app.css` — `.login-today-tip*` 새 규칙, `.login-today-secondary` 의 `cursor: help` 삭제
- `app/static/js/app.js` — `LoginTodayCard` 의 `_setUsersForScope`, hover 핸들러 + destroy 시 정리
- `app/routers/login_history.py` — 응답에 `users` / `extra_users` / `tooltip_top_n` 포함
- `app/routers/home.py` — 카드 description 문구

### 주요 의사결정
- **`title=` HTML 속성 대신 커스텀 패널**: 브라우저 기본 툴팁은 (1) 폰트/색을 제어할 수 없고, (2) cursor 가 `?` 로 바뀌어 비기능적 인상, (3) 정보 밀도가 부족. 칩 패널로 동등한 정보(상위 10명) + 더 많은 정보(접속 횟수) 동시 노출.
- **CSS hover safety net**: JS hover 핸들러가 핵심이지만, JS 가 늦게 로드돼도 마우스 hover 동작은 보장되도록 CSS `:hover .login-today-tip { display: block }` 도 추가.

---

## PR #31 — login-history: CONVERT_TZ 제거 + UI 의 KST/타임존 표기 제거

**커밋**: `54b5710 refactor(login-history): CONVERT_TZ 제거 + UI 의 KST/타임존 표기 제거`
**머지**: `2026-04-29` (Merge: `13cfa90`)

### 변경 사항

1. **SQL 의 `CONVERT_TZ` 제거**
   - 기존(PR #29): WHERE/SELECT 양쪽에서 `CONVERT_TZ(date_time, '+00:00', '+09:00')` 사용.
   - 변경: DB 의 `date_time` 값을 **그대로** 사용. `WHERE date_time >= :start AND date_time < :end`, `SELECT DATE(date_time) AS day`.
   - 의도: 사용자 환경에서는 DB·서버 타임존 정책이 이미 KST 로 일치되어 있어, 코드 단의 보정이 오히려 헷갈림. **DB 가 보유한 값이 진실** 로 간주.

2. **헬퍼 `_today_kst()` 제거**
   - `app/routers/login_history.py` 의 `KST = timezone(...)`, `_today_kst()` 삭제, `date.today()` 단일 사용.

3. **UI/문서 의 KST 표기 제거**
   - 카드 description: `KST 0시 ~ 현재까지` → `오늘 0시 ~ 현재까지`.
   - login_history 페이지 sub: `... · KST 기준 · 일자별 집계` → `... · 일자별 집계`.
   - 페이지 hint: `(KST)` 제거.

### 수정 파일
- `app/queries/login_history_queries.py`
- `app/routers/login_history.py`
- `app/routers/home.py`
- `app/services/login_history_service.py`
- `app/templates/home.html`, `app/templates/login_history.html`

### 운영 시 주의
- DB 가 UTC 로 저장되는 환경에서 PR #31 을 그대로 적용하면 KST 새벽(0–9시) 로그인이 전일로 표시될 수 있음. 그 경우 PR #29 의 `CONVERT_TZ` 패턴을 다시 도입하거나 DB 자체의 timezone 을 변경해야 함.

---

## PR #30 — `/.well-known/appspecific/com.chrome.devtools.json` 204 응답 (404 noise 제거)

**커밋**: `492f6b3 fix(routes): /.well-known/appspecific/com.chrome.devtools.json 204 응답 (404 noise 제거)`
**머지**: `2026-04-29` (Merge: `4b499ef`)

### 변경 사항

- Chrome DevTools 가 자동으로 보내는 `GET /.well-known/appspecific/com.chrome.devtools.json` 요청이 인증 미들웨어에 걸려 303 (→ /login) 또는 정의되지 않은 라우트로 404 가 떨어지면서 **콘솔/서버 로그에 빨간 noise** 가 누적되는 문제.
- **신규 라우터** `app/routers/well_known.py` — `prefix=/.well-known`, `include_in_schema=False`, 위 경로에 **204 No Content** 로 조용히 응답.
- **인증 우회**: `app/routers/auth.py::PUBLIC_PATH_PREFIXES` 에 `"/.well-known/"` 추가.
- **main.py** 에 `app.include_router(well_known.router)` 등록.
- **그 외 `/.well-known/*` 경로** (예: `security.txt`) 는 정의되지 않았으므로 정상적으로 404 → 글로벌 swallow 가 아님.

### 수정 파일
- `app/routers/well_known.py` (신규)
- `app/routers/auth.py` — `PUBLIC_PATH_PREFIXES` 에 well-known 추가
- `app/main.py` — include_router

### 검증
- `/.well-known/appspecific/com.chrome.devtools.json` → 204 (이전 303/404)
- 미인증/인증 모두 동일하게 204
- `/.well-known/security.txt` (미정의) → 404 정상

상세: [WELL_KNOWN.md](./WELL_KNOWN.md)

---

## PR #29 — 통합 대시보드 "오늘 접속자수" 카드 통합 + 카드 순서 변경 + KST 일자 버그 수정 / 로그 패널 토글 정리

**커밋**: `e25a929 feat(home): 오늘 접속자수 카드 통합 + 카드 순서 변경 + KST 일자 버그 수정 / fix(log-panel): 토글 삼각형 중복 표시 정리`
**머지**: `2026-04-29` (Merge: `53d616b`)

### 변경 사항

1. **오늘 접속자수 카드를 한 장으로 통합**
   - 기존(PR #27): 두 장(`오늘 전체 접속`, `오늘 고객 접속`) 카드.
   - 변경: 한 장 카드 안에 좌(전체) | 가운데 divider | 우(고객) 두 컬럼.
   - 단일 fetch (`/login-history/today`) → `data.all`, `data.customer` 양쪽 동시 채움.
   - 새 클래스: `.login-today-card-merged`, `.login-today-cols`, `.login-today-col`, `.login-today-col-divider`, `.login-today-col-head`.
   - JS: `LoginTodayCard.cols = { all: {...}, customer: {...} }` 로 dual-column DOM 보관.

2. **카드 순서 변경**
   - VNAND 파싱 결과 → DRAM 파싱 결과 → AMAT 비정상 스텝(미처리) → 오늘 접속자수.
   - `app/routers/home.py::DASHBOARD_CARDS` 리스트 순서 재배치만으로 반영.

3. **KST 기준 "오늘" 버그 수정**
   - 기존: `date.today()` (= UTC). UTC 15:00–23:59 (= KST 0–8:59) 사이에는 `today` 가 어제로 잡혀 카드가 0명을 표시.
   - 변경(이 PR): `_today_kst()` 헬퍼 추가, `KST = timezone(timedelta(hours=9))`, SQL 의 WHERE/SELECT 모두 `CONVERT_TZ(date_time, '+00:00', '+09:00')`.
   - **주의**: PR #31 에서 다시 제거. 설명은 위쪽 PR #31 노트 참고.

4. **카드 보조 라벨 정리**
   - `참고 · 총 로그인` → `총 로그인` (`참고 · ` 접두 제거 — 이미 작은 글씨라서 부가 설명 불필요).

5. **로그 패널 토글 화살표 중복 표시 수정**
   - 기존: 템플릿에 `▲` 하드코딩 + CSS `::before` 가 상태에 따라 `▼/▲` → 확장 시 `▲ ▼ 로그 패널` 처럼 두 개.
   - 변경: 템플릿의 하드코딩 `▲` 제거. CSS `::before` 만으로 collapsed=▲, expanded=▼ 단일 표시.

### 수정 파일
- `app/templates/home.html` — 통합 카드 마크업, 카드 순서, '총 로그인' 라벨
- `app/templates/_log_panel.html` — `▲` 제거
- `app/routers/home.py` — `DASHBOARD_CARDS` 순서, login_today 단일 카드(scope=both)
- `app/routers/login_history.py` — `_today_kst()`, `today_snapshot` 의 `today = _today_kst()`
- `app/queries/login_history_queries.py` — `CONVERT_TZ` 도입
- `app/static/css/app.css` — `.login-today-card-merged*`, 로그 패널 caret 정돈
- `app/static/js/app.js` — `LoginTodayCard` 가 dual-scope 동시 처리

---

## PR #28 — 로그 패널: 사이드바 로그아웃 가림 해소 + 강조 톤 완화 / AMAT 카드 설명 문구 변경

**커밋**: `5e7251e style(log-panel): 사이드바 로그아웃 가림 해소 + 강조 톤 완화 / fix(home): AMAT 카드 설명 문구 변경`
**머지**: `2026-04-29` (Merge: `1023f39`)

### 변경 사항

- **로그 패널 sticky 위치 조정**: 사이드바 하단 로그아웃 버튼이 가려지지 않도록 `bottom`/`right` margin 보정.
- **로그 패널 강조 톤 완화**: 색/그림자/테두리를 부드럽게 — 페이지 본문 작업을 방해하지 않도록.
- **AMAT 카드 description**: `이상 감지 로그` → `사용자 조치가 필요한 이상 감지 로그 건 수 입니다.` (의미 명확화).

### 수정 파일
- `app/static/css/app.css` — 로그 패널 위치/스타일
- `app/routers/home.py` — count 카드 description

---

## PR #27 — 통합 대시보드 "오늘 접속" 카드 추가 (전체/고객, 접속자 강조)

**커밋**: `e0a38ea feat(home): 통합 대시보드 "오늘 접속" 카드 추가 (전체/고객, 접속자 강조)`
**머지**: `2026-04-29` (Merge: `361e57a`)

### 변경 사항

1. **신규 카드 타입 `login_today`**
   - 데이터: `GET /login-history/today` (단일 호출).
   - 표시: 큰 숫자 = 접속자(고유 사용자), 작은 숫자 = 총 로그인 횟수.
   - **개발자 ID 제외 정책**:
     - `오늘 전체 접속` (scope=all) — 개발자 포함.
     - `오늘 고객 접속` (scope=customer) — `app/queries/developer_ids.py::DEVELOPER_USER_IDS` 셋에서 빠짐.
   - PR #29 에서 두 카드를 한 장으로 통합.

2. **신규 클래스 `LoginTodayCard` (`app/static/js/app.js`)**
   - `QueryRunner` / `ChartCard` 와 동일한 race-UI 패턴 (`_runToken`, `AbortController`, 상태 배지, 토스트).
   - `data-scope="all|customer"` 속성으로 어느 키를 꺼낼지 결정.

3. **신규 서비스 메서드** `app/services/login_history_service.py::today_snapshot()` (PR #28 ~ #32 거치며 발전).

### 수정 파일
- `app/routers/home.py` — `DASHBOARD_CARDS` 에 `type="login_today"` 두 개 추가
- `app/templates/home.html` — `{% elif card.type == "login_today" %}` 분기
- `app/static/js/app.js` — `class LoginTodayCard`
- `app/static/css/app.css` — `.login-today-*` 스타일 셋
- `app/services/login_history_service.py` — `today_snapshot()` (또는 `/run` 재활용)

---

## PR #26 — Client 접속 이력: Y축 동기화 + 개발자 ID hover tooltip + 시리즈/툴팁 라벨 단순화

**커밋**: `7e1a13e feat(login-history): Y축 동기화 + 개발자 ID hover tooltip + 시리즈/툴팁 라벨 단순화`
**머지**: `2026-04-29` (Merge: `1a998e7`)

### 변경 사항

- **두 차트(전체/고객)의 Y축 max 동기화**: 두 차트가 같은 스케일을 공유해 비교가 쉬워짐.
- **개발자 ID hover tooltip**: 페이지 상단 `👤 개발자 ID` 토글 버튼 — hover/click 시 `lh-dev-tip` 패널이 떠서 현재 제외 중인 개발자 ID 목록을 표시. 데이터 소스: `developer_ids.get_developer_id_set()`.
- **시리즈/툴팁 라벨 단순화**: `중복 포함` → `총 로그인`, `중복 제거` → `접속자` (사용자 친화적 어휘).

### 수정 파일
- `app/templates/login_history.html`
- `app/static/css/app.css` — `.lh-dev-toggle`, `.lh-dev-tip`
- `app/static/js/app.js` — login-history 페이지 인라인 또는 동봉 로직

---

## PR #25 — Client 접속 이력: date_time 컬럼명/카드 순서/누적막대/개발자 ID 숨김/조회 버튼 룩앤필

**커밋**: `d266953 fix(login-history): date_time 컬럼명/카드 순서/누적막대/개발자 ID 숨김/조회 버튼 룩앤필`
**머지**: `2026-04-29` (Merge: `448eada`)

### 변경 사항

- DB 컬럼명 `datetime` → **`date_time`** 로 정정 (실제 DB 스키마 일치).
- 차트 카드 순서: `고객 접속(위)` → `전체 접속(아래)` (사용자 요청 — 보고 싶은 정보 우선).
- 막대 형태: grouped → **stacked**. 막대 하단(짙은 색) = 접속자(고유), 그 위에 쌓이는 = 중복 부분. 막대 전체 길이 = 총 로그인.
- 개발자 ID 목록 노출 위치 변경: 화면 하단에 큰 박스 → 카드 헤더 우측에 작은 토글 버튼 (PR #26 에서 hover tooltip 까지 추가).
- 조회 버튼을 다른 페이지의 `.btn .btn-run` 컴포넌트와 동일 룩앤필로 통일.

### 수정 파일
- `app/queries/login_history_queries.py`, `app/services/login_history_service.py`, `app/routers/login_history.py`
- `app/templates/login_history.html`, `app/static/css/app.css`, `app/static/js/app.js`

---

## PR #24 — Client 접속 이력 페이지 신규 + 사이드바 정렬 + ES 메뉴 숨김

**커밋**: `416379c feat(login-history): 사용자 접속 이력 페이지 추가 + 사이드바 정렬/ES 숨김`
**머지**: `2026-04-29` (Merge: `25a0fd1`)

### 변경 사항

1. **신규 페이지 `/login-history`** (당시 이름: "사용자 접속 이력", PR #33 에서 "Client 접속 이력" 으로 리네임).
   - `vnand.advisor.app_server_user_log` 의 `action='login'` 행을 일자별로 집계.
   - 두 차트(전체/고객) — grouped bar (PR #25 에서 stacked 로 변경).
   - 빠른 기간 선택(7/14/30/90일), 사용자별 hover tooltip(상위 10명 + 접속횟수).

2. **신규 모듈**
   - `app/queries/login_history_queries.py` — SQL 정의 + `fetch_history(start, end)`
   - `app/services/login_history_service.py` — 응답 가공
   - `app/routers/login_history.py` — `/login-history`, `/login-history/run`
   - `app/queries/developer_ids.py` — 개발자 ID 화이트리스트(`DEVELOPER_USER_IDS`, `get_developer_id_set()`)
   - `app/templates/login_history.html`

3. **사이드바 정렬 규칙** (`_templating.py::NAV_ITEMS`):
   `통합 대시보드 → 사용자 접속 이력 → Log Search → File Download → VNAND DB → DRAM DB → EQP I/F Manager`.

4. **ES 메뉴 숨김**: `Elasticsearch` 라우트는 유지하되 사이드바에서는 안 보이게 (`NAV_ITEMS_HIDDEN`).

상세: [LOGIN_HISTORY.md](./LOGIN_HISTORY.md)

---

## PR #23 — vendor sourceMappingURL 제거 + 캐시버스팅에 vendor 자산 포함

**커밋**: `1ed04de fix(static): vendor sourceMappingURL 제거 + 캐시버스팅에 vendor 자산 포함`
**머지**: `2026-04-29` (Merge: `2c57d61`)

### 변경 사항

- `app/static/vendor/*` 의 minified 파일 끝에 붙어 있던 `//# sourceMappingURL=...` 주석 제거 → 브라우저 콘솔 404 noise 차단.
- `_templating.py::_compute_asset_version()` 가 vendor 파일 mtime 도 반영 → 벤더 파일이 바뀌어도 `?v=...` 가 갱신.

### 수정 파일
- `app/static/vendor/bootstrap/*`, `app/static/vendor/datatables/*`, `app/static/vendor/chartjs/*`, `app/static/vendor/jquery/*`
- `app/routers/_templating.py` — `_compute_asset_version()` 의 `paths` 확장
- `app/templates/base.html` — vendor `<script>`/`<link>` 에 `?v={{ asset_version }}` 부착

---

## PR #22 — Log Search: 요약 pill 에 [SOURCE] 표기 + 다운로드 파일 없음 시나리오 안내 모달

**커밋**: `0804082 feat(log-search): 요약 pill에 [SOURCE] 표기 + 다운로드 파일없음 시나리오 안내 모달`
**머지**: `2026-04-29` (Merge: `d34ed8d`)

### 변경 사항

1. **요약 pill 3슬롯 표시**
   - `[SOURCE 뱃지] | 테이블 라벨 | 행 수 / 경과시간`
   - SOURCE 뱃지 = `vnand` / `dram` 톤의 작은 칩.
2. **path_column 파일 존재 사전확인**
   - 행 클릭/다운로드 직전에 `HEAD /files/check?path=...` 호출.
   - 파일 없음/권한 없음 시 친화적 모달(`File not found` 안내) — 200 응답인데 빈 파일을 다운로드하는 사고 방지.
3. **테이블 컬럼·행 표시 포맷 다듬기** (긴 path 줄임표 등).

상세: [LOG_SEARCH.md](./LOG_SEARCH.md)

---

## PR #21 — [RcpAdv] 타이틀 프리픽스 + EQP 카드 제목/버튼 정리 + content max-width 해제

**커밋**: `a26622f feat(ui): [RcpAdv] 타이틀 프리픽스 + EQP 카드 제목/버튼 정리 + content max-width 해제`
**머지**: `2026-04-29` (Merge: `7c056c4`)

### 변경 사항

1. **브라우저 타이틀에 `[RcpAdv]` 접두사**: 다중 탭 환경에서 다른 사이트와 한눈에 구분.
2. **EQP I/F Manager 페이지 카드 헤더 정리**
   - 카드 제목에 임베드된 외부 URL 표시(작게).
   - "새 창 열기" 버튼을 카드 우측 상단으로 이동.
   - 페이지명 복구.
3. **콘텐츠 최대 너비 해제**: 메인 영역의 `max-width` 를 풀어 EQP iframe 같은 와이드 콘텐츠가 가용 폭을 모두 사용.

상세: [EQP_IF.md](./EQP_IF.md)

---

## PR #20 — EQP I/F Manager 페이지(iframe 임베드) + 통합대시보드 타이틀 변경

**커밋**: `6bbbb6e feat(eqp-if+title): EQP I/F Manager 페이지(iframe 임베드) 추가 + 통합대시보드 타이틀 변경`
**머지**: `2026-04-29` (Merge: `ba72973`)

### 변경 사항

1. **신규 페이지 `/eqp-if`**: 외부 사이트(`settings.EQP_IF_MANAGER_URL`) 를 iframe 으로 임베드.
   - 대상 사이트가 `X-Frame-Options=DENY` / `frame-ancestors 'none'` 을 보내면 iframe 로드가 차단되므로, 안내 메시지 + "새 창으로 열기" 링크를 함께 표시.
   - 신규 라우터 `app/routers/eqp_if.py`, 템플릿 `app/templates/eqp_if.html`.
   - `.env` 키: `EQP_IF_MANAGER_URL`, `EQP_IF_MANAGER_TITLE`.
2. **통합대시보드 타이틀 변경**: 좀 더 명확한 페이지명으로 — 정확한 텍스트는 `app/routers/home.py` / `home.html` 참조.

상세: [EQP_IF.md](./EQP_IF.md)

---

## PR #19 — Log Search 페이지 추가 + File Download 리네임

**커밋**: `4cb1f70 feat(log-search): Log Search 페이지 추가 + File Download 리네임`
**머지**: `2026-04-29` (Merge: `cc559ac`)

### 변경 사항

1. **신규 페이지 `/log-search`**
   - 단일 검색 파라미터(예: `root_lot_wf_id`)로 화이트리스트 쿼리들을 **병렬 실행** → 통합 테이블.
   - DataTables 로 결과 표시. path 컬럼은 클릭 시 `/files/download?path=...` 로 직링크.
   - 신규 모듈: `app/queries/log_search_queries.py`, `app/services/log_search_service.py`, `app/routers/log_search.py`, `app/templates/log_search.html`.
   - 환경 변수: `LOG_SEARCH_QUERIES` (서비스 코드 내부 화이트리스트).
2. **사이드바 메뉴명**: `Log File Download` → `File Download` (Log Search 와 명확히 구분).

상세: [LOG_SEARCH.md](./LOG_SEARCH.md)

---

## PR #18 — count/chart 카드 새로고침 안 되던 문제 — 정적자원 캐시버스팅 + 카드 초기화 격리

**커밋**: `ba56518 fix(home): 카운트/차트 카드 새로고침 안 되던 문제 — 정적자원 캐시버스팅 + 카드 초기화 격리`
**머지**: `2026-04-29` (Merge: `2445308`)

### 변경 사항

1. **현상**: 새 클래스(`CountCard`) 가 추가되었는데 브라우저가 옛 `app.js` 를 캐시한 채로 보고 있어 `ReferenceError: CountCard is not defined` 가 떨어지고, 그 시점에서 *inline 스크립트 전체가 중단* — 결과적으로 새로고침 버튼 핸들러가 안 붙어 클릭이 무반응.
2. **수정 1 — 캐시버스팅**: `_templating.py::_compute_asset_version()` 가 `app.js`/`app.css` mtime 을 모아 짧은 해시 생성 → 모든 템플릿에서 `<script src="/static/js/app.js?v={{ asset_version }}">` 로 부착. 코드 배포 시 mtime 변화로 자동 재로딩.
3. **수정 2 — 카드 초기화 격리**: 각 카드의 `forEach` 콜백을 `try/catch` 로 감싸 한 카드의 예외가 *다른 카드의 초기화* 까지 끊지 않게. 또한 필수 클래스가 `window` 에 없을 때 `console.error` 로 명시적으로 알림.

### 수정 파일
- `app/routers/_templating.py` — `_compute_asset_version()` + Jinja global `asset_version`
- `app/templates/base.html`, `app/templates/home.html`, etc. — `?v={{ asset_version }}`
- `app/templates/home.html` — `try/catch` + 클래스 존재성 체크

---

## PR #17 — 통합 대시보드: 카운트 카드 추가 (DRAM amat_abnormal_steps_no_treat 결과 행 수)

**커밋**: `2e436d5 feat(home): 카운트 카드 추가 (DRAM amat_abnormal_steps_no_treat 결과 행 수)`
**머지**: `2026-04-29` (Merge: `2cfe762`)

### 변경 사항

1. **신규 카드 타입 `count`**
   - `card.type = "count"` — 임의 쿼리의 결과 행 수(row_count) 만 큰 숫자로 표시.
   - 데이터: `GET /{source}/query/{query_id}` 의 응답 `row_count` 사용.
2. **첫 번째 count 카드**: `AMAT 비정상 스텝 (미처리)` (DRAM, query_id=`amat_abnormal_steps_no_treat`).
3. **신규 JS 클래스 `CountCard`**
   - `QueryRunner` / `ChartCard` 와 동일한 race-UI 패턴.
   - 큰 숫자 + 단위(`건`).

### 수정 파일
- `app/queries/dram_queries.py` — `amat_abnormal_steps_no_treat` SQL
- `app/routers/home.py` — `DASHBOARD_CARDS` 에 `type="count"` 추가
- `app/templates/home.html` — `{% elif card.type == "count" %}` 분기
- `app/static/js/app.js` — `class CountCard`
- `app/static/css/app.css` — `.count-card`, `.count-display`, `.count-value`, `.count-unit`

---

## PR #16 — 개발자 문서 8종 신규 (`docs/`) — 두 번째 추가

**커밋**: `f0d6bdd docs: 개발자/LLM용 프로젝트 문서 8종 추가 (docs/)`  (PR #15 의 누락분 재포함)
**머지**: `2026-04-29` (Merge: `f855d51`)

`docs/` 디렉토리에 README/ARCHITECTURE/DASHBOARD/FRONTEND/QUERY_SYSTEM/AUTH/DEVELOPMENT/CHANGELOG 8개 추가.

---

## PR #15 — docs 첫 추가 (PR #14 와 함께 묶여 머지됨)

**커밋**: `473aecb docs: 개발자/LLM용 프로젝트 문서 8종 추가 (docs/)`
**머지**: `2026-04-29` (Merge: `860947c`)

PR #14 가 docs 8종 추가까지 포함했으나 PR #15 / #16 를 통해 다시 정리하며 머지.

---

## PR #14 — 일평균(마지막 제외) 통계 + MA 색 재조정 + DataTables 툴바 재배치

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

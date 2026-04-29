# Client 접속 이력 (`/login-history`) + 오늘 접속자수 카드

> 본 문서는 **두 가지** 가 함께 묶여 있습니다 — 같은 데이터/같은 서비스/같은
> 쿼리를 공유하기 때문입니다.
>
> 1. **`/login-history` 페이지** — 사이드바의 "Client 접속 이력".
> 2. **통합 대시보드의 "오늘 접속자수" 카드** — `/login-history/today` JSON 을 사용.
>
> 페이지명은 PR #33 에서 *사용자 접속 이력 → Client 접속 이력* 으로 리네이밍.
> URL 과 내부 키(`login_history`)는 그대로 유지.

## 1. 데이터 출처

- **DB**: VNAND 측 MariaDB.
- **테이블**: `login_log` (또는 환경에 맞춰 `app/queries/login_history_queries.py` 의 SQL 참고).
- **필터**: `action = 'login'` 만 집계 (logout/permission 등은 제외).
- **개발자 화이트리스트**: `app/queries/developer_ids.py::DEVELOPER_IDS`. 카드/차트의
  "고객 접속" 계산에서 *제외* 되는 사용자 ID 집합.

> **개발자 ID 추가/제거**: `app/queries/developer_ids.py` 의 `DEVELOPER_IDS` 목록 수정.
> 코드 외부(DB)에 두지 않은 이유: 운영 측에서 빠른 토글이 필요한데, DB 쪽 권한
> 이슈를 피하고 *코드 리뷰를 강제* 하기 위함.

## 2. 두 개의 엔드포인트

```
GET /login-history          (HTML, 페이지)        — Jinja2 + 차트 두 장
GET /login-history/run      (JSON, 페이지용)       — 기간별 일자 집계
GET /login-history/today    (JSON, 대시보드 카드용) — 오늘 단일 일자 스냅샷
```

### 2.1 `/login-history/run`

| 입력 | 타입 | 의미 |
|------|------|------|
| `start` | `YYYY-MM-DD` | 시작일 (포함) |
| `end`   | `YYYY-MM-DD` | 종료일 (포함) |

응답 (요약):

```json
{
  "start": "2026-04-22",
  "end":   "2026-04-29",
  "days": [
    {
      "day": "2026-04-29",
      "all":      { "total": 16, "distinct": 6 },
      "customer": { "total": 11, "distinct": 5 }
    },
    ...
  ],
  "tooltip": [
    {
      "day": "2026-04-29",
      "scope": "all",
      "users": [{ "user_id": "alice", "count": 4 }, ...],
      "extra_users": 0
    },
    ...
  ],
  "tooltip_top_n": 10,
  "developer_count": 1,
  "developer_ids": ["dev_x"],
  "elapsed_ms": 12
}
```

### 2.2 `/login-history/today`

대시보드 카드 전용. `/run` 의 *오늘 한 일자* 부분만 단순화한 응답:

```json
{
  "date": "2026-04-29",
  "all":      { "total": 16, "distinct": 6,
                "users": [{"user_id": "dev_x", "count": 5}, ...],
                "extra_users": 0 },
  "customer": { "total": 11, "distinct": 5,
                "users": [...], "extra_users": 0 },
  "developer_count": 1,
  "tooltip_top_n": 10,
  "elapsed_ms": 12
}
```

핵심:

- `users[]` 는 **count desc** 정렬, 최대 `tooltip_top_n` (기본 10) 명.
- `extra_users` = Top N 을 초과한 인원수 (UI 에 `+N명` 으로 표기).
- `customer` = `all` 에서 `developer_ids` 가 제거된 결과.

## 3. 페이지 (`/login-history`)

### 3.1 마크업 골격

```
<page-card "최근 접속 이력">
  ├── 헤더: [VNAND DB] · 최근 접속 이력 · login_history · 일자별 집계
  │         · 개발자 ID 토글 버튼 (호버 시 화이트리스트 hover-tip)
  ├── 폼: start / end / 빠른선택(7/14/30/90일) / 조회
  ├── 안내문: "stacked bar — 진한색=접속자(distinct), 전체높이=총 로그인,
  │           hover 시 Top 10 ID 표시"
  ├── 차트1: <h2>고객 접속 (개발자 제외)</h2>  → canvas#lh-chart-customer
  └── 차트2: <h2>전체 접속 (개발자 포함)</h2>  → canvas#lh-chart-all
```

### 3.2 차트 스펙

- **타입**: stacked bar (Chart.js).
- **시리즈 2개**:
  1. *접속자(distinct)* — 진한 색.
  2. *중복(total - distinct)* — 옅은 색. (= 같은 사용자가 그날 두 번 이상 로그인한 횟수)
- **막대 전체 높이** = `total` (로그인 횟수 합).
- **Y축 동기화** (PR #26): 두 차트가 같은 max 값을 공유 → 절대치 비교 가능.
- **툴팁**: 해당 일자의 `users[]` 중 Top 10 + `extra_users` 표시.

### 3.3 개발자 ID 토글

- 헤더의 작은 버튼을 hover 하면 현재 적용 중인 화이트리스트(`developer_ids`)가
  hover-tip 으로 표시됨 (PR #26).
- "어떤 ID 가 customer 집계에서 빠지는지" 를 *페이지를 떠나지 않고* 확인하는 용도.

## 4. 통합 대시보드 카드 — "오늘 접속자수" (`type=login_today`)

### 4.1 카드 구조 (현재 = PR #29 이후)

```
┌──────────────────────────────────────────────────────────────┐
│ [VNAND DB]  오늘 접속자수                                      │
│                                       [↻] [자동 10s ☐]         │
│                                                                │
│   ┌─────────────────┐ │ ┌─────────────────┐                   │
│   │ 전체 접속        │ │ │ 고객 접속        │                   │
│   │ 개발자 포함      │ │ │ 개발자 제외      │                   │
│   │                 │ │ │                 │                   │
│   │ [총]  6 명       │ │ │ [고객] 5 명      │                   │
│   │ ↑ hover 시 Top 10│ │ │ ↑ hover 시 Top 10│                   │
│   │                 │ │ │                 │                   │
│   │ 총 로그인 16 회   │ │ │ 총 로그인 11 회   │                   │
│   └─────────────────┘ │ └─────────────────┘                   │
│                                                                │
│ 오늘 0시 ~ 현재까지의 로그인 통계입니다.                          │
└──────────────────────────────────────────────────────────────┘
```

핵심 변동 이력 (시간순):
- PR #27: 두 장 분리 카드("오늘 전체 접속" + "오늘 고객 접속") 도입.
- PR #29: 한 장으로 통합 (`.login-today-card-merged` + `.login-today-cols`).
- PR #31: KST 표기 제거 ("KST 0시" → "오늘 0시").
- PR #32: `?` 커서/기본 `title="..."` 제거 → **Top 10 hover 패널** 도입. 설명문에서 "(개발자 포함/제외 두 가지)" 제거.
- PR #33: 1차 라벨 "접속자" → "총"/"고객" + `min-width: 3.4em` 으로 폭 정렬.

### 4.2 1차 라벨 (PR #33)

| scope | 라벨 |
|-------|------|
| `all` | **총** |
| `customer` | **고객** |

CSS:
```css
.login-today-label {
  min-width: 3.4em;       /* 한 글자/두 글자가 같은 폭으로 보이게 */
  text-align: center;
}
```

### 4.3 hover panel (PR #32)

- 마우스가 1차 컬럼에 들어오면 `.login-today-tip` 박스가 떠서 **Top 10 user_id**
  를 칩 형태로 노출 (count desc).
- 11명 이상이면 끝에 `+N명` 칩.
- DOM 구조:
  ```html
  <div class="login-today-primary login-today-hover">
    <span class="login-today-label">총</span>
    <span class="login-today-value" data-role="distinct-value-all">6</span>
    <span class="login-today-unit">명</span>
    <div class="login-today-tip" data-role="users-tip-all">
      <div class="login-today-tip-title">접속자 ID Top <span data-role="topn-all">10</span></div>
      <div class="login-today-users-list" data-role="users-list-all"><!-- chips --></div>
    </div>
  </div>
  ```
- JS: `LoginTodayCard._setUsersForScope(scope, users, extra, topN)` 가 칩을 채움.
  XSS 방어를 위해 `textContent` 만 사용. mouseenter/mouseleave/focusin/focusout
  핸들러로 `display` 토글 (CSS `:hover` safety net 도 함께).

### 4.4 자동 갱신

- 10초 자동 갱신 토글 (다른 카드와 동일).
- 단일 fetch 로 두 컬럼 동시 채움 → 시각적 race 발생 거의 없음.
- 그래도 race-UI 4종 세트 (token, abort, 누적취소, 토스트) 적용.

## 5. 서비스 레이어 (`app/services/login_history_service.py`)

### 5.1 책임

1. SQL 실행 (`/run` 의 기간 집계, `/today` 의 오늘 단일 일자).
2. `developer_ids` 화이트리스트로 customer 부분집합 계산.
3. 일자별 user 카운트 집계 → tooltip Top N 슬라이스.
4. 응답 dict 직렬화 (라우터는 그대로 JSON 반환).

### 5.2 주요 상수

```python
TOOLTIP_TOP_N = 10            # 카드 hover 와 페이지 차트 툴팁 모두 사용
```

> 변경 시: 라우터 응답의 `tooltip_top_n` / `users[]` 길이 / 카드 hover 의
> `.login-today-tip` 칩 개수가 함께 영향. JS 의 `_setUsersForScope` 는 이 값을
> 응답에서 받아 `topnEl.textContent` 로 표시하므로 코드 수정 없이 반영됨.

### 5.3 일자 처리

- 현재(`PR #31` 이후): SQL 의 `WHERE date_time >= :start AND date_time < :end`,
  `SELECT DATE(date_time) AS day`. **DB 의 timezone 정책** 이 진실.
- 만약 DB 가 UTC 저장이면 KST 기준 새벽 0–9시의 로그가 전일로 묶임 → 그 경우
  `CONVERT_TZ` 패턴(PR #29) 으로 되돌리거나 DB 자체 timezone 설정 변경.

## 6. 수정 포인트 표

| 원하는 변경 | 파일 | 위치 |
|-----------|------|------|
| Top N 개수 (10 → 다른 값) | `app/services/login_history_service.py` | `TOOLTIP_TOP_N` |
| 개발자 ID 추가/제거 | `app/queries/developer_ids.py` | `DEVELOPER_IDS` |
| 카드 1차 라벨 텍스트 | `app/templates/home.html` | `.login-today-label` |
| 카드 컬럼 head 텍스트 ("개발자 포함" 등) | `app/templates/home.html` | `.login-today-col-sub` |
| 카드 자동 갱신 주기 | `app/templates/home.html` | `new LoginTodayCard({ autoRefreshIntervalMs: ... })` |
| hover 칩 색/크기 | `app/static/css/app.css` | `.login-today-tip*` |
| 페이지 차트 색 | `app/static/js/app.js` | login-history 차트 초기화 색 상수 |
| 페이지 차트 Y축 동기화 해제 | `app/static/js/app.js` | 두 차트 동일 max 계산 부분 |
| SQL (집계 단위/필터) | `app/queries/login_history_queries.py` | `QUERIES` |

## 7. 주의/금기

- ❌ `users[]` 에 user_id 를 그대로 innerHTML 삽입 — `textContent` 만 사용.
- ❌ `customer` 계산을 SQL `WHERE user_id NOT IN (...)` 로 옮기지 말 것 — 배포 환경마다
  화이트리스트가 다를 수 있고, `all` / `customer` 양쪽이 *같은 결과 셋* 에서 파생되어야
  일관됨.
- ❌ `/login-history/today` 의 응답 키 변경 — `LoginTodayCard` 가 `data.all`,
  `data.customer`, `data.<scope>.users` 를 직접 참조하므로 deprecated 키도 한동안 함께 유지.

## 8. 관련 PR

- PR #24 페이지 신규
- PR #25 컬럼/카드 순서/누적막대/개발자 hover/조회 버튼
- PR #26 Y축 동기화 + 시리즈 라벨 단순화
- PR #27 카드(분리) 도입
- PR #29 카드 통합 + KST 일자 수정
- PR #31 CONVERT_TZ 제거
- PR #32 ?커서/기본 툴팁 제거 + Top 10 hover 패널
- PR #33 라벨 변경 + 페이지명 리네이밍

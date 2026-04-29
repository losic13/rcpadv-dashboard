# 프론트엔드 — `app/static/js/app.js`

본 문서는 단일 JS 번들 `app.js` 안의 4개 핵심 모듈/클래스를 설명합니다.
모든 코드는 IIFE `(function(){ 'use strict'; ... })()` 안에 들어 있고, 외부 노출은
끝부분의 `window.QueryRunner`, `window.ChartCard`, `window.Toast` 만 합니다.

## 1. 파일 한눈에 보기

```
app/static/js/app.js  (~1700+ lines)
├── 공용 유틸: fmtElapsed, buildQueryString, escapeHtml, PLACEHOLDER_HTML
├── Toast               ← 우측 상단 알림 (race / 일반 메시지)
├── class QueryRunner   ← 쿼리 실행 + DataTables + 자동갱신 + race UI
├── DATATABLES_KO       ← 한국어 번역 상수
├── LogPanel            ← 하단 로그 패널 폴링/렌더 (DOMContentLoaded 시 init)
├── MOVING_AVG_WINDOW = 4   (PR #13 에서 7→4 로 변경)
├── class ChartCard     ← 통합 대시보드 차트 카드 + 이동평균선 + race UI
├── class CountCard     ← 단일 숫자 카드 (PR #17 신규: AMAT 비정상 스텝 등)
└── class LoginTodayCard ← 오늘 접속자수 카드 (PR #27→#29 한 장 통합, #32 hover panel)
```

> 외부 노출(window.\*): `Toast`, `QueryRunner`, `ChartCard`, `CountCard`, `LoginTodayCard`.

## 2. 공용 유틸

| 함수 | 용도 |
|------|------|
| `fmtElapsed(ms)` | `1234` → `"1.23s"`, `87` → `"87ms"` |
| `buildQueryString(params)` | dict → `"?a=1&b=2"` (빈/null 키 자동 제외) |
| `escapeHtml(s)` | `&<>"'` → 엔티티. 사용자 데이터를 innerHTML 에 넣을 때 사용. |
| `PLACEHOLDER_HTML` | DataTables 초기 placeholder ("⏳ 쿼리를 자동 실행 중입니다...") |

## 3. Toast — 우측 상단 알림

```javascript
Toast.show("이전 VNAND 쿼리를 취소하고 다시 실행합니다.", {
  level: 'warn',     // 'info' | 'warn' | 'error'  → CSS 클래스 toast-{level}
  icon: '⚠',         // 좌측 아이콘 (생략 가능)
  durationMs: 2800,  // 자동 사라짐 (0 = 수동 닫기만)
});
```

특징:
- 컨테이너 `<div id="toast-container">` 가 없으면 자동 생성 후 `<body>` 에 append.
- mount 직후 `requestAnimationFrame` 으로 `toast-shown` 클래스 부여 → CSS transition.
- 닫기(×) 버튼 또는 `durationMs` 경과 시 `toast-leaving` 추가, 220ms 후 DOM 제거.

## 4. `class QueryRunner` — 쿼리 실행 + DataTables 갱신

VNAND/DRAM/ES 페이지(공용 `source_page.html`)가 사용합니다.

### 4.1 생성자 옵션

```javascript
new QueryRunner({
  rootEl: HTMLElement,             // 카드/페이지 루트 (data-role 탐색 범위)
  source: 'vnand' | 'dram' | 'es',
  queryId: string,
  autoRefreshIntervalMs: 10000,    // 기본 10초
  paramsCollector: () => ({}),     // 현재는 항상 {} 반환 (PR #4 에서 UI 제거됨)
  pageLength: 25,
  showRaceToast: true,
});
```

루트 안에서 다음 `data-role` 요소를 자동 탐색:

| `data-role` | 역할 |
|-------------|------|
| `table` | 결과를 그릴 `<table>` |
| `refresh` | 새로고침 버튼 |
| `auto-refresh` | 자동 갱신 체크박스 |
| `spinner` | 로딩 아이콘 |
| `elapsed` | "87ms · 1234행" 표시 영역 |
| `error` | 에러 메시지 박스 |
| `status-badge` | 상태 배지 (idle/loading/superseded/error/ok) |
| `cancel-count` | 누적 취소 횟수 배지 (`취소 ×N`) |

### 4.2 라이프사이클

```
new QueryRunner(opts)
   └─ init({ runOnLoad: true })
        └─ run()       ← fetch + render
   ...
   탭 전환 또는 페이지 종료
   └─ destroy()
        ├─ _stopTimer()
        ├─ _abortCtrl.abort()    ← in-flight fetch 즉시 취소
        ├─ refresh/auto 리스너 해제
        ├─ DataTables.destroy(false)  ← <table> 노드 자체는 보존
        └─ 상태 초기화 + placeholder 복구
```

### 4.3 race-condition 방어 (핵심)

자동 갱신 + 탭 전환이 겹치면 응답 순서가 뒤바뀔 수 있습니다.
이전 응답이 늦게 도착해 새 결과를 덮어쓰는 일을 막기 위해 다음을 *전부* 사용합니다:

| 보호 장치 | 동작 |
|-----------|------|
| `_runToken` (number) | `run()` 진입 시 `++this._runToken`. 응답/에러 처리 전에 `token !== this._runToken` 면 즉시 `return` (=폐기). |
| `_abortCtrl` (AbortController) | 새 run 진입 시 이전 fetch 를 `abort()`. 네트워크/JSON 파싱 비용도 절약. |
| `_destroyed` (bool) | `destroy()` 이후 모든 콜백을 차단. |

가시성 (사용자가 race 가 발생했음을 알게):

| UI | 코드 |
|----|------|
| 상태 배지 `이전 요청 취소 · 재실행` | `_setStatusBadge('superseded')`, 1.5초 후 idle/loading 복구 |
| 누적 카운터 `취소 ×N` + 펄스 애니메이션 | `_bumpCancelCount()` |
| 우측 상단 토스트 (`showRaceToast`) | `Toast.show("이전 ... 쿼리를 취소하고 ...")` |

### 4.4 `_renderTable(data)` — DataTables upsert

```
columns 가 비어 있음?
  └─ YES → DataTables 파괴 + "결과 없음" 단일 컬럼 thead

기존 dataTable 이 있고 컬럼 구성이 같음? (_sameColumns)
  ├─ YES → clear().rows.add(rows).draw(false)   ← 깜빡임 없는 재사용 경로
  └─ NO  → destroy(false) 후 thead 재구성 + 새 DataTable 인스턴스 생성
```

DataTables 초기화 옵션:

```javascript
{
  dom: '<"dt-top"<"dt-top-right"i>>rt<"dt-bottom"<"dt-tools"lBf><"dt-bottom-right"p>>',
  // 상단: [건수정보 우측 정렬]    예: "1–25 / 총 30건"
  // 하단: [길이][CSV][검색] 한 줄 + [페이지네이션 우측]
  buttons: [{ extend: 'csvHtml5', text: 'CSV 내보내기', filename: '${source}_${queryId}' }],
  pageLength: this.pageLength,           // 기본 25
  lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, '전체']],
  order: [],
  deferRender: true,
  language: DATATABLES_KO,
}
```

> 상단/하단 툴바 레이아웃은 PR #12 에서 1차 정돈, 이후 후속 커밋에서 *상단=info만*,
> *하단=length+CSV+검색 한 줄 + 페이지네이션* 으로 재배치되어 도구가 결과 표 *아래에*
> 모이도록 단순화되었습니다 (`.dt-tools` 컨테이너).

## 5. `class ChartCard` — 통합 대시보드 차트 카드

`/` 페이지 (`home.html`) 의 카드마다 1개씩 인스턴스 생성됩니다. `QueryRunner` 와
동일한 race-UI 패턴을 *그대로* 사용합니다 (state machine 의 4가지 시그널 + 토스트 + 카운터).

### 5.1 생성자 옵션

```javascript
new ChartCard({
  rootEl: HTMLElement,
  source: 'vnand' | 'dram',
  queryId: 'recent_parsing_results',
  products: ['LAM', 'TEL'],          // VNAND 카드 예
  autoRefreshIntervalMs: 10000,
  showRaceToast: true,
  movingAvgWindow: 4,                // 이동평균 윈도 (기본 4, PR #13 에서 7→4)
});
```

### 5.2 차트 슬롯 구조

`_charts` 객체에 메트릭별 슬롯 2개를 보관:

```javascript
this._charts = {
  regular:  { canvas, statEl, legendEl, chart },
  complete: { canvas, statEl, legendEl, chart },
};
```

각 슬롯은 `home.html` 의 `metric-section-regular/complete` 안에서 다음 셀렉터로 발견됨:

```
[data-role="chart-regular"]    [data-role="chart-complete"]
[data-role="stat-regular"]     [data-role="stat-complete"]
[data-role="legend-regular"]   [data-role="legend-complete"]
```

### 5.3 데이터 변환 — `_groupByProduct(data)`

서버 응답의 row 들을 PRODUCT × 일자(YYYY-MM-DD) 로 합산:

```
in:  data.columns = ['TKIN_TIME', 'PRODUCT', 'REGULAR', 'COMPLETE']
     data.rows    = [{TKIN_TIME, PRODUCT, REGULAR, COMPLETE}, ...]

out: {
  LAM: { dates: ['2026-04-01', ...], regular: [12, ...], complete: [7, ...] },
  TEL: { ... },
}
```

여기서 `regular`, `complete` 는 **raw 값** 입니다. 표시용 합산(REGULAR + COMPLETE) 은
`_renderCharts` 에서 적용 — 합산 정책과 표시 마크업이 한 곳에 응집되도록.

### 5.4 차트 그리기 — `_renderCharts(data)` → `_upsertMetricChart(...)`

각 메트릭(REGULAR/COMPLETE) 마다:

1. **라벨(X축)** = 모든 PRODUCT 의 일자 union → 정렬.
2. **각 PRODUCT series**:
   - `metric === 'regular'` 일 때 값 = `regular[i] + complete[i]` ("초벌파싱 파일 수")
   - `metric === 'complete'` 일 때 값 = `complete[i]`              ("본 파싱 파일 수")
   - 색: `_colorFor(p, metric)` (PRODUCT 톤 + 메트릭 명도)
   - MA 색: `_maColorFor(p, metric)` (막대와 같은 색 계열을 한 단계 연하게 — PR #13 후속 튜닝)
3. **일평균(마지막 제외)** = PRODUCT 마다 `values[0..n-2]` 의 `null` 제외 평균.
   `slot.statEl` 에 `일평균(마지막 제외) · LAM 123 / TEL 45` 형태로 표시.
   - 유효 값 0개면 `—`, 그 외에는 소수 1자리 반올림 후 한국식 천단위 포맷.
   - (이전: "합계" 통계. PR #13 후속 커밋에서 평균 통계로 교체)
4. **자체 범례** = `slot.legendEl` 에 PRODUCT 단위로 한 줄: 막대색 ▮ 이름 + `~MA4` 컬러텍스트.
5. **`_upsertMetricChart`**: 동일 차트 인스턴스 재사용 (`update('none')`). datasets 길이가
   바뀌면 통째로 교체. PRODUCT 가 동적으로 바뀌지 않는 한 같은 인스턴스 재사용.

datasets 구성 (PRODUCT 가 N 개일 때 → datasets 는 2N 개):

```javascript
[
  { type: 'bar',  label: 'LAM',     data: [...], backgroundColor: '#6366f1', order: 2, _kind: 'bar', _product: 'LAM' },
  { type: 'bar',  label: 'TEL',     data: [...], backgroundColor: '#0ea5e9', order: 2, _kind: 'bar', _product: 'TEL' },
  { type: 'line', label: 'LAM MA4', data: [...maExceptLast], borderColor: '#818cf8', borderDash: [6,4], order: 1, _kind: 'ma', _product: 'LAM' },
  { type: 'line', label: 'TEL MA4', data: [...], borderColor: '#38bdf8', borderDash: [6,4], order: 1, _kind: 'ma', _product: 'TEL' },
]
```

`order` 가 작을수록 위에 그려짐 → MA 라인이 막대 위에 표시.
`pointRadius: 0` 으로 점 표시 안 함, `pointHoverRadius: 4` 로 hover 시에만 점.

### 5.5 이동평균 — `_movingAverageExcludingLast(values, windowSize)`

- 길이 `n` 인 입력 → 길이 `n` 인 출력.
- `out[last] = null` (마지막 인덱스는 *항상* 평균 미계산).
- `out[i]` (i < last) = `[max(0, i - window + 1) .. i]` 윈도 내 유효 값들의 평균.
- 윈도 안에 `null` 만 있으면 `null` 반환.

마지막 데이터 제외 이유는 [DASHBOARD.md §5.2](./DASHBOARD.md#52-왜-마지막-데이터를-제외하나) 참조.

### 5.6 race-UI

`QueryRunner` 와 동일한 4종 시그널 + 토스트 사용. 차이점은 로딩 dim 대상이
테이블이 아닌 `metric-sections` 컨테이너라는 것 뿐:

```javascript
_setLoadingDim(on) {
  if (this.metricSectionsEl) {
    this.metricSectionsEl.classList.toggle('is-loading', !!on);
  }
}
```

CSS 측에서 `.metric-sections.is-loading` 에 blur/opacity 를 줘서 갱신 중임을 표시.
PR #12 에서 "갱신 중..." 워터마크 텍스트는 제거되었고 스피너 아이콘만 유지됩니다 —
중복 정보를 줄여 시각적 노이즈를 낮춤.

## 6. LogPanel — 하단 로그 패널

```
init() : DOMContentLoaded 에서 호출
  ├─ #log-panel-toggle 클릭 → .collapsed 토글 (단, #log-clear-view 이벤트는 토글 제외)
  ├─ #log-clear-view 클릭   → 화면 비우기 (서버 버퍼는 유지)
  └─ poll() 즉시 1회 + setInterval(POLL_MS=5000)

poll() : GET /api/logs?since_index=<nextIndex>
  └─ 응답:
       {
         total:       서버 측 전체 누적 (인메모리 deque size),
         next_index:  total 과 동일 (다음 폴링은 이 값부터)
         logs:        [{ts, level, logger, message}, ...]   ← since_index 이후의 새 항목만
       }

appendLogs(logs) :
  ├─ 각 항목을 <tr class="log-row level-{LEVEL}"> 로 prepend/append
  ├─ 최근 로그가 보이도록 panel-body 스크롤 맨 아래로
  └─ DOM 행이 1000개 초과하면 가장 오래된 것부터 자르기 (메모리 보호)
```

서버 측 인메모리 버퍼는 `app/logger.py` 의 `InMemoryBufferHandler(deque(maxlen=500))`.
파일 로그와 별개로 동작.

## 7. CSS 의 `data-state` 활용

`status-badge` 는 5가지 상태를 가지며, 각각 색/애니메이션이 다름:

```html
<span class="status-badge" data-state="loading">실행 중</span>
```

```css
.status-badge[data-state="idle"]       { /* hidden */ }
.status-badge[data-state="loading"]    { animation: status-blink 1s infinite; }
.status-badge[data-state="superseded"] { background: 노랑; animation: status-flash 1.4s; }
.status-badge[data-state="ok"]         { background: 초록; }
.status-badge[data-state="error"]      { background: 빨강; }
```

상태 전환은 모두 JS 의 `_setStatusBadge(state, [text])` 한 메서드로만 일어납니다.

## 8. 페이지별 사용 패턴

| 페이지 | 템플릿 | 사용 클래스 |
|--------|-------|-----------|
| `/` 통합 대시보드 | `home.html` | `ChartCard` × 2 + `CountCard` × 1 + `LoginTodayCard` × 1 + LogPanel |
| `/vnand`, `/dram`, `/es` | `source_page.html` | `QueryRunner` × 1 (탭 전환 시 destroy + 재생성) + LogPanel |
| `/files`, `/log-search` | `files.html`, `log_search.html` | (자체 인라인 스크립트) + LogPanel |
| `/login-history` | `login_history.html` | (페이지 자체 차트 init 스크립트) + LogPanel |
| `/eqp-if` | `eqp_if.html` | (없음 — iframe 임베드) + LogPanel |
| `/login` | `login.html` | (없음 — base.html 미상속) |

## 8.1. `class CountCard` (PR #17 신규)

단일 카운트(결과 행 수 등)를 큰 숫자로 표시하는 카드. `ChartCard` 와 동일한
race-UI 4종 세트를 사용하지만 차트/캔버스 없음.

```javascript
new CountCard({
  rootEl: HTMLElement,           // <section class="card count-card" data-source="dram" data-query-id="amat_abnormal_steps_no_treat">
  source: 'dram',
  queryId: 'amat_abnormal_steps_no_treat',
  unit: '건',
  autoRefreshIntervalMs: 10000,
});
```

- 응답: `/{source}/query/{query_id}` 의 `row_count` 만 사용.
- DOM: `<span data-role="count-value">` 에 `toLocaleString('ko-KR')` 한 값 주입.
- 카드 부제 (PR #33): `결과 행 수` 만 표시 (`{query_id} ·` 부분 제거).
- 에러 시 빨강 status-badge + `<div data-role="error">` 메시지.

## 8.2. `class LoginTodayCard` (PR #27 → #29 통합 → #32 hover → #33 라벨 정렬)

오늘 접속자수 카드. **단일 fetch** (`/login-history/today`) 로 두 컬럼 (전체 / 고객) 동시 채움.

### 8.2.1 생성

```javascript
new LoginTodayCard({
  rootEl: HTMLElement,
  endpoint: '/login-history/today',
  autoRefreshIntervalMs: 10000,
});
```

내부적으로 두 scope 컬럼을 보관:

```javascript
this.cols = {
  all:      { primary, distinctValueEl, totalValueEl, usersTip, usersList, topnEl },
  customer: { primary, distinctValueEl, totalValueEl, usersTip, usersList, topnEl },
};
```

### 8.2.2 데이터 → DOM 매핑

```
응답.all.distinct      → cols.all.distinctValueEl   (1차 큰 숫자, 라벨 "총")
응답.all.total         → cols.all.totalValueEl       (2차 작은 글씨, "총 로그인 N 회")
응답.all.users[]       → cols.all.usersList chips    (Top N hover panel)
응답.all.extra_users   → "+N명" chip (Top N 초과시)
응답.tooltip_top_n     → cols.all.topnEl.textContent (hover panel 헤더의 "10")
(같은 매핑이 customer 에도 적용)
```

핵심 메서드:

- `_setValuesForScope(scope, distinct, total)` — 1차/2차 숫자 갱신.
- `_setUsersForScope(scope, users, extra, topN)` — hover panel 칩 갱신.
  XSS 방어: `textContent` 만 사용. innerHTML 금지.

### 8.2.3 hover/focus 핸들링 (PR #32)

```javascript
this._hoverHandlers = [];   // destroy 시 정리용
const show = () => col.usersTip.style.display = 'block';
const hide = () => col.usersTip.style.display = 'none';
col.primary.addEventListener('mouseenter', show);
col.primary.addEventListener('mouseleave', hide);
col.primary.addEventListener('focusin',   show);  // 키보드 접근성
col.primary.addEventListener('focusout',  hide);
this._hoverHandlers.push({ el: col.primary, show, hide });
```

CSS `:hover .login-today-tip { display: block }` 도 함께 두어, JS 가 늦게 로드돼도
hover 동작은 보장 (safety net).

### 8.2.4 1차 라벨 폭 정렬 (PR #33)

전체 컬럼은 "총" (1글자), 고객 컬럼은 "고객" (2글자) — 글자 수가 다르지만 시각
폭은 동일하게 보이도록:

```css
.login-today-label {
  min-width: 3.4em;
  text-align: center;
}
```

→ pill 배경/패딩/폰트는 동일하면서 좌우 균형이 맞음.

> 카드 데이터 흐름과 서버 응답 스키마 상세는 [LOGIN_HISTORY.md](./LOGIN_HISTORY.md) 참고.

## 9. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|------------|
| `Chart is not defined` | base.html 에서 `chart.umd.min.js` 로드 누락. 또는 home.html 인라인 스크립트가 base.html 의 `extra_scripts` 블록 안에 있는지 확인. |
| 자동 갱신해도 차트 갱신이 안 됨 | DevTools Network 에서 `/{source}/query/recent_parsing_results` 응답 200 인지, JS 콘솔에 fetch 에러 없는지 확인. 401 이면 세션 만료 — 재로그인. |
| 탭 전환 시 이전 응답이 새 탭을 덮음 | 정상 시나리오에서는 발생 X. 발생한다면 `destroy()` 가 호출되지 않은 경우 — `source_page.html` 인라인 스크립트의 `runner.destroy()` 호출 확인. |
| `취소 ×N` 카운터가 비정상으로 증가 | 자동 갱신 주기가 응답 시간보다 짧아 race 가 빈번하게 발생. `autoRefreshIntervalMs` 를 늘리거나 SQL 최적화. |
| DataTables 컬럼이 사라짐 | 응답의 `columns` 가 빈 배열. SQL 의 `LIMIT 0` 이나 결과 0행 + 컬럼 부재 케이스. |
| Toast 가 사이드바 뒤에 가림 | CSS `.toast-container` 의 `z-index` 확인 (기본 1000). |

## 10. 관련 문서

- 메트릭/색/이동평균 의사결정: [DASHBOARD.md](./DASHBOARD.md)
- 응답 스키마(`columns`, `rows`, ...): [QUERY_SYSTEM.md §3.2](./QUERY_SYSTEM.md#32-응답-스키마-자동-생성)
- 서버 측 race UI 와의 일관성: [ARCHITECTURE.md §3](./ARCHITECTURE.md#3-요청-처리-흐름)

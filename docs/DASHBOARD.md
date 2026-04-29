# 통합 대시보드 — 카드 구성

본 문서는 `/` 통합 대시보드 페이지의 시각화 설계, 데이터 변환 규칙, 그리고
"어디를 고치면 어디가 바뀌는지" 를 정리합니다.

## 1. 카드 구성 (현재 = PR #29 이후)

대시보드는 **한 페이지에 4개의 카드** 를 위→아래 순서로 표시합니다.

| # | 카드 | type | source | 데이터 |
|---|------|------|--------|--------|
| 1 | VNAND 파싱 결과 | `chart` | `vnand` | `recent_parsing_results` (PRODUCT: `LAM`, `TEL`) |
| 2 | DRAM 파싱 결과  | `chart` | `dram`  | `recent_parsing_results` (PRODUCT: `AMAT`, `LAM`, `TEL`) |
| 3 | AMAT 비정상 스텝(미처리) | `count` | `dram` | `amat_abnormal_steps_no_treat` 결과 행 수 |
| 4 | 오늘 접속자수 | `login_today` | `vnand` (logically) | `/login-history/today` |

> 이 정의는 `app/routers/home.py` 의 `DASHBOARD_CARDS` 리스트에 그대로 들어 있습니다.
> 카드 추가/제거/순서 변경/PRODUCT 변경은 이 리스트만 수정하면 됩니다.

### 1.1 카드 타입별 책임 분리

| type | JS 클래스 | 마크업 골격 | 핵심 동작 |
|------|----------|------------|---------|
| `chart` | `ChartCard` | metric-section × 2 + canvas × 2 | bar + MA line, 일평균(마지막 제외) chip(차트 X축 아래) |
| `count` | `CountCard` | 큰 숫자 + 단위 | `/run` 응답의 `row_count` 만 표시 |
| `login_today` | `LoginTodayCard` | 좌(전체) + 가운데 divider + 우(고객), 각 컬럼: 1차 카운트 + 2차 총 로그인 + Top 10 hover | `/login-history/today` 단일 fetch 로 두 컬럼 동시 채움 |

> JS 클래스 상세는 [FRONTEND.md](./FRONTEND.md), 오늘 접속자수 카드 데이터 흐름은
> [LOGIN_HISTORY.md](./LOGIN_HISTORY.md) 참고.

## 2. 카드 내부 구조

```
┌─────────────────────────────────────────────────────────┐
│ [VNAND DB]  VNAND 파싱 결과                              │ ← card-header
│ recent_parsing_results · TKIN_TIME 기준                  │
│                              [실행중] [↻] [자동 10s ☐]   │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 초벌파싱 파일 수 (REGULAR + COMPLETE)                 │ │ ← metric-section-regular
│ │  ▮ LAM  ▮ TEL   ~MA4   일평균(마지막 제외) ·         │ │
│ │                          LAM 123 / TEL 45           │ │
│ │ ┌─ Bar(LAM, TEL) + Line(LAM-MA4, TEL-MA4) ────────┐ │ │
│ │ │                                                  │ │ │
│ │ └──────────────────────────────────────────────────┘ │ │
│ ├─────────────────────────────────────────────────────┤ │
│ │ 본 파싱 파일 수 (COMPLETE)                            │ │ ← metric-section-complete
│ │  ▮ LAM  ▮ TEL   ~MA4   일평균(마지막 제외) ·         │ │
│ │                          LAM 12 / TEL 5             │ │
│ │ ┌─ Bar + Line ─────────────────────────────────────┐ │ │
│ │ └──────────────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

핵심:

- **카드 = 데이터 소스 (VNAND/DRAM).**
- **카드 안 = 메트릭 섹션 2개** (REGULAR / COMPLETE) — *상단/하단 분리*.
- **각 메트릭 차트의 series = PRODUCT** (LAM, TEL, AMAT 가 서로 다른 색의 막대).
- **각 PRODUCT 마다 이동평균 line** 을 함께 그림 (대시 패턴, 마지막 데이터 제외).

> 이 그룹화 방식은 PR #11 에서 결정되었습니다.
> 그 이전(PR #10)에는 PRODUCT 단위로 묶고 그 안에 REGULAR/COMPLETE 를 두었으나,
> 메트릭 단위 묶음이 *동일한 의미의 비교* 를 한눈에 보여주는 데 더 유리하다고 판단.

## 3. 메트릭의 의미 (PR #12 에서 변경)

| 라벨 (UI 표시) | 차트가 사용하는 값 |
|----------------|-------------------|
| **초벌파싱 파일 수 (REGULAR + COMPLETE)** | `REGULAR + COMPLETE` 합산 |
| **본 파싱 파일 수 (COMPLETE)** | `COMPLETE` 만 |

### 의도

- "초벌파싱 파일 수" = *그 날 파싱이 시도된 전체 파일* — 따라서 1차(REGULAR) + 본(COMPLETE) 양쪽 합산.
- "본 파싱 파일 수" = *완전한 파싱이 끝난 파일* — COMPLETE 만.
- 같은 일자에서 두 차트의 막대 높이를 비교하면 "초벌 대비 본 파싱 진척률" 을 시각적으로 추정 가능.

### 코드상 위치

`app/static/js/app.js` `ChartCard._renderCharts` 안:

```javascript
const v = (metric === 'regular')
  ? (Number(g.regular[i]) || 0) + (Number(g.complete[i]) || 0)   // ← 합산
  : (Number(g.complete[i]) || 0);                                 // ← COMPLETE 만
```

`_groupByProduct` 는 raw 값 (`regularRaw`, `complete`) 만 보존하고, 합산은
표시 단계에서 일관되게 적용합니다.

## 4. 색상 팔레트

PRODUCT 별 톤 + 메트릭(REGULAR/COMPLETE)의 명도 차이를 둡니다.

| PRODUCT | REGULAR (막대) | COMPLETE (막대) | MA · REGULAR | MA · COMPLETE |
|---------|----------------|-----------------|--------------|----------------|
| LAM | `#6366f1` indigo-500 | `#a78bfa` violet-400 | `#818cf8` indigo-400 | `#c4b5fd` violet-300 |
| TEL | `#0ea5e9` sky-500 | `#67e8f9` cyan-300 | `#38bdf8` sky-400 | `#a5f3fc` cyan-200 |
| AMAT | `#10b981` emerald-500 | `#6ee7b7` emerald-300 | `#34d399` emerald-400 | `#86efac` green-300 |
| (fallback) | `#64748b` slate | `#cbd5e1` slate-300 | `#94a3b8` slate-400 | `#cbd5e1` slate-300 |

위 매핑은 `_colorFor(product, kind)` / `_maColorFor(product, kind)` 함수에 정의되어 있습니다.

> **PR #13 의 결정**: 이동평균선의 색을 *막대보다 진한 톤* 에서 *막대와 유사 계열·한 단계 연한 톤* 으로
> 변경했습니다. 라인이 막대 위에 떠 있는 시각 흐름을 보존하되, 라인이 너무 강조되어 데이터 포인트의
> 절댓값 비교를 방해하던 문제를 해소합니다.
>
> **PR #13 후속 튜닝**: 첫 톤다운 안(`#a5b4fc` 등)이 너무 옅어 식별이 어렵다는 피드백 → 한 단계 진하게
> 재조정 (`#818cf8` 등). 막대와 라인이 명확히 구별되면서도 같은 PRODUCT 임을 색 계열로 인지하도록
> 하는 균형점.

## 5. 이동평균 (MA) 시리즈

### 5.1 규칙

- **윈도**: 4일 (`MOVING_AVG_WINDOW = 4`, PR #13 에서 7→4 로 단축).
  - 단기 추세를 더 민감하게 반영하기 위함. 7일 윈도는 변화가 느려 보였음.
  - 생성자 옵션 `movingAvgWindow` 로 카드별 오버라이드 가능.
- **마지막 데이터 제외**: 시리즈의 마지막 인덱스(`labels` 의 가장 최근 일자)는
  계산하지 않고 `null` 로 채움 → 라인이 끝까지 그려지지 않음.
- **결측 처리**: 윈도 내 `null` 값은 무시하고 *존재하는 값* 들의 평균. 윈도 안에 유효 값이
  하나도 없으면 `null`.
- **Chart.js 옵션**: `spanGaps: true` 로 중간에 null 이 있어도 라인이 끊기지 않음.
  마지막 인덱스 null 만 정확히 끝부분의 한 점으로 작용.

### 5.2 왜 마지막 데이터를 제외하나?

당일/최근 시점은 **데이터가 아직 흘러 들어오는 중**이라 합산이 미완.
- 그 값을 평균에 포함하면 트렌드가 일시적으로 *낮게* 보임.
- 그 점만 라인 끝에 직접 그리면 사용자가 "이게 추세 평균이다" 라고 오해하기 쉬움.
- 따라서 평균선은 안정된 과거 데이터까지만 그려서 신뢰성을 유지.

### 5.3 코드

```javascript
_movingAverageExcludingLast(values, windowSize) {
  const n = values.length;
  const out = new Array(n).fill(null);
  if (n <= 1) return out;
  const last = n - 1;
  for (let i = 0; i < last; i++) {
    const start = Math.max(0, i - windowSize + 1);
    let sum = 0, cnt = 0;
    for (let j = start; j <= i; j++) {
      const v = values[j];
      if (v != null && !isNaN(v)) { sum += Number(v); cnt += 1; }
    }
    out[i] = cnt > 0 ? sum / cnt : null;
  }
  // out[last] 는 null 로 유지
  return out;
}
```

## 6. 데이터 → 차트 변환 파이프라인

```
[GET /{source}/query/recent_parsing_results]
  응답: { columns: [...], rows: [{TKIN_TIME, PRODUCT, REGULAR, COMPLETE}, ...] }
            │
            ▼
[ChartCard._groupByProduct(data)]
  - columns 에서 PRODUCT/TKIN_TIME/REGULAR/COMPLETE 컬럼명을 대소문자 무시로 탐색
    (TKIN-TIME 처럼 하이픈 변형도 허용)
  - 카드의 products 목록에 없는 PRODUCT 의 row 는 폐기
  - PRODUCT × 일자(YYYY-MM-DD) 로 합산
  →  { LAM: {dates:[...], regular:[raw...], complete:[raw...]},
       TEL: {dates:[...], regular:[raw...], complete:[raw...]} }
            │
            ▼
[ChartCard._renderCharts(data)]
  - 라벨(X축) = 모든 PRODUCT 의 일자 union, 정렬
  - metric ∈ ['regular', 'complete'] 각각:
       series = products.map(p => {
         values: labels 에 맞춰 채움 + null 패딩,
         color: _colorFor(p, metric),
         maColor: _maColorFor(p, metric),
       })
       slot.statEl    ← `일평균(마지막 제외) · LAM 123 / TEL 45` 표시
       slot.legendEl  ← 자체 범례 (막대색 + ~MA4 표시)
       _upsertMetricChart(slot, labels, series, metric)
            │
            ▼
[Chart.js Bar + Line (mixed)]
  - bar dataset: PRODUCT 마다 1개  (order: 2)
  - line dataset(MA): PRODUCT 마다 1개 (order: 1, borderDash, pointRadius:0)
  - 동일 인스턴스 update('none') 로 깜빡임 최소화
```

### 6.1 컬럼 이름 매칭 정책

`_groupByProduct` 의 `findCol` 은 다음을 모두 받아들입니다:

```
'PRODUCT', 'product', 'Product'
'TKIN_TIME', 'tkin_time', 'TKIN-TIME', 'tkin-time'
'REGULAR', 'regular', ...
'COMPLETE', 'complete', ...
```

→ DB 측 컬럼 대소문자 변경(예: MariaDB collation 변경)이 있어도 깨지지 않습니다.
새 컬럼 별칭이 필요하면 `findCol('TKIN_TIME') || findCol('TKIN-TIME')` 처럼
fallback 한 줄만 추가하세요.

## 7. 자동 갱신 / 레이스 UI

`ChartCard` 는 `QueryRunner` 와 동일한 race-UI 패턴을 사용합니다.

| 요소 | 의미 |
|------|------|
| `_runToken` | 매 `run()` 호출마다 증가. 응답 도착 시 `token !== this._runToken` 이면 폐기. |
| `_abortCtrl` | 현재 in-flight `fetch` 의 `AbortController`. 새 run 진입 시 `abort()`. |
| `_cancelledCount` | 사용자에게 표시되는 누적 취소 수 (배지 `취소 ×N`). |
| 토스트 | race 발생 시 우측 상단에 `⚠ 이전 VNAND 차트(...)를 취소하고 다시 불러옵니다.` |
| 로딩 dim | `.metric-sections.is-loading` → blur + opacity 감소 |

자세한 race-UI 내부 동작은 [FRONTEND.md](./FRONTEND.md) 참조.

## 8. 자체 범례 (custom legend)

Chart.js 기본 legend 는 `display: false` 로 끄고, `metric-section-legend` 에
직접 마크업을 넣습니다.

```html
<span class="legend-item">
  <span class="legend-bar" style="background:#6366f1"></span>
  <span class="legend-name">LAM</span>
  <span class="legend-ma" title="이동평균선 (4일, 마지막 데이터 제외)" style="color:#818cf8">~MA4</span>
</span>
```

이유:
- 막대 색 + MA 라인 색을 **한 PRODUCT 한 줄** 로 보여주기 위함.
- 기본 legend 는 `bar`, `line` dataset 각각 따로 표시되어 PRODUCT 가 두 번 나타남.
- 현재 디자인은 PRODUCT 를 단위로 묶어서 인지 부하를 줄임.

## 9. 통계: 일평균 (마지막 제외) — `stat-{metric}`

각 메트릭 섹션 헤더 우측에 `일평균(마지막 제외) · LAM 123 / TEL 45` 형태로 표시합니다.

### 9.1 규칙 (PR #33 이후)

- 시리즈에서 **마지막 인덱스 값 제외** 후, **`null` 도 제외** 하고 *유효 일자* 만으로 평균.
- 유효 일자가 0 이면 `—` 로 표시.
- **정수 반올림** (`Math.round(v)`) → 소수점 표기 없음. (PR #33에서 변경: 이전엔 소수 1자리)
- 한국식 천단위 콤마 포맷.
- PRODUCT 마다 평균을 따로 계산해, **PRODUCT 칩**(이름 + 큰 값) 단위로 분리 노출 (REGULAR=인디고, COMPLETE=시안).
- **위치**: 차트 X축 *아래* 의 `<footer class="metric-section-foot">` 안. (PR #33 에서 헤더 우측 → X축 아래로 이동 — 가독성 + 헤더 혼잡 해소)

### 9.2 코드

```javascript
// PR #33: 정수만, 차트 X축 아래(.metric-section-foot)에 chip 형태로 렌더
const dailyAvgByProduct = series.map(s => {
  const head = s.values.slice(0, Math.max(0, s.values.length - 1));   // ← 마지막 제외
  const valid = head.filter(v => v != null);
  const avg = valid.length > 0
    ? valid.reduce((a, b) => a + (Number(b) || 0), 0) / valid.length
    : null;
  return { product: s.product, avg };
});
const fmtAvg = v => v == null ? '—' : Math.round(v).toLocaleString('ko-KR');  // ← 정수
// chip DOM: <span class="metric-section-stat-chip"><b>LAM</b><span>123</span></span>
```

### 9.3 왜 "합계" → "일평균" 으로?

- 합계는 *조회 기간이 길어질수록 단조 증가* 해 절대치 비교가 무의미해짐.
- 일평균은 *기간에 정규화* 되어 PRODUCT 간 처리량을 직접 비교 가능.
- MA 계산과 동일하게 마지막 데이터를 제외해, 미완 데이터로 인한 왜곡 방지.

> 이전 "합계" 통계는 `git log -- app/static/js/app.js` 의 PR #13 후속 커밋 이전 버전에 보존됩니다.

## 10. 수정 포인트 표

원하는 변경 → 어디를 고쳐야 하는지:

| 원하는 변경 | 파일 | 위치/심볼 |
|-----------|------|----------|
| 카드 추가/제거, PRODUCT 목록 변경 | `app/routers/home.py` | `DASHBOARD_CARDS` |
| 카드 제목/배지 라벨 | `app/routers/home.py` | `DASHBOARD_CARDS[].title`, `source_label` |
| 메트릭 라벨 ("초벌파싱 파일 수" 등) | `app/templates/home.html` | `metric-section-label` 스팬 |
| 차트가 사용하는 metric 값 (합산 규칙) | `app/static/js/app.js` | `_renderCharts` 의 `metric === 'regular' ? ... : ...` |
| PRODUCT/메트릭 색상 | `app/static/js/app.js` | `_colorFor`, `_maColorFor` |
| 이동평균 윈도 크기 | `app/static/js/app.js` | `MOVING_AVG_WINDOW` 상수 또는 `ChartCard` 옵션 `movingAvgWindow` |
| 마지막 데이터 *포함* 한 MA 로 변경 | `app/static/js/app.js` | `_movingAverageExcludingLast` → 마지막 인덱스도 계산 |
| 자동 갱신 주기 | `app/templates/home.html` | `new ChartCard({ autoRefreshIntervalMs: ... })` |
| 차트 그리드/스택 변경 | `app/static/js/app.js` | `_upsertMetricChart` 의 datasets `stack` 옵션 |
| 막대 두께 | `app/static/js/app.js` | `_upsertMetricChart` 의 `maxBarThickness: 22` |
| 라인 점선 패턴 | `app/static/js/app.js` | `borderDash: [6, 4]` |
| 메트릭 섹션 디자인 | `app/static/css/app.css` | `.metric-section-*` |

## 11. 알려진 제약 / 향후 개선 후보

- 클라이언트에서 모든 행을 받아 그룹핑하므로, 만 단위 이상이 되면 서버 사이드 집계 (예:
  `SELECT TKIN_TIME, PRODUCT, SUM(REGULAR), SUM(COMPLETE) ... GROUP BY ...`) 로 옮길 것.
- 일자 라벨이 너무 많아지면 Chart.js `autoSkip: true` + `maxRotation: 0` 설정으로 자동
  솎음 처리. 90일 이상이면 별도 zoom 플러그인 도입을 고려.
- 카드/PRODUCT 동적 생성을 지원하려면 `home.html` 의 인라인 스크립트와
  `_initMetricSlots()` 가 사전에 마크업이 존재한다는 가정을 풀어야 함.
- 비어 있는 응답(`row_count: 0`) 처리 — 현재는 `일평균(마지막 제외) · — / —` 와 빈 차트로 표시. 명시적
  empty-state 메시지를 원하면 `_renderCharts` 시작 부분에 분기 추가.

## 12. 관련 문서

- 응답 스키마(`recent_parsing_results`): [QUERY_SYSTEM.md](./QUERY_SYSTEM.md)
- `ChartCard` 클래스의 race-UI 내부 동작: [FRONTEND.md](./FRONTEND.md)
- 라벨/규칙 변경의 PR 이력: [CHANGELOG.md](./CHANGELOG.md)

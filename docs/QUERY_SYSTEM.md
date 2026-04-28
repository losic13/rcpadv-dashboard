# 쿼리 시스템

본 문서는 VNAND/DRAM (MariaDB) 와 Elasticsearch 쿼리의 정의 방식, 실행 파이프라인,
그리고 통합 대시보드가 의존하는 `recent_parsing_results` 응답 계약을 설명합니다.

## 1. 핵심 원칙

> **쿼리 추가는 한 곳에서만**: `app/queries/<source>_queries.py` 의 `QUERIES` 딕셔너리에
> 항목 하나만 추가하면 사이드바, 탭, (필요 시) 통합 대시보드까지 자동 반영됩니다.

라우터/서비스/템플릿 수정은 보통 필요 없습니다. 새 데이터 소스를 추가할 때만 라우터/서비스가
함께 늘어납니다.

## 2. 자료구조 (`app/queries/_base.py`)

```python
@dataclass
class ParamDef:
    name: str
    label: str
    type: Literal["string", "int", "date", "datetime"] = "string"
    default: Any = None
    required: bool = False

@dataclass
class SqlQueryDef:
    id: str
    title: str                       # UI 표시용 한글 제목 (탭/사이드바 텍스트)
    sql: str                         # SQLAlchemy text() 로 실행됨 — :name 바인딩 사용
    description: str = ""
    params: list[ParamDef] = []      # 현재 UI에서 입력받지 않음 (PR #4에서 제거)
    show_in_dashboard: bool = False  # (메타) 대시보드 후보 표시 — home.py 가 직접 enumerate

@dataclass
class EsQueryDef:
    id: str
    title: str
    index: str                       # 검색할 ES 인덱스 (또는 패턴)
    body: dict[str, Any]             # ES DSL JSON
    description: str = ""
    params: list[ParamDef] = []
    show_in_dashboard: bool = False
```

> `params` 는 자료구조에는 남아 있지만 UI 에서 입력받지 않습니다 (PR #4 의 결정).
> 파라미터가 필요한 쿼리는 SQL 의 `COALESCE(:name, <기본값>)` 패턴으로 자체 처리하세요.

## 3. SQL 쿼리 추가 — 가장 흔한 작업

### 3.1 절차

1. `app/queries/<source>_queries.py` 를 엽니다 (`vnand_queries.py` 또는 `dram_queries.py`).
2. `QUERIES` 딕셔너리에 새 항목 추가:

```python
QUERIES["recent_parsing_results"] = SqlQueryDef(
    id="recent_parsing_results",
    title="최근 파싱 결과",
    description="TKIN_TIME × PRODUCT 별 REGULAR/COMPLETE 집계.",
    sql="""
        SELECT
            DATE(TKIN_TIME)              AS TKIN_TIME,
            PRODUCT,
            SUM(REGULAR_FILE_COUNT)      AS REGULAR,
            SUM(COMPLETE_FILE_COUNT)     AS COMPLETE
        FROM parsing_summary
        WHERE TKIN_TIME >= NOW() - INTERVAL 30 DAY
        GROUP BY DATE(TKIN_TIME), PRODUCT
        ORDER BY TKIN_TIME ASC
    """,
)
```

3. 끝. 사이드바 → VNAND DB 페이지의 탭에 "최근 파싱 결과" 가 자동 노출.

### 3.2 응답 스키마 (자동 생성)

`app/services/_sql_runner.py` 의 `run_query()` 가 모든 SQL 쿼리에 대해
다음 구조의 dict 를 반환합니다:

```jsonc
{
  "query_id":   "recent_parsing_results",
  "title":      "최근 파싱 결과",
  "columns":    ["TKIN_TIME", "PRODUCT", "REGULAR", "COMPLETE"],
  "rows": [
    {"TKIN_TIME": "2026-04-01", "PRODUCT": "LAM", "REGULAR": 12, "COMPLETE": 7},
    {"TKIN_TIME": "2026-04-01", "PRODUCT": "TEL", "REGULAR":  5, "COMPLETE": 3},
    ...
  ],
  "row_count":  120,
  "elapsed_ms": 87
}
```

값 변환 규칙 (`_row_to_dict`):

- `None` → `null`
- `str | int | float | bool` → 그대로
- `datetime`, `date`, `Decimal`, `bytes` → `str(val)` (ISO 형식 문자열 등)

### 3.3 SQL 작성 가이드

| 권장 | 이유 |
|------|------|
| `LIMIT N` 명시 | UI 에 만 단위 이상 안 흘리기. 기본 1000 권장. |
| `COALESCE(:p, <default>)` 로 옵션 파라미터 처리 | 파라미터 입력 UI 없이도 동작 |
| `ORDER BY` 명시 | DataTables/차트 X축 일관성 |
| `:name` 바인딩 사용, `%s` 금지 | SQLAlchemy `text()` 규칙 |
| 멀티스테이트먼트 금지 | `text()` 가 차단함 — 시스템 한계 |

## 4. ES 쿼리 추가

```python
# app/queries/es_queries.py
QUERIES["recent_alerts"] = EsQueryDef(
    id="recent_alerts",
    title="최근 알람 (1h)",
    index="alerts-*",
    body={
        "size": 200,
        "sort": [{"@timestamp": "desc"}],
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": "now-1h"}}},
                    {"term": {"level": "ERROR"}},
                ]
            }
        }
    },
)
```

ES 응답은 SQL 과 같은 표준 dict (`columns`, `rows`, ...) 로 변환되어 클라이언트에 동일하게
처리됩니다. 변환은 `app/services/es_service.py` 가 수행 (hits → flat dict).

## 5. 실행 파이프라인 (SQL)

```
[GET /vnand/query/recent_parsing_results]
        │
        ▼
[router.vnand.run_query]
        │   request.query_params → dict
        ▼
[service.vnand.run(query_id, params)]
        │   _sql_runner.run_query("vnand", QUERIES, query_id, params)
        ▼
[_sql_runner.run_query]
        │   • _filter_params(): 정의된 ParamDef 만 추려서 binding 준비
        │   • asyncio.to_thread(mariadb.execute, ...)  — 동기 SQL 을 워커 스레드로
        │   • asyncio.wait_for(timeout=QUERY_TIMEOUT_SECONDS) — 기본 600초
        │   • elapsed_ms 측정, 표준 응답 dict
        ▼
[repositories.mariadb.execute(source, sql, bound)]
        │   • _get_engine(source) — 풀 lazy-init
        │   • text(sql) + params 바인딩
        │   • columns = list(result.keys())
        │   • rows    = [_row_to_dict(r, columns) for r in fetchall()]
        ▼
[JSONResponse]
```

예외 매핑 (라우터 단):

| 예외 | HTTP 응답 |
|------|----------|
| `KeyError` (정의되지 않은 query_id) | 404 Not Found |
| `asyncio.TimeoutError` (실행 타임아웃) | 504 Gateway Timeout |
| 그 외 모든 예외 | 500 Internal Server Error |

## 6. `recent_parsing_results` 계약 (대시보드 의존)

통합 대시보드의 `ChartCard` 가 동작하려면, VNAND/DRAM 의 `recent_parsing_results` 가
**다음 컬럼을 포함** 해야 합니다 (대소문자/하이픈 변형 허용).

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `TKIN_TIME` (또는 `TKIN-TIME`) | date / datetime / str (`YYYY-MM-DD...`) | 일자. 차트 X축. |
| `PRODUCT` | str | `LAM`, `TEL`, `AMAT` 등. 카드에 정의된 PRODUCT 만 사용. |
| `REGULAR` | int | 1차 파싱 파일 수 |
| `COMPLETE` | int | 완전 파싱 완료 파일 수 |

> 다른 컬럼이 더 있어도 무시됩니다 — `_groupByProduct` 가 위 4개만 골라서 사용.

### 컬럼 이름이 다르면?

- 대소문자 무시: `product`, `Product`, `PRODUCT` 모두 매치.
- 하이픈/언더스코어: `TKIN_TIME` / `TKIN-TIME` 둘 다 매치.
- 그 외 별칭이 필요하면 `app/static/js/app.js` 의 `_groupByProduct` 안에서
  `findCol('REGULAR') || findCol('REG_CNT')` 처럼 fallback 한 줄 추가.

### 그룹핑 정책

- `(PRODUCT, DATE(TKIN_TIME))` 단위로 합산.
- 카드의 `products` 목록에 없는 PRODUCT 의 row 는 폐기.
- 메트릭별 의미:
  - **REGULAR 차트** = `REGULAR + COMPLETE` 합산 (= "초벌파싱 파일 수")
  - **COMPLETE 차트** = `COMPLETE` 만 (= "본 파싱 파일 수")

자세한 변환은 [DASHBOARD.md §6](./DASHBOARD.md#6-데이터-차트-변환-파이프라인) 참조.

### 권장 SQL 형태

```sql
SELECT
    DATE(TKIN_TIME)             AS TKIN_TIME,
    PRODUCT,
    SUM(REGULAR_FILE_COUNT)     AS REGULAR,
    SUM(COMPLETE_FILE_COUNT)    AS COMPLETE
FROM parsing_summary
WHERE TKIN_TIME >= NOW() - INTERVAL 30 DAY
GROUP BY DATE(TKIN_TIME), PRODUCT
ORDER BY TKIN_TIME ASC
```

> 이 정의는 VNAND/DRAM 양쪽 DB 의 실제 스키마에 맞게 작성하세요.
> 본 리포지토리는 사내 스키마를 포함하지 않으며 사용자가 환경별로 작성/관리합니다.

## 7. 사이드바/탭에서 자동 노출되는 메커니즘

```
[startup]
  app/queries/<source>_queries.py 에서 QUERIES 가 import 됨
        │
        ▼
[GET /vnand]
  → router.vnand.page() : queries=vnand_service.list_queries()
        │
        ▼
[templates/source_page.html]
  for q in queries:                       ← 탭 자동 생성
      <button class="query-tab" data-query-id="{{ q.id }}" ...>
        {{ q.title }}
      </button>
  첫 탭 자동 활성화 → QueryRunner({queryId: ...}).init({runOnLoad: true})
```

탭 전환 시 `QueryRunner` 인스턴스가 `destroy()` 후 새 ID 로 재생성되며,
이때 in-flight fetch 는 `AbortController` 로 취소됩니다 (race UI). 자세한 것은
[FRONTEND.md](./FRONTEND.md) 참조.

## 8. 통합 대시보드 카드 추가/제거

대시보드는 자동 노출이 아니라 **명시적 enumerate** 방식입니다.

```python
# app/routers/home.py
DASHBOARD_CARDS = [
    {
        "source": "vnand",
        "source_label": "VNAND DB",
        "title": "VNAND 파싱 결과",
        "query_id": "recent_parsing_results",
        "products": ["LAM", "TEL"],
    },
    {
        "source": "dram",
        "source_label": "DRAM DB",
        "title": "DRAM 파싱 결과",
        "query_id": "recent_parsing_results",
        "products": ["AMAT", "LAM", "TEL"],
    },
]
```

이유:
- 대시보드 카드는 *PRODUCT 목록*, *카드 라벨* 등 페이지 고유 메타가 필요하므로 자동 노출이 부적합.
- `show_in_dashboard=True` 로 마킹된 쿼리를 enumerate 하는 자동 모드도 가능하지만, 현재는 의도적으로
  명시적 리스트를 채택해 통제권을 둠.

## 9. 새 데이터 소스(예: NAND2 DB) 추가 절차

```
1) app/queries/nand2_queries.py        ← QUERIES 딕셔너리 작성
2) app/services/nand2_service.py       ← vnand_service.py 와 동일 패턴
3) app/repositories/mariadb.py         ← _get_engine 의 source 분기에 'nand2' 추가
4) app/config.py                        ← NAND2_DB_* 항목 추가, nand2_db_url() 추가
5) app/routers/nand2.py                ← vnand.py 와 동일 패턴
6) app/main.py                          ← include_router(nand2.router)
7) app/routers/_templating.py          ← NAV_ITEMS 에 1줄 추가
8) (선택) app/routers/home.py          ← DASHBOARD_CARDS 에 카드 추가
```

> 동일 형태가 반복되면 향후 source-factory 함수로 추출하기 좋습니다.

## 10. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|------------|
| 404 "Unknown query: ..." | `QUERIES` 딕셔너리의 키가 URL 의 `query_id` 와 정확히 일치하는지 확인. |
| 504 "쿼리 타임아웃" | `QUERY_TIMEOUT_SECONDS` (기본 600초) 초과. SQL 에 인덱스/`LIMIT` 추가. |
| 500 + `Unknown column ...` | DB 컬럼명 변경. SQL 수정. |
| 차트가 비어 있음 (행 수는 들어옴) | 응답 컬럼명이 `PRODUCT/TKIN_TIME/REGULAR/COMPLETE` 와 다른지, 또는 PRODUCT 값이 카드의 `products` 목록과 대소문자 다른지 확인 (차트는 `.toUpperCase()` 비교). |
| `:p_name` 이 SQL 그대로 출력됨 | `text()` 바인딩이 안 된 경우. 파라미터가 `_filter_params` 에 의해 None 으로 설정됐는지, SQL 에서 `COALESCE(:p_name, ...)` 로 처리하고 있는지 확인. |
| ES 응답이 거대함 | `EsQueryDef.body` 에서 `size` 와 `_source` 필드 좁히기. 응답 압축이 필요한 경우 nginx 단의 gzip 권장. |

## 11. 관련 문서

- 라우터/서비스 계층 책임: [ARCHITECTURE.md §2.1](./ARCHITECTURE.md#21-각-계층의-책임-한-줄-요약)
- 응답을 차트로 렌더하는 코드 위치: [DASHBOARD.md](./DASHBOARD.md), [FRONTEND.md](./FRONTEND.md)

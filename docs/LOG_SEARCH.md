# Log Search (`/log-search`)

> PR #19 에서 신규 추가된 페이지. 같은 PR 에서 기존 "로그 파일 다운로드" 메뉴를
> "File Download" 로 리네이밍. PR #22 에서 요약 pill `[SOURCE]` 표기 + 다운로드
> 파일 부재 시 안내 모달 추가.

## 1. 무엇을 하는 페이지인가

VNAND DB / DRAM DB 양쪽의 **파싱 결과 메타** 를 단일 검색어로 동시 조회 (룻 LOT WF
ID, 제품, TKIN_TIME, 파일 경로 등). 결과 행에서 *원본 로그 파일* 로 바로
이동하거나 다운로드 가능.

## 2. 라우트

```
GET /log-search           (HTML 페이지)
GET /log-search/run       (JSON 검색 API)  — 단일 query 파라미터
```

### 2.1 `/log-search/run`

- 입력: `q` (단일 키워드 — root_lot_wf_id 일부 / 파일명 일부 / product 등).
- 처리: `app/services/log_search_service.py` 가 화이트리스트의 (source, query_id)
  쌍을 **병렬** (asyncio gather) 로 호출. 각 소스의 응답을 정규화 후 합산.
- 응답:
  ```json
  {
    "rows": [
      { "source": "vnand", "table": "parsing_results",
        "root_lot_wf_id": "...", "product": "LAM",
        "tkin_time": "2026-04-29 12:34:56",
        "file_path": "/data/...", ... },
      ...
    ],
    "columns": [...],            // DataTables 가 사용
    "row_count": 12,
    "elapsed_ms": 47,
    "per_table": [               // 디버그/요약 pill 용
      { "source": "vnand", "table": "parsing_results", "row_count": 12, "elapsed_ms": 35 },
      { "source": "dram",  "table": "parsing_results", "row_count": 0,  "elapsed_ms": 12 }
    ]
  }
  ```

## 3. UI 구성

```
[검색바: q 입력 + [검색] 버튼]
[요약 pill: vnand.parsing_results 12건 35ms · dram.parsing_results 0건 12ms]    ← PR #22: [SOURCE] 라벨
[DataTables 결과표]
   - 컬럼: SOURCE / ROOT_LOT_WF_ID / PRODUCT / TKIN_TIME / FILE / 동작
   - 동작 컬럼: 파일 다운로드 / 미리보기 등
[모달 (다운로드 파일 없을 때)]   ← PR #22 신규
```

### 3.1 `[SOURCE]` 라벨 (PR #22)

요약 pill 에 *어느 소스의 어느 테이블* 인지를 명시:

```
[VNAND] parsing_results · 12건 · 35ms
[DRAM]  parsing_results · 0건 · 12ms
```

색상 토큰은 사이드바 배지와 동일 (`vnand` 인디고 / `dram` 시안).

### 3.2 다운로드 파일 부재 안내 모달 (PR #22)

- 결과 행의 `file_path` 가 가리키는 실파일이 디스크에 없으면 다운로드 시
  *조용히 실패* 하던 문제 → 모달로 명시 안내.
- 모달 본문: 누락된 파일 경로 + "관리자에게 문의하세요" 안내 + 닫기.

## 4. 서비스 레이어 (`app/services/log_search_service.py`)

- 화이트리스트 (SOURCE, QUERY_ID) 페어:
  - `("vnand", "parsing_results_for_log_search")` (또는 동등 식별자)
  - `("dram",  "parsing_results_for_log_search")`
- 각 페어마다 `app/queries/<source>_queries.py` 의 SQL 을 재사용.
- `asyncio.gather(...)` 병렬 실행 → 가장 느린 소스 시간 ≈ 전체 elapsed_ms.
- 각 row 에 `source` / `table` 메타 컬럼을 *서비스 레이어에서* 부여 → DataTables
  컬럼 일관성 확보.

## 5. 쿼리 정의 (`app/queries/log_search_queries.py`)

- 검색용 SQL 은 *기본 parsing_results 쿼리와 분리* 된 별도 정의.
  이유: 대시보드 차트용 쿼리는 PRODUCT/시간 단위 집계, 검색용은 원시 row 반환
  + LIKE 조건. 두 쓰임을 한 SQL 로 묶으면 인덱스 전략이 어긋남.
- LIKE 패턴은 *prefix match 위주* (인덱스 활용). full-text 가 필요해지면 별도
  Elasticsearch 인덱스 도입을 검토.

## 6. 자동 갱신 / race UI

- Log Search 는 **자동 갱신을 사용하지 않는다** (사용자 검색어가 입력되어야 의미가 있어서).
- 단, 같은 검색어를 빠르게 두 번 누르거나 엔터 + 버튼이 겹치면 race 가능 →
  `QueryRunner` 와 동일 패턴(`_runToken` + `AbortController`) 적용.

## 7. 수정 포인트 표

| 원하는 변경 | 파일 | 위치 |
|-----------|------|------|
| 검색 대상 소스/테이블 추가 | `app/services/log_search_service.py` | 화이트리스트 페어 |
| 검색용 SQL | `app/queries/log_search_queries.py` | `QUERIES` |
| 결과 컬럼 / 표시 순서 | `app/templates/log_search.html` | DataTables 컬럼 옵션 |
| `[SOURCE]` pill 색 | `app/static/css/app.css` | `.lh-source-pill-*` 또는 동등 클래스 |
| 다운로드 파일 부재 모달 | `app/templates/log_search.html` + `app/static/js/app.js` | 모달 마크업 + handler |

## 8. 알려진 제약

- `LIKE '%...%'` 의 풀 스캔 가능성: 검색어가 짧고 와일드카드 양쪽에 붙으면 인덱스
  사용 불가 → *최소 길이 3 이상* 가이드를 UI 힌트로 노출 권장.
- 결과 행 수가 수만 단위면 DataTables 클라이언트 사이드 페이징이 무거워짐 →
  서버 사이드 페이징 도입 후보.
- 다운로드 파일 부재 모달은 *클라이언트의 HEAD 요청 실패* 로 판정 — 보안 헤더
  설정에 따라 false negative 가능.

## 9. 관련 PR

- PR #19 페이지 신규 + File Download 리네이밍
- PR #22 `[SOURCE]` pill + 파일 부재 모달
- PR #23 vendor sourceMappingURL 제거 + 캐시버스팅에 vendor 자산 포함

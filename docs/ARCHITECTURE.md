# 아키텍처

본 문서는 시스템 전체 구조와 요청 처리 흐름, 그리고 각 계층의 책임 범위를 설명합니다.

## 1. 기술 스택

| 영역 | 채택 |
|------|------|
| Web framework | FastAPI 0.115+ |
| ASGI server | Uvicorn (`[standard]` 옵션 — websockets/http-tools 포함) |
| 템플릿 | Jinja2 3.1 (서버사이드 렌더링) |
| 세션 | Starlette `SessionMiddleware` (itsdangerous 서명된 쿠키) |
| ORM/SQL | SQLAlchemy 2.0 + PyMySQL (MariaDB 드라이버) |
| Elasticsearch | `elasticsearch` 파이썬 클라이언트 8.15+ |
| 환경 변수 | `pydantic-settings` 2.6+ (`.env` 자동 로드) |
| Frontend 라이브러리 | Bootstrap 5, jQuery, DataTables, Chart.js v4 (UMD 로컬 번들) |
| 패키지 매니저 | uv (PEP 621 `pyproject.toml`) |

> Python 3.11 이상이 필요합니다 (`pyproject.toml` 의 `requires-python = ">=3.11"`).

## 2. 디렉토리/파일 구조와 계층 책임

```
app/
├── main.py              ← FastAPI 부트스트랩, 미들웨어 체인 등록, 라우터 include
├── config.py            ← .env 로드 (pydantic-settings)
├── logger.py            ← 로깅 (파일/콘솔/인메모리 3중)
├── routers/             ← URL 라우팅 — "얇게"
│   ├── _templating.py   ← Jinja2Templates 인스턴스 + NAV_ITEMS 공유
│   ├── auth.py          ← GET/POST /login, /logout
│   ├── home.py          ← GET / 통합 대시보드
│   ├── files.py         ← GET /files, /files/check, /files/download
│   ├── vnand.py         ← GET /vnand, /vnand/query/{query_id}
│   ├── dram.py          ← GET /dram, /dram/query/{query_id}
│   ├── es.py            ← GET /es, /es/query/{query_id}
│   └── logs.py          ← GET /api/logs (UI 로그 패널 폴링)
├── services/            ← 비즈니스 로직 (쿼리 선택, 결과 가공, 시간 측정)
│   ├── _sql_runner.py   ← VNAND/DRAM 공통 SQL 실행 + 응답 dict 표준화
│   ├── vnand_service.py
│   ├── dram_service.py
│   └── es_service.py
├── repositories/        ← 외부 시스템(DB/ES) 커넥션 + execute()
│   ├── mariadb.py       ← SQLAlchemy 엔진 lazy-init, source 별 풀
│   └── es_client.py     ← elasticsearch 8.x 클라이언트, search()
├── queries/             ← 쿼리 상수 (SqlQueryDef / EsQueryDef)
│   ├── _base.py         ← 공통 dataclass 정의
│   ├── vnand_queries.py
│   ├── dram_queries.py
│   └── es_queries.py
├── templates/           ← Jinja2 템플릿
│   ├── base.html        ← 공통 레이아웃 (사이드바 + 콘텐츠 + 로그 패널 + 벤더 스크립트)
│   ├── _sidebar.html    ← 좌측 사이드바 (브랜드/네비/로그아웃)
│   ├── _log_panel.html  ← 하단 로그 패널 (접기/펼치기)
│   ├── login.html       ← 로그인 페이지 (base.html 미상속)
│   ├── home.html        ← 통합 대시보드 (차트 카드)
│   ├── source_page.html ← VNAND/DRAM/ES 공용 (탭 + DataTables)
│   └── files.html       ← Log File Download 페이지
└── static/
    ├── css/app.css
    ├── js/app.js
    └── vendor/{bootstrap,jquery,datatables,chartjs}/
```

### 2.1 각 계층의 책임 (한 줄 요약)

| 계층 | 책임 | 하지 않는 일 |
|------|------|------------|
| `routers/*` | URL → 템플릿 렌더 / JSON 직렬화 | DB 호출, 결과 가공 |
| `services/*` | 쿼리 식별, 실행, 결과 가공, 시간 측정 | URL/HTTP 의존 |
| `repositories/*` | 커넥션/엔진 관리, execute() | 비즈니스 의미 부여 |
| `queries/*` | SQL/DSL 상수 + 메타(타이틀/설명/파라미터) | 동적 분기 (가능하면 SQL `COALESCE` 등으로 처리) |
| `templates/*` | HTML 마크업 + 최소한의 부트스트랩 JS | 데이터 가공 |
| `static/js/app.js` | `QueryRunner` / `ChartCard` / `Toast` / `LogPanel` | 페이지별 분기 (CSS 클래스/`data-*` 로 일반화) |

> 새 기능 추가 시 위 표의 "하지 않는 일" 칸을 위반하지 않는지 점검하세요.
> 특히 라우터에 SQL 을 직접 쓰거나, 쿼리 상수에 if/else 분기를 넣지 마세요.

## 3. 요청 처리 흐름

### 3.1 미들웨어 체인 (Starlette LIFO 등록 규칙)

`main.py` 에서는 의도적으로 **auth 미들웨어를 먼저 등록**하고
**SessionMiddleware 를 뒤에 등록**합니다. Starlette 는 등록 순서의 역순으로 wrap 하기
때문에, 이렇게 해야 SessionMiddleware 가 외곽에 위치하여 auth 미들웨어 안에서
`request.session` 을 안전하게 사용할 수 있습니다.

```
[Client]
   │
   ▼
[SessionMiddleware]              ← session_cookie 디코드/서명 검증, request.session 부여
   │
   ▼
[require_auth_middleware]        ← 공개 경로면 통과 / 인증 OK 면 통과 / 미인증 HTML→303 / 미인증 XHR→401
   │
   ▼
[FastAPI Router]
   │
   ▼
[엔드포인트 함수]
```

### 3.2 인증 결정 트리 (`require_auth_middleware`)

```
path 가 PUBLIC_PATH_PREFIXES 중 하나로 시작?
  └── YES → 통과
  └── NO
       └── request.session.get("authenticated") == True ?
              ├── YES → 통과
              └── NO
                   ├── XHR 또는 (Accept: application/json && !text/html) → 401 JSON
                   └── 그 외 → 303 RedirectResponse → /login?next=<원경로>
```

자세한 동작과 보안 고려사항은 [AUTH.md](./AUTH.md) 참조.

### 3.3 페이지 요청 — 통합 대시보드 (`GET /`)

```
1. require_auth_middleware: 세션 OK 확인
2. home.dashboard()            : DASHBOARD_CARDS 메타 + nav_items 를 컨텍스트로 home.html 렌더
3. 브라우저: HTML 수신 → base.html 의 vendor JS + app.js 로드
4. home.html 의 인라인 스크립트:
     for each .chart-card:
        new ChartCard({...}).init({ runOnLoad: true })
5. 각 ChartCard 가 GET /{source}/query/recent_parsing_results 비동기 호출
   - 응답: { columns, rows, row_count, elapsed_ms, ... }
   - 클라이언트가 PRODUCT × 일자로 그룹핑 → REGULAR / COMPLETE 차트 2개씩 렌더
```

### 3.4 데이터 요청 — VNAND/DRAM 쿼리 (`GET /vnand/query/recent_parsing_results`)

```
[Client fetch]
      │
      ▼
[router.vnand.run_query]
      │   query_params 를 dict 로 변환
      ▼
[service.vnand.run]
      │   _sql_runner.run_query(SOURCE="vnand", QUERIES, query_id, params)
      ▼
[_sql_runner.run_query]
      │   • _filter_params() 로 파라미터 바인딩
      │   • asyncio.to_thread(mariadb.execute, ...) 로 동기 SQL 을 워커 스레드에서 실행
      │   • asyncio.wait_for() 로 QUERY_TIMEOUT_SECONDS 타임아웃
      │   • elapsed_ms 측정, 표준 응답 dict 구성
      ▼
[repositories.mariadb.execute]
      │   • _get_engine(source) — lazy-init, pool_size=5, pool_pre_ping
      │   • SELECT 결과를 (columns, [dict, ...]) 로 변환
      ▼
[JSONResponse]
      {
        "query_id": "recent_parsing_results",
        "title": "...",
        "columns": ["TKIN_TIME", "PRODUCT", "REGULAR", "COMPLETE"],
        "rows":   [{...}, ...],
        "row_count": 1234,
        "elapsed_ms": 87
      }
```

타임아웃 시 `TimeoutError` → 라우터에서 `HTTPException(504)`,
미정의 query_id 면 `KeyError` → `HTTPException(404)`,
그 외 예외는 `HTTPException(500)`.

## 4. 동시성 / 타임아웃

- **Async 라우터 + 동기 SQL**: SQLAlchemy 동기 엔진을 `asyncio.to_thread()` 로 워커
  스레드에서 실행. `asyncio.wait_for()` 로 `QUERY_TIMEOUT_SECONDS` (기본 600초) 타임아웃.
- **DB 풀**: `create_engine(pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=3600)`.
  좀비 커넥션 방지를 위해 `pool_pre_ping` 활성화.
- **앱 종료**: `lifespan` 컨텍스트 매니저에서 `mariadb.dispose_all()`,
  `es_client.close()` 호출하여 자원 정리.

## 5. 정적 자원 / 벤더 라이브러리

외부 CDN 의존 없이 **모든 벤더 라이브러리를 `app/static/vendor/` 안에 로컬 번들**로 보관합니다.
사내망/오프라인 환경에서도 동작해야 한다는 요구 사항을 충족하기 위함.

```
static/vendor/
├── bootstrap/{bootstrap.min.css, bootstrap.bundle.min.js}
├── jquery/jquery.min.js
├── datatables/{datatables.min.css, datatables.min.js}
└── chartjs/chart.umd.min.js   ← v4.4.4 UMD (PR #10 에서 추가)
```

`base.html` 마지막에 위 순서대로 로드합니다 (jQuery → Bootstrap → DataTables → Chart.js → app.js).

## 6. 로깅

`logger.py` 에 3중 핸들러를 구성:

| 핸들러 | 용도 | 보존 |
|--------|------|------|
| `RotatingFileHandler` | 운영 영구 보관 | 10MB × 5 파일 |
| `StreamHandler` | 콘솔 출력 (개발용) | uvicorn stdout |
| `InMemoryBufferHandler` | UI 로그 패널 | `deque(maxlen=LOG_BUFFER_SIZE=500)` |

UI 로그 패널은 `GET /api/logs?since_index=N` 으로 5초마다 폴링 (`LogPanel.POLL_MS`).
서버는 `since_index` 이후의 새 항목만 잘라 반환.

> 로깅의 `.access` 잡음을 줄이기 위해 `uvicorn.access`, `elastic_transport`,
> `elasticsearch` 로거의 레벨을 `WARNING` 으로 강제하고 있습니다.

## 7. 라우트 인벤토리

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/login` | 로그인 페이지 | 공개 |
| POST | `/login` | 비밀번호 검증, 세션 부여 | 공개 |
| GET / POST | `/logout` | 세션 클리어 후 `/login` 으로 | 공개 |
| GET | `/` | 통합 대시보드 | 필요 |
| GET | `/files` | Log File Download 페이지 | 필요 |
| GET | `/files/check` | 파일 존재 확인 (JSON) | 필요 |
| GET | `/files/download` | 파일 다운로드 | 필요 |
| GET | `/vnand` | VNAND DB 페이지 | 필요 |
| GET | `/vnand/query/{query_id}` | 쿼리 실행 (JSON) | 필요 |
| GET | `/dram` | DRAM DB 페이지 | 필요 |
| GET | `/dram/query/{query_id}` | 쿼리 실행 (JSON) | 필요 |
| GET | `/es` | Elasticsearch 페이지 | 필요 |
| GET | `/es/query/{query_id}` | DSL 실행 (JSON) | 필요 |
| GET | `/api/logs` | 인메모리 로그 폴링 | 필요 (XHR이면 401) |
| GET | `/static/*` | 정적 자원 | 공개 |

## 8. 새 기능을 추가할 때의 결정 트리

```
새 SQL 쿼리 하나 추가?
  → app/queries/<source>_queries.py 의 QUERIES 에 SqlQueryDef 항목 추가. 끝.
     - show_in_dashboard=True 면 통합 대시보드 후보 (단 현재 home.py 는
       DASHBOARD_CARDS 로 직접 enumerate 하는 구조이므로 카드 추가는 home.py 수정 필요)

새 데이터 소스(예: 다른 MariaDB) 추가?
  → repositories/, services/, queries/, routers/ 각각에 비슷한 모듈을 추가하고
     _templating.py 의 NAV_ITEMS 에 새 항목을 한 줄 추가.

새 페이지(쿼리 결과가 아닌 일반 페이지) 추가?
  → routers/<name>.py 만들고 templates/<name>.html 추가.
     사이드바에 노출하려면 NAV_ITEMS 에 추가.
     보호된 경로면 PUBLIC_PATH_PREFIXES 는 건드리지 말 것 (기본 보호됨).

차트 카드 동작 수정?
  → DASHBOARD.md 의 "수정 포인트 표" 부터 확인.

인증 정책 수정 (예: 다중 사용자, OAuth)?
  → AUTH.md 의 "확장 가이드" 섹션 참조.
```

## 9. 핵심 의사결정 메모

- **단일 비밀번호 인증**: 사내 인하우스 도구 + 사용자 식별 불필요라는 요구로 출발.
  추후 SSO/OAuth 로 갈 때는 `is_authenticated()` 의 판정만 교체하면 되도록 분리되어 있음.
- **클라이언트 사이드 그룹핑**: `recent_parsing_results` 의 raw row 를 그대로 내려주고
  PRODUCT × 일자 그룹핑은 JS 에서 수행. 같은 raw 응답을 여러 차트가 재사용 가능하고,
  쿼리 정의(서버) 단순화. 행 수가 만 단위 이상이면 서버 사이드 집계로 옮길 것.
- **Chart.js 로컬 번들**: 사내망 오프라인 가능성 + 버전 고정 위해 CDN 미사용.
- **LIFO 미들웨어 등록 순서**: `auth → session` 순으로 add 하여 session 이 외곽이 되도록.
  순서를 뒤집으면 auth 안에서 `request.session` 사용 시 AssertionError 발생.

## 10. 관련 문서

- 인증 상세: [AUTH.md](./AUTH.md)
- 차트 카드 / 메트릭 그룹: [DASHBOARD.md](./DASHBOARD.md)
- 쿼리 정의/추가: [QUERY_SYSTEM.md](./QUERY_SYSTEM.md)
- 프론트엔드 클래스: [FRONTEND.md](./FRONTEND.md)
- 실행/배포: [DEVELOPMENT.md](./DEVELOPMENT.md)
- 변경 이력: [CHANGELOG.md](./CHANGELOG.md)

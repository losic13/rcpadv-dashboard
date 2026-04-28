# Recipe Advisor Site Reliability Dashboard — 문서

VNAND DB / DRAM DB (MariaDB) / Elasticsearch 데이터를 한 곳에서 조회하고,
파싱 결과를 차트로 시각화하는 인하우스 대시보드의 설계/구현 문서입니다.

> 본 문서 셋은 **사람**과 **Claude 4.7 Sonnet** 등 LLM 코딩 에이전트 모두가
> 프로젝트의 의사결정 배경, 모듈 책임, 핵심 동작을 빠르게 파악할 수 있도록
> 작성되었습니다. 새로운 작업을 시작하기 전 관련 문서를 먼저 읽기를 권장합니다.

## 문서 색인

| 문서 | 다루는 범위 | 누구에게 |
|------|------------|----------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 디렉토리 구조, 계층 책임, 요청 흐름, 미들웨어 체인 | 백엔드 작업자 / 신규 합류자 |
| [AUTH.md](./AUTH.md) | 단일 비밀번호 + 서명 쿠키 세션 인증, 미들웨어 동작 | 인증/배포 담당 |
| [DASHBOARD.md](./DASHBOARD.md) | 통합 대시보드 차트 카드 — 메트릭 그룹, 이동평균, 색상 팔레트 | 프론트엔드/UX 작업자 |
| [QUERY_SYSTEM.md](./QUERY_SYSTEM.md) | VNAND/DRAM/ES 쿼리 정의 방식, `recent_parsing_results` 계약 | 쿼리 추가 담당 |
| [FRONTEND.md](./FRONTEND.md) | `QueryRunner` / `ChartCard` / `Toast` / `LogPanel` 클래스 | JS 작업자 |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | 로컬 실행, 환경 변수, 테스트, 배포 절차 | 개발/운영 |
| [CHANGELOG.md](./CHANGELOG.md) | PR #1 ~ #12 이력과 의사결정 메모 | 모두 |

## 30초 요약

- **Backend**: FastAPI + Uvicorn (Python 3.11+, uv 패키지 관리)
- **Frontend**: Jinja2 SSR + Bootstrap 5 + DataTables + Chart.js (UMD 로컬 번들) + 순수 fetch JS
- **Data**: MariaDB(VNAND/DRAM, SQLAlchemy 풀) + Elasticsearch 8.x
- **인증**: 단일 `APP_PASSWORD` + Starlette SessionMiddleware(서명된 쿠키)
- **차트**: 카드(VNAND/DRAM) > 메트릭 섹션(REGULAR/COMPLETE) > PRODUCT 별 막대 + 이동평균선(마지막 데이터 제외)
- **쿼리 추가**: `app/queries/<source>_queries.py` 의 `QUERIES` 딕셔너리에 `SqlQueryDef` 한 줄 추가하면 끝

## 핵심 설계 원칙

1. **얇은 라우터, 두꺼운 서비스**: 라우터는 URL 매핑/템플릿 렌더링만 담당. 비즈니스 로직은 `services/` 에 둔다.
2. **쿼리 추가는 한 곳에서만**: `queries/<source>_queries.py` 만 수정하면 사이드바/탭/대시보드에 자동 반영.
3. **레이스 컨디션 방어 + 가시화**: 자동 갱신/탭 전환 시 in-flight 요청을 `AbortController` 로 취소하고, 사용자가 그것을 *알 수 있도록* 배지/토스트/누적 카운터로 표시.
4. **일관된 차트 카드 패턴**: `QueryRunner` 와 동일한 race-UI 패턴을 `ChartCard` 가 그대로 채택.
5. **공개/비공개 경로의 명시적 분리**: `/login`, `/logout`, `/static/`, `/favicon` 만 미인증 통과. 그 외 HTML 은 303 → `/login`, JSON/XHR 은 401.

## 디렉토리 한눈에 보기

```
webapp/
├── app/
│   ├── main.py                  # FastAPI 부트스트랩 + 미들웨어
│   ├── config.py                # .env → Settings (pydantic-settings)
│   ├── logger.py                # 파일/콘솔/인메모리(로그 패널용) 핸들러
│   ├── routers/                 # URL 라우팅 (얇음)
│   │   ├── auth.py              # /login, /logout
│   │   ├── home.py              # / 통합 대시보드
│   │   ├── files.py             # /files Log File Download
│   │   ├── vnand.py / dram.py   # MariaDB 소스
│   │   ├── es.py                # Elasticsearch
│   │   ├── logs.py              # /api/logs 인메모리 로그 폴링
│   │   └── _templating.py       # Jinja2Templates 공유 인스턴스 + NAV_ITEMS
│   ├── services/                # 비즈니스 로직 (쿼리 실행/가공)
│   ├── repositories/            # DB/ES 커넥션 + execute()
│   ├── queries/                 # 쿼리 상수 정의 (SqlQueryDef / EsQueryDef)
│   ├── templates/               # Jinja2 템플릿 (base, _sidebar, login, home, source_page, files, _log_panel)
│   └── static/                  # CSS / JS / 벤더(jquery, bootstrap, datatables, chartjs)
├── docs/                        # ← 본 문서 셋
├── logs/                        # RotatingFileHandler 출력
├── .env.example
├── pyproject.toml / uv.lock
└── run.sh                       # nohup 운영 스크립트
```

## 빠른 시작

```bash
# 의존성 설치
uv sync

# .env 작성 (APP_PASSWORD, SESSION_SECRET_KEY 는 반드시 운영 값으로 교체)
cp .env.example .env

# 실행
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

브라우저: `http://<서버>:8000/` → 비밀번호 입력 → 통합 대시보드.

자세한 절차/환경 변수/배포는 [DEVELOPMENT.md](./DEVELOPMENT.md) 참조.

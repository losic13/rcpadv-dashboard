# 개발/운영 가이드

본 문서는 로컬 환경 셋업, 환경 변수, 실행 옵션, 배포, 그리고 흔한 운영 트러블슈팅을 정리합니다.

## 1. 사전 요구사항

| 항목 | 버전 |
|------|------|
| Python | 3.11 이상 (`pyproject.toml`: `requires-python = ">=3.11"`) |
| uv | 최신 (`curl -LsSf https://astral.sh/uv/install.sh \| sh`) |
| OS | Linux (운영) / macOS (개발) — Windows 는 `run.sh` 미지원, uvicorn 직접 실행 |
| MariaDB | VNAND/DRAM 두 인스턴스에 readonly 사용자 |
| Elasticsearch | 8.x (인덱스 접근 권한 readonly 권장) |

## 2. 로컬 셋업

```bash
# 1) 저장소 클론
git clone https://github.com/losic13/rcpadv-dashboard.git
cd rcpadv-dashboard

# 2) 의존성 설치 (uv 가 .venv 를 자동 생성/관리)
uv sync

# 3) 환경 변수 파일
cp .env.example .env
vi .env       # APP_PASSWORD, SESSION_SECRET_KEY, DB/ES 접속 정보 입력

# 4) 실행
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
# 또는
uv run python -m app.main
# 또는 (운영)
./run.sh start
```

## 3. 환경 변수 (`.env`)

`app/config.py` 의 `Settings` 클래스가 자동 로드합니다 (`pydantic-settings`).

### 3.1 App

| 키 | 기본값 | 설명 |
|----|--------|------|
| `APP_HOST` | `0.0.0.0` | uvicorn 바인딩 호스트 |
| `APP_PORT` | `8000` | 포트 |
| `QUERY_TIMEOUT_SECONDS` | `600` | SQL/ES 쿼리 타임아웃 (10분) |

### 3.2 인증 (PR #12)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `APP_PASSWORD` | `changeme` | **운영 시 반드시 변경** |
| `SESSION_SECRET_KEY` | `dev-only-secret-please-override-in-env` | **운영 시 반드시 변경** (32바이트 이상 랜덤) |
| `SESSION_MAX_AGE` | `43200` (12h) | 세션 유효 시간(초) |
| `SESSION_COOKIE_NAME` | `rcpadv_session` | 세션 쿠키 이름 |

랜덤 시크릿 생성 예:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3.3 VNAND DB

| 키 | 예시 |
|----|------|
| `VNAND_DB_HOST` | `10.0.0.11` |
| `VNAND_DB_PORT` | `3306` |
| `VNAND_DB_USER` | `readonly` |
| `VNAND_DB_PASSWORD` | (사내 비밀번호) |
| `VNAND_DB_NAME` | `vnand` |

### 3.4 DRAM DB

`DRAM_DB_*` 동일 구조. `DRAM_DB_HOST=10.0.0.12` 등.

### 3.5 Elasticsearch

| 키 | 예시 |
|----|------|
| `ES_HOSTS` | `http://10.0.0.20:9200` (콤마로 다중: `http://es1:9200,http://es2:9200`) |
| `ES_USERNAME` | `elastic` |
| `ES_PASSWORD` | (사내 비밀번호) |
| `ES_VERIFY_CERTS` | `false` (사내 자체 서명 인증서 환경) |

### 3.6 로깅

| 키 | 기본값 |
|----|--------|
| `LOG_LEVEL` | `INFO` |
| `LOG_FILE` | `logs/app.log` |
| `LOG_BUFFER_SIZE` | `500` (인메모리 deque maxlen) |

## 4. 실행 옵션

### 4.1 uvicorn 직접

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
# 개발용 reload
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2 모듈 단독 실행

```bash
uv run python -m app.main
```

`main.py` 의 `if __name__ == "__main__":` 블록이 `uvicorn.run(app, host=..., port=...)` 을
호출. `.env` 의 `APP_HOST`/`APP_PORT` 사용.

### 4.3 nohup 운영 스크립트

```bash
./run.sh start      # 백그라운드 기동, PID 파일 기록
./run.sh stop
./run.sh restart
./run.sh status
```

내부적으로 `nohup uv run uvicorn ...` 호출 후 표준출력/에러를 `logs/` 로 리다이렉트.

## 5. 정적 자원 / 벤더 라이브러리

CDN 의존 없이 모두 `app/static/vendor/` 안에 보관됩니다 — 사내망/오프라인 환경 대응.

```
app/static/vendor/
├── bootstrap/    bootstrap.min.css, bootstrap.bundle.min.js
├── jquery/       jquery.min.js
├── datatables/   datatables.min.css, datatables.min.js
└── chartjs/      chart.umd.min.js   (v4.4.4 UMD, PR #10)
```

> 버전 업그레이드 시 동일 위치에 파일 교체 후 `base.html` 의 `<script>` 태그가
> 그대로 동작하는지 확인. CDN 으로 회귀하지 마세요.

## 6. 새 쿼리/카드 추가

상세 절차는 [QUERY_SYSTEM.md](./QUERY_SYSTEM.md) 참조. 요약:

1. 새 SQL 쿼리: `app/queries/<source>_queries.py` 의 `QUERIES` 에 1줄.
2. 사이드바/탭에 자동 노출 — 추가 작업 없음.
3. 통합 대시보드 카드로 추가하려면 `app/routers/home.py` 의 `DASHBOARD_CARDS` 도 수정.

## 7. 검증 / 스모크 테스트

`pytest` 등 자동 테스트는 현재 미구성. 로컬 검증은 다음 패턴을 사용합니다.

### 7.1 import 체크

```bash
cd /home/user/webapp
uv run python -c "from app.main import app; print(len(app.routes))"
# 16
```

### 7.2 JS 문법 검증

```bash
node -e "const fs=require('fs'); new Function(fs.readFileSync('app/static/js/app.js','utf-8')); console.log('ok')"
```

### 7.3 라우트 스모크 테스트

```bash
PORT=8000
# 미인증 — 보호된 페이지 → 303
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:$PORT/
# 미인증 XHR — /api/logs → 401
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Requested-With: XMLHttpRequest" http://127.0.0.1:$PORT/api/logs
# 잘못된 비밀번호 → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:$PORT/login -d "password=wrong&next=/"
# 올바른 비밀번호 → 303 + Set-Cookie
curl -s -i -c /tmp/cj.txt -X POST http://127.0.0.1:$PORT/login -d "password=changeme&next=/" | head -10
# 쿠키로 보호된 경로 → 200
for p in / /vnand /dram /es /files /api/logs; do
  echo -n "$p → "; curl -s -o /dev/null -w "%{http_code}\n" -b /tmp/cj.txt http://127.0.0.1:$PORT$p
done
```

전체 정상 응답 매트릭스:

| 시나리오 | / | /vnand | /dram | /es | /files | /api/logs |
|---------|---|--------|-------|-----|--------|-----------|
| 미인증 (브라우저) | 303 | 303 | 303 | 303 | 303 | 303 |
| 미인증 (XHR) | 303 | 303 | 303 | 303 | 303 | 401 |
| 인증 후 | 200 | 200 | 200 | 200 | 200 | 200 |

## 8. 운영 배포 체크리스트

- [ ] `.env` 의 `APP_PASSWORD` 를 운영 비밀번호로 교체
- [ ] `.env` 의 `SESSION_SECRET_KEY` 를 32바이트 이상 랜덤 문자열로 교체
- [ ] DB readonly 계정의 비밀번호 적용
- [ ] ES 인증 정보 적용
- [ ] `LOG_FILE` 디스크 공간 확보 (RotatingFileHandler 10MB × 5 = 약 50MB)
- [ ] (HTTPS 환경이면) `app/main.py` 의 `SessionMiddleware(https_only=True)` 변경 검토
- [ ] 리버스 프록시(nginx 등) 가 `Set-Cookie`, `Cookie` 헤더를 그대로 전달하는지 확인
- [ ] 방화벽: `APP_PORT` 만 노출, DB/ES 포트는 차단
- [ ] `run.sh start` 가 systemd 서비스 등으로 부트 시 자동 재시작되도록 등록 (선택)

## 9. 로그 / 모니터링

- 파일 로그: `logs/app.log` (회전됨, 최대 5개 보존). `tail -f logs/app.log` 로 실시간 관찰.
- UI 로그 패널: 인증 후 화면 하단의 "로그" 패널 (접기/펼치기). 인메모리 최근 500개.
- 핵심 로그 라인 패턴:
  - `[router.vnand] 쿼리 실행 시작: ...`
  - `[service.sql] [vnand] 쿼리 완료: recent_parsing_results (1234행, 87ms)`
  - `[app.routers.auth] 로그인 성공 from 127.0.0.1`
  - `[app.routers.auth] 로그인 실패 (잘못된 비밀번호) from 127.0.0.1`
- uvicorn access log 는 잡음을 줄이기 위해 `WARNING` 으로 강제 (`logger.py`).
- 외부 모니터링 연동이 필요하면 `RotatingFileHandler` 와 별도로 syslog/journald handler 를
  추가하세요.

## 10. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|------------|
| `ModuleNotFoundError: app` | cwd 가 webapp 루트가 아님. `cd webapp && uv run ...` 또는 `main.py` 가 자동 보정하므로 그대로 실행 가능. |
| `address already in use` | 동일 포트의 이전 프로세스 미종료. `./run.sh stop` 또는 `lsof -i :8000` → kill. |
| `OperationalError: ... Lost connection` | DB 풀 좀비 커넥션. `pool_pre_ping=True` 가 켜져 있으니 재시도하면 정상. 빈도가 높으면 `pool_recycle` 단축. |
| 페이지 로드만 되고 데이터가 안 들어옴 | DevTools Network 에서 `/{source}/query/...` 응답 확인. 401 이면 세션 만료, 504 면 쿼리 타임아웃, 500 이면 SQL 오류. 응답 JSON 의 `detail` 메시지 확인. |
| 차트가 안 그려짐 | 콘솔에 `Chart is not defined` 가 있으면 `chart.umd.min.js` 로드 실패. `/static/vendor/chartjs/chart.umd.min.js` 가 200 인지 확인. |
| 로그아웃이 안 됨 | 사이드바 로그아웃은 `<form method="post" action="/logout">`. CSP/프록시가 POST 를 막지 않는지 확인. GET `/logout` 도 동일 동작. |

## 11. 의존성 업데이트

```bash
uv lock --upgrade            # 모든 패키지 최신 호환 버전으로
uv lock --upgrade-package fastapi   # 특정 패키지만
uv sync                       # lock 적용
```

## 12. 코드 스타일

- Python: 표준 라이브러리 + FastAPI 컨벤션. 라우터는 얇게, 서비스는 두껍게.
- JS: IIFE + ES2020 + 명시적 `data-role` 셀렉터. 페이지별 특수 분기 금지.
- HTML: 시맨틱 태그(`<aside>`, `<main>`, `<section>`, `<header>`) 우선.
- CSS: BEM-lite (`.metric-section-regular`, `.legend-item` 등) + 커스텀 프로퍼티(`--color-brand-...`).

## 13. 관련 문서

- 시스템 아키텍처: [ARCHITECTURE.md](./ARCHITECTURE.md)
- 인증: [AUTH.md](./AUTH.md)
- 차트 카드 설계: [DASHBOARD.md](./DASHBOARD.md)
- 쿼리 추가: [QUERY_SYSTEM.md](./QUERY_SYSTEM.md)
- 프론트엔드 클래스: [FRONTEND.md](./FRONTEND.md)
- 변경 이력: [CHANGELOG.md](./CHANGELOG.md)

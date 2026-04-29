# 다른 Claude Code / LLM 에이전트에게 — 입문 가이드

> **목적**: 이 저장소에 새로 투입된 Claude Code (또는 다른 코딩 LLM) 가
> "어디부터 읽어야 하는지", "어떤 패턴/금기를 따라야 하는지", "최근 어떤
> 흐름으로 작업이 진행됐는지" 를 5–10분 안에 따라잡도록 작성된 문서입니다.
>
> 이전 세션의 **결과물(코드)** 만 보면 *왜 그렇게 했는지* 가 사라집니다. 본 문서는
> **의사결정 맥락** 을 짧게 압축해서 넘겨주기 위한 핸드오프입니다.

## 0. 한 줄 요약

이건 **VNAND DB / DRAM DB (MariaDB) + Elasticsearch + 로그파일 검색** 을 한
페이지에서 둘러보고, **파싱 처리량 + AMAT 비정상 스텝 + 오늘 접속자수** 를
대시보드 카드로 요약하는 사내 운영 도구입니다. FastAPI(Python 3.11) + Jinja2
SSR + 단일 `app.js` 번들. 단일 비밀번호 + 서명 쿠키 세션 인증.

## 1. 처음 5분 — 무엇부터 읽나

순서대로:

1. **[README.md](./README.md)** — 30초 요약 + 디렉토리 + 빠른 시작.
2. **[ARCHITECTURE.md](./ARCHITECTURE.md)** — 계층(Router → Service → Repository → Query) + 요청 흐름.
3. **[CHANGELOG.md](./CHANGELOG.md)** — **반드시 최상단부터 5–10개 PR을 훑을 것.** 최근 의사결정의 이유가 모두 여기 있다.
4. 그 다음은 작업 영역에 맞춰:
   - 통합 대시보드 카드 → [DASHBOARD.md](./DASHBOARD.md)
   - JS 클래스 / `LoginTodayCard` / `CountCard` → [FRONTEND.md](./FRONTEND.md)
   - 쿼리 추가/수정 → [QUERY_SYSTEM.md](./QUERY_SYSTEM.md)
   - Client 접속 이력 페이지 → [LOGIN_HISTORY.md](./LOGIN_HISTORY.md)
   - Log Search 페이지 → [LOG_SEARCH.md](./LOG_SEARCH.md)
   - EQP I/F (iframe) → [EQP_IF.md](./EQP_IF.md)
   - Chrome DevTools 404 / `/.well-known/` → [WELL_KNOWN.md](./WELL_KNOWN.md)
   - 인증/세션 → [AUTH.md](./AUTH.md)
   - 로컬 실행/배포 → [DEVELOPMENT.md](./DEVELOPMENT.md)

## 2. 절대 어기지 말 것 (Hard rules)

이 프로젝트는 운영 중인 사내 도구입니다. 아래는 회귀 사고 방지를 위한 **하드 룰**
이니, 변경하려면 반드시 PR 본문에 근거를 적고 사용자에게 컨펌을 받으세요.

1. **얇은 라우터, 두꺼운 서비스**.
   - `app/routers/*.py` 는 URL 매핑/템플릿 렌더/응답 직렬화만 담당.
   - 비즈니스 로직(쿼리 실행/가공/필터링)은 전부 `app/services/*_service.py` 로.
2. **쿼리 추가는 한 곳에서만**.
   - `app/queries/<source>_queries.py` 의 `QUERIES` 딕셔너리에 `SqlQueryDef`/`EsQueryDef`
     를 *한 줄* 추가하면 사이드바·탭·라우팅이 자동 반영. 라우터/템플릿 수정 금지.
3. **인증 우회 경로는 화이트리스트로만**.
   - `app/routers/auth.py::PUBLIC_PATH_PREFIXES` 가 단일 진실. 새 `/login` 류
     공개 경로가 필요하면 여기 추가하고, 그 외 *어떤 경로도* 미인증으로 열지 않는다.
4. **레이스(Race) 방어 + 가시화 패턴 유지**.
   - 차트/카드/테이블의 자동 갱신은 `_runToken` + `AbortController` + `취소 ×N` 배지
     + 토스트의 4종 세트로 구현되어 있다. 새 카드 만들면 동일 패턴을 따를 것.
5. **DataTables 한국어화는 `DATATABLES_KO` 상수를 통해서만**.
6. **자산 캐시버스팅은 `_compute_asset_version()` 으로 자동**.
   - 정적 자원(`app/static/...`) 의 mtime 기반 짧은 해시가 모든 `<link>`/`<script>`
     의 `?v=` 에 자동 부착. 수동 버전 표기 금지.
7. **민감 데이터는 로그에 남기지 않는다**.
   - 비밀번호 비교 실패 로그도 입력값을 출력하지 않는다(`hmac.compare_digest`).
8. **PR 단위로 commit + push + PR + merge**.
   - 작업이 멈추기 전에는 절대 dirty working tree 로 두지 말 것.
   - 한 PR 안에서는 여러 incremental commit 을 squash 하여 단일 commit 으로 머지.

## 3. 작업 흐름 (Operational loop)

```
1) 사용자 요청 분해 → TodoWrite 로 작업 목록 작성
2) 관련 docs/ 파일과 대상 코드 read (Glob/Grep 우선)
3) 변경 (Edit / MultiEdit) — 한 번에 한 가지 책임만
4) 즉시 sanity check
   - python -m py_compile app/**/*.py
   - python -c "from jinja2 import Environment, FileSystemLoader; ..."
   - node -e "new Function(fs.readFileSync('app/static/js/app.js','utf8'))"
   - 가능하면 Python TestClient 로 / , /login-history/today 호출
5) git add -A && git commit  (한 커밋 = 한 책임)
6) git fetch origin main && git rebase origin/main  (충돌 시 remote 우선)
7) (필요 시) squash: git reset --soft origin/main && git commit
8) git push -f origin genspark_ai_developer
9) gh pr create / gh pr edit  → 사용자에게 PR URL 공유
10) gh pr merge --squash 후 main 동기화 (genspark_ai_developer 리셋)
```

> 자세한 명령은 본 시스템 프롬프트의 GenSpark Project Workflow 섹션 참고.

## 4. 코드 지도 — 어디를 보면 되나

```
사용자 요청 유형                       → 우선 봐야 하는 파일
──────────────────────────────────────────────────────────────────
사이드바 메뉴 추가/이름변경/숨김      → app/routers/_templating.py (NAV_ITEMS / NAV_ITEMS_HIDDEN)
새 페이지(라우트) 추가                → app/routers/<new>.py + app/main.py include_router
새 SQL 쿼리 추가                       → app/queries/<source>_queries.py 의 QUERIES dict
새 ES 쿼리 추가                        → app/queries/es_queries.py 의 QUERIES dict
대시보드 카드 추가/제거/순서          → app/routers/home.py 의 DASHBOARD_CARDS
대시보드 카드 마크업                   → app/templates/home.html (chart_card / count_card / login_today)
JS 차트 동작                           → app/static/js/app.js 의 ChartCard
JS 카운트 카드 동작                    → app/static/js/app.js 의 CountCard
JS 오늘 접속자수 카드 동작             → app/static/js/app.js 의 LoginTodayCard
스타일                                 → app/static/css/app.css
인증/세션                              → app/routers/auth.py + app/main.py SessionMiddleware
환경 변수 / 기본값                     → app/config.py (Settings 클래스)
DB 커넥션 / 풀                         → app/repositories/_base.py (또는 sql 러너)
ES 커넥션                              → app/repositories/es_repository.py
로그(콘솔/파일/패널 폴링)              → app/logger.py + app/routers/logs.py
```

## 5. 자주 하는 실수 — 미리 막기

- ❌ **라우터에서 SQL 직접 실행** — 서비스 레이어로 빼기.
- ❌ **`title="..."` HTML 속성으로 새 정보 노출** — 폰트/색 제어 불가, `?` cursor 변경. 커스텀 hover panel 사용 (예: `.login-today-tip`).
- ❌ **`date.today()` 를 그대로 KST 가정** — 서버가 UTC 면 새벽에 일자가 어긋난다. PR #29/#31 노트 참고.
- ❌ **새 정적 자원에 수동 `?v=...`** — `_compute_asset_version()` 의 `_STATIC_FILES_FOR_HASH` 에 추가만 하면 자동.
- ❌ **HTML innerHTML 에 사용자 입력 직삽입** — `escapeHtml()` 또는 `textContent` 사용.
- ❌ **Chart.js 인스턴스 매번 destroy/new** — `_upsertMetricChart` 가 `update('none')` 으로 깜빡임 최소화. 같은 슬롯에 재사용.
- ❌ **새 카드에서 in-flight 요청을 무시** — race-UI 4종 세트 미적용 시 자동 갱신이 망가진다.

## 6. 최근 흐름 (2026-04 기준 한 페이지 요약)

> 자세한 PR 별 결정 근거는 [CHANGELOG.md](./CHANGELOG.md) 참고. 아래는 *제일 최근 흐름* 만.

- **PR #14**: 일평균(마지막 제외) 통계 + MA 색 재조정 + DataTables 툴바 정리 → 첫 docs 셋(8종) 추가.
- **PR #17**: 통합 대시보드에 **CountCard** 추가 (DRAM `amat_abnormal_steps_no_treat`).
- **PR #18**: count/chart 카드가 새로고침 안 되던 문제 → 자산 캐시버스팅 + 카드 초기화 격리.
- **PR #19~20**: **Log Search** 페이지 신규 + File Download 리네이밍 / **EQP I/F Manager** iframe 신규.
- **PR #24~26**: **사용자 접속 이력** 페이지 신규 + 누적막대 + 개발자 ID 토글 hover + Y축 동기화.
- **PR #27~29**: 통합 대시보드에 **오늘 접속자수 카드** 추가 → 두 장(전체/고객) → 한 장 통합 + 카드 순서 변경 + KST 일자 버그 수정.
- **PR #30**: `/.well-known/appspecific/com.chrome.devtools.json` 204 응답으로 콘솔 noise 제거.
- **PR #31**: `CONVERT_TZ` 제거 (DB·서버 타임존이 이미 KST 정책이라).
- **PR #32**: 오늘 접속자수 카드의 `?` 커서/기본 툴팁 제거 → **접속자 ID Top 10 hover 패널** 도입.
- **PR #33**: AMAT 카드 부제 단순화 + 일평균 정수화·X축 아래 이동 + **사용자 접속 이력 → Client 접속 이력** 리네이밍 + 라벨(전체→총, 고객→고객) 폭 정렬.

## 7. 한국어 / 영어 / 코드네이밍 규약

- **사용자에게 보이는 텍스트**: 한국어 우선. 단, 제품명·사이트 분류(`Client`, `EQP I/F`)는 영문 표기 유지.
- **커밋 메시지**: 한국어 본문 + Conventional Commits prefix (`feat:`, `fix:`, `refactor:`, `style:`, `docs:`, `chore:`). 본 저장소는 한국어 커밋 메시지를 그대로 사용.
- **PR 제목/본문**: 한국어. 변경 사항/검증/롤백 영향을 bullet 으로.
- **코드 식별자(클래스/함수/변수)**: 영문 snake_case (Python), camelCase (JS), `data-role="..."` 는 kebab-case.
- **CSS 클래스**: kebab-case + BEM-스러운 네임스페이스 (`login-today-*`, `metric-section-*`, `lh-chart-*`).

## 8. 이 문서 자체를 갱신해야 하는 시점

다음 중 하나라도 발생하면 본 문서를 갱신:
- 디렉토리 레이아웃 변경 (예: `app/repositories/` 추가)
- 새 핵심 클래스가 `app.js` 에 추가됨
- 인증 흐름이 바뀜 (예: SSO 도입)
- 사이드바 메뉴가 바뀜
- "절대 어기지 말 것" 룰이 추가/제거됨

CHANGELOG 는 PR 마다 자동으로 갱신해야 합니다.

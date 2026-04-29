"""FastAPI 앱 부트스트랩.

실행 방법:
    1) uvicorn 직접:   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
    2) 모듈 단독 실행:  uv run python -m app.main
    3) nohup 스크립트:  ./run.sh start
"""
import os
import sys

# ------------------------------------------------------------
# 실행 환경 보정 — 상대경로/패키지 경로 이슈 대응
#   - `python app/main.py` 처럼 직접 실행하거나, IDE 의 Run 버튼처럼
#     CWD 가 webapp 루트가 아닌 경우에도 `from app.xxx import ...` 가
#     올바르게 동작하도록 webapp 루트를 sys.path 에 추가한다.
# ------------------------------------------------------------
def _ensure_project_root_on_path() -> None:
    # 현재 작업 디렉토리(우선) + 이 파일의 부모의 부모(webapp 루트) 두 군데를 보장
    candidates = [
        os.path.abspath("."),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    ]
    for p in candidates:
        if p and p not in sys.path:
            sys.path.append(p)


_ensure_project_root_on_path()

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.logger import get_logger, setup_logging
from app.repositories import es_client, mariadb
from app.routers import (
    auth,
    dram,
    eqp_if,
    es,
    files,
    home,
    log_search,
    login_history,
    logs,
    vnand,
)
from app.routers.auth import is_authenticated, is_public_path

# ---- 로깅 초기화 (라우터 import 전에 호출되어도 무방하지만 일관성 위해 여기서) ----
setup_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("앱 시작 (host=%s, port=%s)", settings.APP_HOST, settings.APP_PORT)
    yield
    log.info("앱 종료 — 커넥션 정리 중...")
    mariadb.dispose_all()
    es_client.close()
    log.info("앱 종료 완료")


app = FastAPI(
    title="Recipe Advisor Site Reliability Dashboard",
    docs_url=None,        # 인하우스 도구 — Swagger 비공개
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# ---- 인증 미들웨어 ----
# Starlette 미들웨어는 등록 순서의 역순으로 wrap 된다(LIFO):
# 가장 늦게 add 된 것이 가장 바깥쪽. 따라서 SessionMiddleware 가 auth
# 미들웨어를 감싸도록 auth 를 먼저 등록하고, SessionMiddleware 를 뒤에 등록한다.
# 그래야 auth 미들웨어 안에서 request.session 이 사용 가능.
#
# 동작:
#   - 공개 경로(/login, /logout, /static/, /favicon)  → 그대로 통과
#   - 인증 OK                                          → 그대로 통과
#   - 미인증 + JSON/XHR 요청                           → 401 응답
#   - 미인증 + HTML 페이지                             → /login?next=<현재URL> 로 303
@app.middleware("http")
async def require_auth_middleware(request: Request, call_next):
    path = request.url.path
    if is_public_path(path):
        return await call_next(request)

    if is_authenticated(request):
        return await call_next(request)

    accept = request.headers.get("accept", "")
    is_xhr = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    if is_xhr or ("application/json" in accept and "text/html" not in accept):
        return JSONResponse(
            {"detail": "인증이 필요합니다. /login 에서 로그인하세요."},
            status_code=401,
        )

    qs = request.url.query
    nxt = path + (f"?{qs}" if qs else "")
    return RedirectResponse(url=f"/login?next={nxt}", status_code=303)


# ---- 세션(서명된 쿠키) ----
# auth 미들웨어보다 뒤에 등록하여 외곽 래퍼가 되도록 한다.
# itsdangerous 로 서명된 쿠키에 세션 저장. request.session 사용 가능.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    session_cookie=settings.SESSION_COOKIE_NAME,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",
    https_only=False,  # 사내 환경에서 http 도 허용
)


# ---- 정적 자원 ----
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---- 라우터 등록 ----
app.include_router(auth.router)   # /login, /logout (공개)
app.include_router(home.router)
app.include_router(login_history.router)
app.include_router(log_search.router)
app.include_router(files.router)
app.include_router(vnand.router)
app.include_router(dram.router)
app.include_router(es.router)     # 사이드바에는 숨김 (NAV_ITEMS_HIDDEN), 라우트는 유지
app.include_router(eqp_if.router)
app.include_router(logs.router)


# ============================================================
# 단독 실행 진입점
#   - `python -m app.main` 또는 IDE 에서 직접 Run 시 사용
#   - 운영 시에는 uvicorn 또는 run.sh 사용 권장
# ============================================================
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
    )

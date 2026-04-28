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
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logger import get_logger, setup_logging
from app.repositories import es_client, mariadb
from app.routers import dram, es, home, logs, vnand

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

# ---- 정적 자원 ----
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---- 라우터 등록 ----
app.include_router(home.router)
app.include_router(vnand.router)
app.include_router(dram.router)
app.include_router(es.router)
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

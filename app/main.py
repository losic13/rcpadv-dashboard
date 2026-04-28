"""FastAPI 앱 부트스트랩.

실행 방법:
    1) uvicorn 직접:   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
    2) 모듈 단독 실행:  uv run python -m app.main
    3) nohup 스크립트:  ./run.sh start
"""
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

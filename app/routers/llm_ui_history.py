"""LLM UI 사용 이력 페이지 / API.

라우트:
    GET /llm-ui-history          : 페이지 (입력 폼 + 막대 차트 2개)
    GET /llm-ui-history/run      : JSON API (start/end 받아 집계 결과 반환)

login_history 페이지(/login-history) 의 코드 구조를 그대로 따른다 — 데이터
소스만 MariaDB(VNAND) → PostgreSQL(LLM_PG) 로 바뀐 형태.

타임존 정책:
    DB 의 timestamp 값을 *그대로* 사용한다. 별도 변환을 하지 않으며, "오늘"
    도 단순히 서버 로컬 기준 date.today() (login_history 와 동일).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import llm_ui_service as svc

router = APIRouter(prefix="/llm-ui-history")
log = get_logger("router.llm_ui_history")


@router.get("")
def page(request: Request):
    today = date.today()
    start, end = svc.default_range(today=today, days=14)
    return templates.TemplateResponse(
        request,
        "llm_ui_history.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "llm_ui_history",
            "page_title": "LLM UI 사용 이력",
            "default_start": start.isoformat(),
            "default_end": end.isoformat(),
            "today": today.isoformat(),
        },
    )


@router.get("/run")
def run(
    start: str = Query(..., description="시작일 (YYYY-MM-DD, 포함)"),
    end: str = Query(..., description="종료일 (YYYY-MM-DD, 포함)"),
):
    try:
        s = svc.parse_date(start, label="시작")
        e = svc.parse_date(end, label="종료")
        svc.validate_range(s, e)
    except svc.InvalidRangeError as ex:
        raise HTTPException(status_code=400, detail=str(ex))

    try:
        return svc.fetch_history(s, e)
    except Exception as ex:
        log.exception("[llm_ui_history] 집계 실패: %s", ex)
        raise HTTPException(status_code=500, detail=f"집계 실패: {ex}")

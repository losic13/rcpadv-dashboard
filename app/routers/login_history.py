"""사용자 접속 이력 페이지 / API.

라우트:
    GET /login-history          : 페이지 (입력 폼 + 막대 차트 2개)
    GET /login-history/run      : JSON API (start/end 받아 집계 결과 반환)
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import login_history_service as svc

router = APIRouter(prefix="/login-history")
log = get_logger("router.login_history")


@router.get("")
def page(request: Request):
    today = date.today()
    start, end = svc.default_range(today=today, days=14)
    return templates.TemplateResponse(
        request,
        "login_history.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "login_history",
            "page_title": "사용자 접속 이력",
            "default_start": start.isoformat(),
            "default_end": end.isoformat(),
            "today": today.isoformat(),
        },
    )


@router.get("/run")
def run(
    start: str = Query(..., description="시작일 (YYYY-MM-DD, KST, 포함)"),
    end: str = Query(..., description="종료일 (YYYY-MM-DD, KST, 포함)"),
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
        log.exception("[login_history] 집계 실패: %s", ex)
        raise HTTPException(status_code=500, detail=f"집계 실패: {ex}")

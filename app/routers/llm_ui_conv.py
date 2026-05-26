"""LLM UI 사용 이력(대화 메시지) 페이지 / API.

라우트:
    GET /llm-ui-conversations       : 페이지 (탭 2종 - 타임라인/사용자별)
    GET /llm-ui-conversations/run   : JSON API (start/end 범위 → 두 뷰 페이로드)

llm_ui_history (접속 이력) 와 별개의 페이지이며, 같은 PostgreSQL 인스턴스
(``llm_pg``) 의 대화 메시지 테이블을 조회한다.

타임존 정책:
    DB 의 timestamp 값을 *그대로* 사용한다 (별도 변환 없음).
    "오늘" 은 서버 로컬 기준 ``date.today()``.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import llm_ui_conv_service as svc

router = APIRouter(prefix="/llm-ui-conversations")
log = get_logger("router.llm_ui_conv")


@router.get("")
def page(request: Request):
    today = date.today()
    start, end = svc.default_range(today=today, days=7)  # Q2=7일
    return templates.TemplateResponse(
        request,
        "llm_ui_conversations.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "llm_ui_conversations",
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
        return svc.fetch_conversations(s, e)
    except Exception as ex:
        log.exception("[llm_ui_conv] 집계 실패: %s", ex)
        raise HTTPException(status_code=500, detail=f"집계 실패: {ex}")

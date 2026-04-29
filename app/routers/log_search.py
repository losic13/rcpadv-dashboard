"""Log Search 페이지 / API.

라우트:
    GET  /log-search           : 페이지 (입력 폼 + 빈 DataTable)
    GET  /log-search/run?param=... : JSON API (검색 실행 결과)

다운로드는 기존 /files/download?path=... 를 그대로 재사용한다
(별도 엔드포인트 추가 없음).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import log_search_service

router = APIRouter(prefix="/log-search")
log = get_logger("router.log_search")


@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "log_search.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "log_search",
            "page_title": "Log Search",
            "search_column": log_search_service.SEARCH_COLUMN,
            "min_len": log_search_service.MIN_PARAM_LEN,
            "max_len": log_search_service.MAX_PARAM_LEN,
        },
    )


@router.get("/run")
async def run(
    param: str = Query(
        ...,
        description="검색 파라미터 (예: root_lot_wf_id 값)",
    ),
):
    """화이트리스트 쿼리들을 param 으로 병렬 실행하고 통합 결과를 반환."""
    try:
        normalized = log_search_service.validate_param(param)
    except log_search_service.InvalidParamError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await log_search_service.search_all(normalized)
    except Exception as e:
        log.exception("[log_search] 통합 검색 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"검색 실패: {e}")

    return result

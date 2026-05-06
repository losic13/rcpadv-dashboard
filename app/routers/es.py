"""Elasticsearch 페이지/API."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import es_service

router = APIRouter(prefix="/es")
log = get_logger("router.es")


# ── 기존: /es (소스 탭 페이지) ──────────────────────────────────────────
@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "source_page.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es",
            "page_title": es_service.SOURCE_LABEL,
            "source": es_service.SOURCE,
            "queries": es_service.list_queries(),
        },
    )


@router.get("/query/{query_id}")
async def run_query(query_id: str, request: Request):
    params = dict(request.query_params)
    try:
        result = await es_service.run(query_id, params)
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_id}")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"쿼리 실패: {e}")


# ── 신규: /es/overview (대상 로그 개요) ──────────────────────────────────
@router.get("/overview")
def overview_page(request: Request):
    """대상 로그 개요 페이지."""
    return templates.TemplateResponse(
        request,
        "es_overview.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_overview",
            "page_title": "대상 로그 개요",
        },
    )


@router.get("/overview/data/comparison")
async def overview_comparison(request: Request):
    """Section A API: index-1 vs index-2 날짜별 건수 비교."""
    result = await es_service.run_overview_comparison()
    status = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status)


@router.get("/overview/data/tkin")
async def overview_tkin(request: Request):
    """Section B API: index-2 tkin_time 최근 2주 날짜별 카운트."""
    result = await es_service.run_overview_tkin()
    status = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status)


# ── 준비 중 페이지들 (나중에 구현) ───────────────────────────────────────
@router.get("/targets")
def targets_page(request: Request):
    return templates.TemplateResponse(
        request,
        "es_stub.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_targets",
            "page_title": "대상 설비",
        },
    )


@router.get("/history")
def history_page(request: Request):
    return templates.TemplateResponse(
        request,
        "es_stub.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_history",
            "page_title": "종합 처리 이력",
        },
    )


@router.get("/delay")
def delay_page(request: Request):
    return templates.TemplateResponse(
        request,
        "es_stub.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_delay",
            "page_title": "처리 지연 상태",
        },
    )


@router.get("/anomaly")
def anomaly_page(request: Request):
    return templates.TemplateResponse(
        request,
        "es_stub.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_anomaly",
            "page_title": "이상 발생 현황",
        },
    )

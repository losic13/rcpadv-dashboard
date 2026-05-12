"""Elasticsearch 페이지/API."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import es_service

router = APIRouter(prefix="/es")
log = get_logger("router.es")


# ── Pydantic 모델: Document 조회 (POST body) ────────────────────────────
class DocumentLookupBody(BaseModel):
    """`POST /es/document/lookup` 요청 본문.

    - ids: 사용자가 입력한 _id 목록. 중복 제거 / 빈 값 제거는 서비스 레이어에서 수행.
    """
    ids: list[str] = Field(default_factory=list, description="조회할 _id 목록")


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


# ── 신규: /es/document (Document 조회 — _id terms 쿼리) ──────────────────
@router.get("/document")
def document_page(request: Request):
    """Document 조회 페이지 — _id 목록으로 parsing-index-2-* doc 조회."""
    return templates.TemplateResponse(
        request,
        "es_document.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_document",
            "page_title": "Document 조회",
            "lookup_index": es_service.DOCUMENT_LOOKUP_INDEX,
            "lookup_max_ids": es_service.DOCUMENT_LOOKUP_MAX_IDS,
        },
    )


@router.post("/document/lookup")
async def document_lookup(body: DocumentLookupBody):
    """_id terms 쿼리 실행. 빈 입력 / 한도 초과는 422 로 반환."""
    if not body.ids:
        raise HTTPException(status_code=422, detail="조회할 _id 가 비어 있습니다.")

    result = await es_service.run_document_lookup(body.ids)

    # 서비스에서 한도 초과 / 빈 입력 정규화 후 ok=False 로 떨어지면 422 매핑.
    if not result["ok"]:
        err = result.get("error") or "조회 실패"
        # 한도 초과 / 빈 입력은 client error
        if "최대" in err or "비어" in err:
            raise HTTPException(status_code=422, detail=err)
        # 타임아웃은 504
        if "타임아웃" in err:
            raise HTTPException(status_code=504, detail=err)
        # 그 외는 500
        raise HTTPException(status_code=500, detail=err)

    return JSONResponse(result)


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

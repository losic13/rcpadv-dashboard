"""Elasticsearch 페이지/API."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import es_service

router = APIRouter(prefix="/es")
log = get_logger("router.es")


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

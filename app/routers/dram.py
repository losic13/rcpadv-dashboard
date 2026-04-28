"""DRAM DB 페이지/API."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import dram_service

router = APIRouter(prefix="/dram")
log = get_logger("router.dram")


@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "source_page.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "dram",
            "page_title": dram_service.SOURCE_LABEL,
            "source": dram_service.SOURCE,
            "queries": dram_service.list_queries(),
        },
    )


@router.get("/query/{query_id}")
async def run_query(query_id: str, request: Request):
    params = dict(request.query_params)
    try:
        result = await dram_service.run(query_id, params)
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_id}")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"쿼리 실패: {e}")

"""VNAND DB 페이지/API."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import vnand_service

router = APIRouter(prefix="/vnand")
log = get_logger("router.vnand")


@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "source_page.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "vnand",
            "page_title": vnand_service.SOURCE_LABEL,
            "source": vnand_service.SOURCE,
            "queries": vnand_service.list_queries(),
        },
    )


@router.get("/query/{query_id}")
async def run_query(query_id: str, request: Request):
    # 쿼리 파라미터 그대로 전달 (필요 시에만 바인딩됨)
    params = dict(request.query_params)
    try:
        result = await vnand_service.run(query_id, params)
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_id}")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"쿼리 실패: {e}")

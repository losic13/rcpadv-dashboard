"""DRAM DB 페이지/API.

기존에는 AMAT 관련 탭 2개(Abnormal Step List, Keyword 관리)가 이 페이지에
포함되어 있었으나, PR ① 에서 /amat (AMAT 설비관리) 전용 페이지로 이전됨.
DRAM 페이지는 다시 "DRAM DB 단순 조회" 역할만 담당한다.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.routers._templating import NAV_ITEMS, templates
from app.services import dram_service

router = APIRouter(prefix="/dram")


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

"""통합 대시보드 페이지.

각 서비스에서 show_in_dashboard=True 인 쿼리들을 카드로 노출.
실제 데이터는 페이지 로드 후 JS 가 fetch 로 채움.
"""
from fastapi import APIRouter, Request

from app.routers._templating import NAV_ITEMS, templates
from app.services import dram_service, es_service, vnand_service

router = APIRouter()


@router.get("/")
def dashboard(request: Request):
    cards = []

    for q in vnand_service.list_dashboard_queries():
        cards.append({
            "source": vnand_service.SOURCE,
            "source_label": vnand_service.SOURCE_LABEL,
            "query_id": q.id,
            "title": q.title,
        })
    for q in dram_service.list_dashboard_queries():
        cards.append({
            "source": dram_service.SOURCE,
            "source_label": dram_service.SOURCE_LABEL,
            "query_id": q.id,
            "title": q.title,
        })
    for q in es_service.list_dashboard_queries():
        cards.append({
            "source": es_service.SOURCE,
            "source_label": es_service.SOURCE_LABEL,
            "query_id": q.id,
            "title": q.title,
        })

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "home",
            "cards": cards,
        },
    )

"""통합 대시보드 페이지.

VNAND DB / DRAM DB 의 `recent_parsing_results` 쿼리 결과를
PRODUCT 별로 분리해 차트(REGULAR / COMPLETE 상하 분리)로 시각화한다.

데이터는 페이지 로드 후 JS(ChartCard)가
  GET /{source}/query/recent_parsing_results
를 호출해 채운다. 라우터에서는 카드 메타 정보만 내려준다.
"""
from fastapi import APIRouter, Request

from app.routers._templating import NAV_ITEMS, templates

router = APIRouter()

# 통합 대시보드에 표시할 차트 카드 정의
#   - source       : 백엔드 라우트 prefix (vnand|dram)
#   - source_label : UI 배지/제목용
#   - query_id     : 차트 데이터를 가져올 쿼리 ID
#   - products     : 카드 안에서 분리해 그릴 PRODUCT 목록
DASHBOARD_CARDS = [
    {
        "source": "vnand",
        "source_label": "VNAND DB",
        "title": "VNAND 파싱 결과",
        "query_id": "recent_parsing_results",
        "products": ["LAM", "TEL"],
    },
    {
        "source": "dram",
        "source_label": "DRAM DB",
        "title": "DRAM 파싱 결과",
        "query_id": "recent_parsing_results",
        "products": ["AMAT", "LAM", "TEL"],
    },
]


@router.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "home",
            "cards": DASHBOARD_CARDS,
        },
    )

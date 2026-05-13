"""파서 처리 절차 페이지.

정적 페이지로, ``app/static/img/parser-flow/`` 폴더의 이미지 3장
(consume.png / preparse.png / fullparse.png) 을 카드 단위로
"접기/펴기" 가능한 형태로 보여준다.

이미지 파일 자체는 사용자가 직접 그려 같은 경로에 덮어쓰는 것으로
교체된다 — 이 라우터는 파일 존재 여부와 무관하게 같은 URL 을
참조하기만 한다. (브라우저 캐시 무효화를 위해 ``asset_version``
쿼리를 붙임.)
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates

router = APIRouter(prefix="/infra/parser-flow")
log = get_logger("router.parser_flow")


# ============================================================
# 페이지에 출력할 카드 정의
#
# 사용자가 description 만 한 곳에서 쉽게 수정할 수 있도록 라우터
# 모듈 상수로 분리. 향후 단계가 늘면 dict 만 추가하면 된다.
#
# image 경로는 /static/... 로 시작하는 절대 경로 — 템플릿에서
# 그대로 src 에 사용. 캐시 무효화는 base.html 의 ``asset_version``
# 이 처리한다.
# ============================================================
PARSER_FLOW_STEPS = [
    {
        "key":         "consume",
        "title":       "1. Consume",
        "description": "Kafka 등 메시지 큐에서 원본 로그를 수신하는 단계.",
        "image":       "/static/img/parser-flow/consume.png",
        "alt":         "Consume 단계 절차도",
    },
    {
        "key":         "preparse",
        "title":       "2. Pre-Parse",
        "description": "수신된 메시지를 사전 파싱하여 메타데이터를 추출하는 단계.",
        "image":       "/static/img/parser-flow/preparse.png",
        "alt":         "Pre-Parse 단계 절차도",
    },
    {
        "key":         "fullparse",
        "title":       "3. Full-Parse",
        "description": "전체 본문을 파싱하여 인덱싱에 사용할 필드를 구성하는 단계.",
        "image":       "/static/img/parser-flow/fullparse.png",
        "alt":         "Full-Parse 단계 절차도",
    },
]


# ============================================================
# 페이지  GET /infra/parser-flow
# ============================================================

@router.get("")
def page(request: Request):
    log.info("parser-flow 페이지 렌더링 (%d steps)", len(PARSER_FLOW_STEPS))
    return templates.TemplateResponse(
        request,
        "infra_parser_flow.html",
        {
            "nav_items":  NAV_ITEMS,
            "active_nav": "parser_flow",
            "page_title": "파서 처리 절차",
            "steps":      PARSER_FLOW_STEPS,
        },
    )

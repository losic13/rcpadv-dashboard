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

import textwrap

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
#
# ── description 작성 규칙 (줄바꿈 지원) ───────────────────────
# description 은 다음 세 가지 형태 모두 지원한다:
#
#   1) 한 줄 문자열:
#        "description": "한 줄짜리 설명입니다."
#
#   2) 여러 줄 문자열 — 일반 문자열에 \n 으로 줄바꿈:
#        "description": "첫째 줄\n둘째 줄\n셋째 줄"
#
#   3) Triple-quoted 멀티라인 문자열 (들여쓰기 OK):
#        "description": '''
#            첫째 줄
#            둘째 줄
#            셋째 줄
#        '''
#      → textwrap.dedent + strip 으로 공통 들여쓰기와 앞뒤 공백을
#        자동 정리.  결과적으로 들여쓴 코드도 깔끔하게 표시된다.
#
# 렌더 측(CSS .pf-card-desc) 은 white-space: pre-line 으로
# \n 을 실제 줄바꿈으로 출력한다.  Jinja 의 자동 이스케이프가
# 그대로 적용되므로 XSS 걱정 없이 사용자 입력 그대로 써도 안전.
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
        # 여러 줄 예시 (\n 직접 사용)
        "description": (
            "수신된 메시지를 사전 파싱하여 메타데이터를 추출하는 단계.\n"
            "필요한 필드만 미리 잘라내어 후속 단계의 비용을 줄인다."
        ),
        "image":       "/static/img/parser-flow/preparse.png",
        "alt":         "Pre-Parse 단계 절차도",
    },
    {
        "key":         "fullparse",
        "title":       "3. Full-Parse",
        # 여러 줄 예시 (triple-quoted, dedent 자동 적용)
        "description": """
            전체 본문을 파싱하여 인덱싱에 사용할 필드를 구성하는 단계.
            파싱 결과는 Elasticsearch 로 색인된다.
        """,
        "image":       "/static/img/parser-flow/fullparse.png",
        "alt":         "Full-Parse 단계 절차도",
    },
]


# ============================================================
# 내부 헬퍼 — description 정규화
# ============================================================

def _normalize_description(text: str) -> str:
    """description 문자열을 표시에 적합한 형태로 정규화한다.

    - ``textwrap.dedent`` 로 공통 들여쓰기 제거
      (triple-quoted 문자열을 들여써서 적어도 OK).
    - 앞뒤 공백/빈 줄 제거 (``strip``).
    - CRLF/CR 을 LF 로 통일 (혹시 모를 윈도 줄바꿈 방어).
    """
    if not text:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    s = textwrap.dedent(s)
    return s.strip()


def _prepared_steps() -> list[dict]:
    """``PARSER_FLOW_STEPS`` 각 step 의 description 을 정규화해 새 리스트로 반환.

    원본 상수는 그대로 두고 매 요청마다 정규화된 사본을 만들어 템플릿에
    전달한다. (모듈 import 시점에 한 번만 정규화해도 무방하지만,
    소스 수정 후 reload 시 즉시 반영되는 게 디버깅에 편하므로 함수형 유지.)
    """
    return [
        {**step, "description": _normalize_description(step.get("description", ""))}
        for step in PARSER_FLOW_STEPS
    ]


# ============================================================
# 페이지  GET /infra/parser-flow
# ============================================================

@router.get("")
def page(request: Request):
    steps = _prepared_steps()
    log.info("parser-flow 페이지 렌더링 (%d steps)", len(steps))
    return templates.TemplateResponse(
        request,
        "infra_parser_flow.html",
        {
            "nav_items":  NAV_ITEMS,
            "active_nav": "parser_flow",
            "page_title": "파서 처리 절차",
            "steps":      steps,
        },
    )

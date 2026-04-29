"""통합 대시보드 페이지.

카드 종류:
  - type="chart" : `recent_parsing_results` 쿼리 결과를 PRODUCT 별로 분리해
                   막대(REGULAR/COMPLETE 상·하) + 이동평균선으로 시각화.
  - type="count" : 임의 쿼리의 결과 행 수(row_count) 만 큰 숫자로 보여주는 카드.

데이터는 페이지 로드 후 JS 가
  GET /{source}/query/{query_id}
를 호출해 채운다. 라우터에서는 카드 메타 정보만 내려준다.
"""
from fastapi import APIRouter, Request

from app.routers._templating import NAV_ITEMS, templates

router = APIRouter()

# 통합 대시보드에 표시할 카드 정의
#   공통:
#     - type        : "chart" | "count"
#     - source      : 백엔드 라우트 prefix (vnand|dram|es)
#     - source_label: UI 배지/제목용
#     - query_id    : 호출할 쿼리 ID
#   chart 전용:
#     - products    : 카드 안에서 분리해 그릴 PRODUCT 목록
#   count 전용:
#     - unit        : 큰 숫자 옆 단위 (예: "건")
#     - description : 카드 본문 부가 설명
DASHBOARD_CARDS = [
    # 카드 표시 순서 (사용자 요청):
    #   ① VNAND 파싱 결과
    #   ② DRAM  파싱 결과
    #   ③ AMAT  비정상 스텝 (미처리)
    #   ④ 오늘 접속자수  (전체/고객 한 장에 통합)
    {
        "type": "chart",
        "source": "vnand",
        "source_label": "VNAND DB",
        "title": "VNAND 파싱 결과",
        "query_id": "recent_parsing_results",
        "products": ["LAM", "TEL"],
    },
    {
        "type": "chart",
        "source": "dram",
        "source_label": "DRAM DB",
        "title": "DRAM 파싱 결과",
        "query_id": "recent_parsing_results",
        "products": ["AMAT", "LAM", "TEL"],
    },
    {
        "type": "count",
        "source": "dram",
        "source_label": "DRAM DB",
        "title": "AMAT 비정상 스텝 (미처리)",
        "query_id": "amat_abnormal_steps_no_treat",
        "unit": "건",
        "description": "사용자 조치가 필요한 이상 감지 로그 건 수 입니다.",
    },
    # ─────────────────────────────────────────────────────
    # ④ 오늘 접속자수 카드 — "전체" / "고객" 을 한 카드 안에 같이 표시.
    #    * 데이터 소스: GET /login-history/today (단일 호출)
    #    * 큰 숫자 = 접속자(고유 사용자), 보조 = 총 로그인 횟수
    #      (사용자 요청: "접속자 수가 명확히 보이도록, 총 로그인은 참고만")
    #    * 이전 버전은 전체/고객을 두 장의 카드로 나란히 두었으나,
    #      "한 카드로 합치자" 는 요청에 따라 단일 카드 + 좌우 두 컬럼으로 변경.
    # ─────────────────────────────────────────────────────
    {
        "type": "login_today",
        "source": "login_history",
        "source_label": "VNAND DB",
        "title": "오늘 접속자수",
        "description": "오늘 0시 ~ 현재까지의 로그인 통계입니다.",
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

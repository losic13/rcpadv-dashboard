"""LLM UI 사용 이력 페이지 / API.

라우트:
    GET /llm-ui-history          : 페이지 (입력 폼 + 막대 차트 2개)
    GET /llm-ui-history/run      : JSON API (start/end 받아 집계 결과 반환)
    GET /llm-ui-history/today    : 통합 대시보드 'LLM 사용' 카드용 오늘 스냅샷

login_history 페이지(/login-history) 의 코드 구조를 그대로 따른다 — 데이터
소스만 MariaDB(VNAND) → PostgreSQL(LLM_PG) 로 바뀐 형태.

타임존 정책:
    DB 의 timestamp 값을 *그대로* 사용한다. 별도 변환을 하지 않으며, "오늘"
    도 단순히 서버 로컬 기준 date.today() (login_history 와 동일).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import llm_ui_service as svc

router = APIRouter(prefix="/llm-ui-history")
log = get_logger("router.llm_ui_history")


@router.get("")
def page(request: Request):
    today = date.today()
    start, end = svc.default_range(today=today, days=14)
    return templates.TemplateResponse(
        request,
        "llm_ui_history.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "llm_ui_history",
            "page_title": "LLM UI 사용 이력",
            "default_start": start.isoformat(),
            "default_end": end.isoformat(),
            "today": today.isoformat(),
        },
    )


@router.get("/run")
def run(
    start: str = Query(..., description="시작일 (YYYY-MM-DD, 포함)"),
    end: str = Query(..., description="종료일 (YYYY-MM-DD, 포함)"),
):
    try:
        s = svc.parse_date(start, label="시작")
        e = svc.parse_date(end, label="종료")
        svc.validate_range(s, e)
    except svc.InvalidRangeError as ex:
        raise HTTPException(status_code=400, detail=str(ex))

    try:
        return svc.fetch_history(s, e)
    except Exception as ex:
        log.exception("[llm_ui_history] 집계 실패: %s", ex)
        raise HTTPException(status_code=500, detail=f"집계 실패: {ex}")


@router.get("/today")
def today_snapshot():
    """통합 대시보드 'LLM 사용' 카드용: 오늘 하루치 사용자/총 사용 횟수.

    login_history 의 ``/login-history/today`` 와 응답 스키마가 **완전히 동일**
    하다 — 통합 대시보드의 ``LoginTodayCard`` JS 클래스를 그대로 재사용하기
    위함이다.

    응답 형태(간결화):
        {
          "date": "2026-05-15",
          "all": {
            "distinct": 12,        # 오늘 LLM UI 사용자 수 (고유)
            "total":    25,        # 오늘 총 사용 횟수
            "users":    [{"user_id": "alice", "count": 4}, ...],  # Top N
            "extra_users": 0
          },
          "customer": { ... 같은 형태 ... },
          "developer_count": 3,
          "tooltip_top_n": 10,
          "elapsed_ms": 42
        }

    fetch_history(today, today) 결과를 카드 표시용으로 압축한다.
    "오늘" 은 서버 로컬 기준 date.today() 이며, DB 의 timestamp 값을
    그대로 비교한다 (타임존 변환 없음 — login_history 와 동일 정책).
    """
    today = date.today()
    try:
        full = svc.fetch_history(today, today)
    except Exception as ex:
        log.exception("[llm_ui_history] today 집계 실패: %s", ex)
        raise HTTPException(status_code=500, detail=f"집계 실패: {ex}")

    # fetch_history 는 days 길이만큼 시리즈를 주는데, today=today 인 경우
    # 항상 길이 1 짜리 리스트가 된다. [0] 하나만 꺼내 단일 값으로 정리.
    def _pick(side: dict) -> dict:
        totals = side.get("total") or [0]
        distincts = side.get("distinct") or [0]
        tips = side.get("tooltip") or []
        first_tip = tips[0] if tips else {}
        return {
            "total": int(totals[0] if totals else 0),
            "distinct": int(distincts[0] if distincts else 0),
            "users": list(first_tip.get("users") or []),
            "extra_users": int(first_tip.get("extra_users") or 0),
        }

    return {
        "date": full.get("end") or today.isoformat(),
        "all": _pick(full.get("all") or {}),
        "customer": _pick(full.get("customer") or {}),
        "developer_count": len(full.get("developer_ids") or []),
        "tooltip_top_n": int(full.get("tooltip_top_n") or 10),
        "elapsed_ms": int(full.get("elapsed_ms") or 0),
    }

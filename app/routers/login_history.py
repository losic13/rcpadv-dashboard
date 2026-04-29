"""Client 접속 이력 페이지 / API.

라우트:
    GET /login-history          : 페이지 (입력 폼 + 막대 차트 2개)
    GET /login-history/run      : JSON API (start/end 받아 집계 결과 반환)
    GET /login-history/today    : 통합 대시보드 카드용 오늘 스냅샷

타임존 정책:
    DB 의 `date_time` 값을 *그대로* 사용한다. 서버/DB 가 어떤 타임존으로
    저장·동작하든 별도 변환 없이 화면에 표시한다 (사용자 요청).
    여기서의 "오늘" 도 단순히 서버 로컬 기준 date.today() 이며, 별도 KST
    변환을 하지 않는다.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import login_history_service as svc

router = APIRouter(prefix="/login-history")
log = get_logger("router.login_history")


@router.get("")
def page(request: Request):
    today = date.today()
    start, end = svc.default_range(today=today, days=14)
    return templates.TemplateResponse(
        request,
        "login_history.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "login_history",
            "page_title": "Client 접속 이력",
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
        log.exception("[login_history] 집계 실패: %s", ex)
        raise HTTPException(status_code=500, detail=f"집계 실패: {ex}")


@router.get("/today")
def today_snapshot():
    """통합 대시보드 카드용: 오늘 하루치 접속자/총 로그인 수.

    응답 형태(간결화):
        {
          "date": "2026-04-29",
          "all": {
            "distinct": 12,
            "total": 25,
            "users": [{"user_id": "alice", "count": 4}, ...],   # Top N (count 내림차순)
            "extra_users": 0                                     # Top N 을 초과한 추가 인원 수
          },
          "customer": { ... 같은 형태 ... },
          "developer_count": 3,
          "tooltip_top_n": 10,
          "elapsed_ms": 42
        }

    fetch_history(today, today) 결과를 카드 표시용으로 압축한다.
    "오늘" 은 서버 로컬 기준 date.today() 이며, DB 의 date_time 값을
    그대로 비교한다 (타임존 변환 없음).

    users / extra_users 는 카드 hover 툴팁에서 "오늘 접속자 ID Top N"
    리스트를 보여주기 위해 함께 내려준다.
    """
    today = date.today()
    try:
        full = svc.fetch_history(today, today)
    except Exception as ex:
        log.exception("[login_history] today 집계 실패: %s", ex)
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

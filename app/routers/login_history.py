"""사용자 접속 이력 페이지 / API.

라우트:
    GET /login-history          : 페이지 (입력 폼 + 막대 차트 2개)
    GET /login-history/run      : JSON API (start/end 받아 집계 결과 반환)
    GET /login-history/today    : 통합 대시보드 카드용 오늘 스냅샷
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import login_history_service as svc

router = APIRouter(prefix="/login-history")
log = get_logger("router.login_history")

# KST(Asia/Seoul) — 운영 데이터/사용자 화면 모두 KST 기준으로 동작한다.
# 컨테이너/서버가 UTC 로 떠 있으면 date.today() 가 UTC 일자를 돌려주는데,
# UTC 15:00 ~ 23:59 (= KST 다음날 00:00 ~ 08:59) 시간대에는 그게
# "어제 KST 일자" 가 되어 버려서 "오늘 카드는 0 인데 사용자 접속 이력
# 페이지에는 보임" 증상이 생겼다. → 항상 KST 기준 일자로 계산한다.
KST = timezone(timedelta(hours=9))


def _today_kst() -> date:
    """현재 시각을 KST 기준 date 로 반환."""
    return datetime.now(KST).date()


@router.get("")
def page(request: Request):
    today = _today_kst()
    start, end = svc.default_range(today=today, days=14)
    return templates.TemplateResponse(
        request,
        "login_history.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "login_history",
            "page_title": "사용자 접속 이력",
            "default_start": start.isoformat(),
            "default_end": end.isoformat(),
            "today": today.isoformat(),
        },
    )


@router.get("/run")
def run(
    start: str = Query(..., description="시작일 (YYYY-MM-DD, KST, 포함)"),
    end: str = Query(..., description="종료일 (YYYY-MM-DD, KST, 포함)"),
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
    """통합 대시보드 카드용: 오늘(KST) 하루치 접속자/총 로그인 수.

    응답 형태(간결화):
        {
          "date": "2026-04-29",
          "all":      {"distinct": 12, "total": 25},   # 개발자 포함
          "customer": {"distinct":  9, "total": 18},   # 개발자 제외
          "developer_count": 3,
          "elapsed_ms": 42
        }

    fetch_history(today, today) 결과를 카드 표시용으로 압축한다.

    *주의*: 여기서의 "오늘" 은 KST 기준이다. 서버 시간대(UTC) 의 date.today()
    를 그대로 쓰면 KST 0~9시 사이에 항상 "어제" 의 데이터가 나오는 버그가
    있었다. (사용자 접속 이력 페이지는 0이 아닌데 통합 대시보드 카드만
    0으로 떠 있는 증상의 근본 원인.)
    """
    today = _today_kst()
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
        return {
            "total": int(totals[0] if totals else 0),
            "distinct": int(distincts[0] if distincts else 0),
        }

    return {
        "date": full.get("end") or today.isoformat(),
        "all": _pick(full.get("all") or {}),
        "customer": _pick(full.get("customer") or {}),
        "developer_count": len(full.get("developer_ids") or []),
        "elapsed_ms": int(full.get("elapsed_ms") or 0),
    }

"""사용자 접속 이력 서비스.

DB 에서 (day, user_id, login_count) 행을 받아와 페이지가 사용하는
응답 형태로 가공한다. 응답 구조:

    {
        "start": "2026-04-15",     # KST, 포함
        "end":   "2026-04-29",     # KST, 포함 (페이지 입력 기준)
        "days":  ["2026-04-15", ..., "2026-04-29"],
        "all": {
            "total":     [3, 5, 4, ...],          # 날짜별 총 로그인 수
            "distinct":  [2, 4, 3, ...],          # 날짜별 고유 사용자 수
            "tooltip":   [
                {"total": 3, "distinct": 2,
                 "users": [{"user_id": "alice", "count": 2},
                            {"user_id": "bob",   "count": 1}],
                 "extra_users": 0},
                ...  # days 길이만큼
            ],
        },
        "customer": { ... 같은 형태 ... },           # 개발자 제외 버전
        "developer_ids": ["alice", ...],          # 현재 적용 중인 개발자 화이트리스트
        "elapsed_ms": 123,
    }

설계:
  - SQL 은 [start, end) 반-개방 구간으로 호출한다 (end 다음날 0시).
  - 입력 페이지에서 받는 start/end 는 둘 다 "포함" 이다 (사람 친화).
  - 0 로그인 일자도 차트가 비지 않도록 days 를 채운다.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.logger import get_logger
from app.queries import developer_ids
from app.queries.login_history_queries import (
    LOGIN_HISTORY_SOURCE,
    LOGIN_HISTORY_SQL,
)
from app.repositories import mariadb

log = get_logger("service.login_history")

# 툴팁에 보여줄 사용자 상위 N명
TOOLTIP_TOP_N = 10


# ============================================================
# 입력 검증
# ============================================================
class InvalidRangeError(ValueError):
    """start/end 파라미터가 유효하지 않을 때."""


def parse_date(s: str | None, *, label: str) -> date:
    if not s:
        raise InvalidRangeError(f"{label} 일자가 비어 있습니다.")
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise InvalidRangeError(
            f"{label} 일자 형식이 잘못되었습니다 (YYYY-MM-DD): {s!r}"
        )


def validate_range(start: date, end: date) -> None:
    if end < start:
        raise InvalidRangeError(
            f"종료일이 시작일보다 빠릅니다 (start={start}, end={end})."
        )


def default_range(*, today: date | None = None, days: int = 14) -> tuple[date, date]:
    """기본 기간: 오늘 포함 최근 `days` 일.

    days=14 면 [today - 13, today] 를 돌려준다 (양끝 포함).
    """
    if today is None:
        today = date.today()
    return today - timedelta(days=days - 1), today


# ============================================================
# 메인 로직
# ============================================================
def fetch_history(start: date, end: date) -> dict[str, Any]:
    """start, end (둘 다 포함, KST) 범위로 로그인 이력을 집계한다."""
    validate_range(start, end)
    started = time.perf_counter()

    # SQL 은 [start_dt, end_dt) 반-개방 구간. end 다음날 0시까지.
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)

    log.info(
        "[login_history] 조회 시작 start=%s end=%s (SQL: [%s, %s))",
        start, end, start_dt, end_dt,
    )

    columns, rows = mariadb.execute(
        LOGIN_HISTORY_SOURCE,
        LOGIN_HISTORY_SQL,
        {"start": start_dt, "end": end_dt},
    )
    log.info(
        "[login_history] 원본 행 수: %d (columns=%s)", len(rows), columns,
    )

    # day 키는 'YYYY-MM-DD' 문자열로 정규화. DB 가 date 객체로 줄 수도, 문자열로 줄 수도 있다.
    def _norm_day(v: Any) -> str:
        if isinstance(v, datetime):
            return v.date().isoformat()
        if isinstance(v, date):
            return v.isoformat()
        return str(v)[:10]

    # (day → user_id → count) 누적 — 같은 (day, user_id) 가 여러 행으로 올 일은
    # 사실상 없지만, 안전하게 sum 한다.
    by_day_user: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        day = _norm_day(r.get("day"))
        uid = r.get("user_id")
        if uid is None:
            uid = ""
        cnt = int(r.get("login_count") or 0)
        if cnt <= 0:
            continue
        by_day_user[day][str(uid)] += cnt

    # 차트 X축: 0 로그인 일자도 빈 막대로 표시
    days = _date_range(start, end)

    # 두 가지 시리즈를 만든다: 전체 / 고객(개발자 제외)
    dev_set = developer_ids.get_developer_id_set()

    def _build(filter_dev: bool) -> dict[str, Any]:
        totals: list[int] = []
        distincts: list[int] = []
        tooltips: list[dict[str, Any]] = []
        for d in days:
            user_map = by_day_user.get(d, {})
            if filter_dev and dev_set:
                user_map = {
                    uid: cnt
                    for uid, cnt in user_map.items()
                    if uid.strip().lower() not in dev_set
                }
            total = sum(user_map.values())
            distinct = len(user_map)
            # 툴팁용 상위 N명
            top = sorted(user_map.items(), key=lambda x: (-x[1], x[0]))
            top_users = [{"user_id": u, "count": c} for u, c in top[:TOOLTIP_TOP_N]]
            extra = max(0, len(top) - TOOLTIP_TOP_N)
            totals.append(total)
            distincts.append(distinct)
            tooltips.append({
                "total": total,
                "distinct": distinct,
                "users": top_users,
                "extra_users": extra,
            })
        return {
            "total": totals,
            "distinct": distincts,
            "tooltip": tooltips,
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    result = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "all": _build(filter_dev=False),
        "customer": _build(filter_dev=True),
        "developer_ids": sorted(dev_set),
        "tooltip_top_n": TOOLTIP_TOP_N,
        "elapsed_ms": elapsed_ms,
    }
    log.info(
        "[login_history] 완료 days=%d, all.total=%d, customer.total=%d, %dms",
        len(days),
        sum(result["all"]["total"]),
        sum(result["customer"]["total"]),
        elapsed_ms,
    )
    return result


def _date_range(start: date, end: date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur = cur + timedelta(days=1)
    return out

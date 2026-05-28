"""LLM UI 사용 이력(/llm-ui-conversations) 서비스 레이어.

PostgreSQL 에서 대화 메시지 원본 행을 받아 두 가지 뷰로 가공한다:

    1) timeline : created_at 시간순으로 정렬된 단일 리스트
    2) by_user  : user_id → conversations[] → messages[] 계층

응답 구조 (페이지가 그대로 받아 렌더):
    {
        "start":      "2026-05-19",
        "end":        "2026-05-26",
        "row_count":  1234,            # 원본 행 수
        "timeline":   [ message, ... ],   # created_at ASC
        "by_user":    [
            {
                "user_id":      "alice",
                "msg_count":    42,
                "conv_count":   3,
                "conversations": [
                    {
                        "conversation_id": "conv-abc",
                        "msg_count":  12,
                        "started_at": "2026-05-20 10:11:22",
                        "ended_at":   "2026-05-20 10:45:33",
                        "messages":   [ message, ... ],  # seq ASC
                    },
                    ...
                ],
            },
            ...
        ],
        "elapsed_ms": 87,
    }

message 의 구조 (timeline / messages 둘 다 동일):
    {
        "conversation_id": str,
        "id":              str,
        "seq":             int|None,
        "role":            str,        # 'user' / 'assistant'
        "content":         str,
        "trace":           str|None,   # raw (모달에서 JSON pretty-print)
        "created_at":      str,        # 'YYYY-MM-DD HH:MM:SS' 등
        "parent_id":       str|None,
        "user_id":         str,
    }

타임존 정책:
    DB 의 timestamp 값을 *그대로* 사용한다 (llm_ui_history 와 동일).
    별도 변환을 하지 않으며, "시간순" 도 DB 값의 lexicographic / 자연 정렬.

제한:
    사용자 결정(Q3=C) — 행 수 제한 없음. SQL 에 LIMIT 미포함.
"""
from __future__ import annotations

import ast
import json
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.logger import get_logger
from app.queries.llm_ui_conv_queries import (
    LLM_UI_CONV_SOURCE,
    LLM_UI_CONV_SQL,
)
from app.repositories import postgres

log = get_logger("service.llm_ui_conv")


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


def default_range(*, today: date | None = None, days: int = 7) -> tuple[date, date]:
    """기본 기간: 오늘 포함 최근 ``days`` 일 (사용자 결정 Q2=7)."""
    if today is None:
        today = date.today()
    return today - timedelta(days=days - 1), today


# ============================================================
# 메인 로직
# ============================================================
def fetch_conversations(start: date, end: date) -> dict[str, Any]:
    """start, end (둘 다 포함) 범위 안의 대화 메시지를 두 뷰로 가공.

    DB 의 timestamp 값을 타임존 변환 없이 그대로 비교한다.
    """
    validate_range(start, end)
    started = time.perf_counter()

    # SQL 은 [start_dt, end_dt) 반-개방 구간. end 다음날 0시까지.
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)

    log.info(
        "[llm_ui_conv] 조회 시작 start=%s end=%s (SQL: [%s, %s))",
        start, end, start_dt, end_dt,
    )

    columns, rows = postgres.execute(
        LLM_UI_CONV_SOURCE,
        LLM_UI_CONV_SQL,
        {"start": start_dt, "end": end_dt},
    )
    log.info(
        "[llm_ui_conv] 원본 행 수: %d (columns=%s)",
        len(rows), columns,
    )

    # ─────────────────────────────────────────────────────
    # 행 정규화: dict[str, ...] 로 통일
    # ─────────────────────────────────────────────────────
    messages: list[dict[str, Any]] = [_normalize_row(r) for r in rows]

    # ─────────────────────────────────────────────────────
    # 뷰 1) timeline : created_at ASC
    # ─────────────────────────────────────────────────────
    timeline = sorted(
        messages,
        key=lambda m: (m.get("created_at") or "", m.get("conversation_id") or "", m.get("seq") or 0),
    )

    # ─────────────────────────────────────────────────────
    # 뷰 2) by_user : user_id → conversation_id → messages (seq ASC)
    # ─────────────────────────────────────────────────────
    # (user_id, conversation_id) → [messages]
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for m in messages:
        uid = m.get("user_id") or ""
        cid = m.get("conversation_id") or ""
        grouped[uid][cid].append(m)

    by_user: list[dict[str, Any]] = []
    for uid in sorted(grouped.keys()):
        conv_map = grouped[uid]
        conversations: list[dict[str, Any]] = []
        for cid in conv_map.keys():
            msgs = conv_map[cid]
            msgs_sorted = sorted(
                msgs,
                key=lambda m: (
                    (m.get("seq") if m.get("seq") is not None else 1 << 30),
                    m.get("created_at") or "",
                ),
            )
            started_at = min(
                (m.get("created_at") or "" for m in msgs_sorted),
                default="",
            )
            ended_at = max(
                (m.get("created_at") or "" for m in msgs_sorted),
                default="",
            )
            conversations.append({
                "conversation_id": cid,
                "msg_count": len(msgs_sorted),
                "started_at": started_at,
                "ended_at": ended_at,
                "messages": msgs_sorted,
            })
        # 사용자 내 대화 정렬: started_at 시간 순 (오래된 것 → 최신)
        conversations.sort(key=lambda c: (c.get("started_at") or "", c.get("conversation_id") or ""))
        msg_total = sum(c["msg_count"] for c in conversations)
        by_user.append({
            "user_id": uid,
            "msg_count": msg_total,
            "conv_count": len(conversations),
            "conversations": conversations,
        })

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    result = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "row_count": len(messages),
        "timeline": timeline,
        "by_user": by_user,
        "elapsed_ms": elapsed_ms,
    }
    log.info(
        "[llm_ui_conv] 완료 rows=%d users=%d, %dms",
        len(messages), len(by_user), elapsed_ms,
    )
    return result


# ============================================================
# 헬퍼
# ============================================================
def _normalize_trace(raw: str | None) -> str | None:
    """trace 원본 문자열을 프런트가 ``JSON.parse`` 할 수 있는 형태로 정규화.

    DB 에 저장된 trace 는 두 가지 형태로 들어올 수 있다:

      1) **표준 JSON 문자열**    — ``{"k": "v", ...}`` (큰따옴표). 이미 정상.
      2) **Python ``repr()`` 형식의 dict 문자열**
         — ``{'k': 'v', None, True, False, ...}`` (작은따옴표 + Python 리터럴).
         이 경우 그대로 ``JSON.parse`` 하면 실패해서 프런트에서 raw 모드로
         떨어지고, ``\\n`` 같은 escape sequence 도 풀리지 않은 채 노출된다.

    이 함수는 다음 우선순위로 시도해 **표준 JSON 문자열 (큰따옴표, ASCII-safe
    하지 않음)** 로 정규화한다. 어느 단계에서든 결과는 프런트의
    ``JSON.parse`` 가 받아들일 수 있는 형태여야 한다.

      Step 1) ``json.loads(raw)``        → 이미 표준 JSON. ``json.dumps`` 로
                                            ``ensure_ascii=False`` 재직렬화만.
      Step 2) ``ast.literal_eval(raw)``  → Python 리터럴 (dict/list/tuple/
                                            str/int/float/bool/None) 로 평가.
                                            성공 시 tuple → list 로 치환 후
                                            ``json.dumps`` 로 직렬화.
      Step 3) 둘 다 실패하면 **원본 그대로 반환** (프런트가 raw <pre> 로 표시).

    ``ast.literal_eval`` 은 임의 코드 실행이 아닌 리터럴 평가만 수행하므로
    안전하다 (Python 공식 문서). 즉, 함수 호출이나 이름 조회는 거부된다.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        # 혹시 dict/list 등이 그대로 넘어오면 직렬화만 해서 반환.
        try:
            return json.dumps(raw, ensure_ascii=False, default=str)
        except Exception:
            return None
    s = raw.strip()
    if not s:
        return raw  # 빈 문자열은 그대로

    # Step 1: 이미 표준 JSON 인지.
    try:
        obj = json.loads(s)
        # 재직렬화로 통일된 표기 보장 (ensure_ascii=False → 한글 그대로).
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        pass

    # Step 2: Python repr() 형태의 dict/list 인지.
    try:
        obj = ast.literal_eval(s)
    except Exception:
        return raw  # 평가 실패 → 원본 그대로 (프런트 raw fallback).

    # tuple → list, set → list 로 강제 (JSON 비호환 자료형 정리).
    def _jsonable(v: Any) -> Any:
        if isinstance(v, dict):
            return {str(k): _jsonable(val) for k, val in v.items()}
        if isinstance(v, (list, tuple, set, frozenset)):
            return [_jsonable(x) for x in v]
        # bytes 는 utf-8 decode 시도, 실패하면 repr.
        if isinstance(v, (bytes, bytearray)):
            try:
                return v.decode("utf-8")
            except Exception:
                return repr(v)
        return v  # str / int / float / bool / None → 그대로

    try:
        return json.dumps(_jsonable(obj), ensure_ascii=False, default=str)
    except Exception:
        return raw  # 직렬화 실패 → 원본 그대로.


def _normalize_row(r: dict[str, Any]) -> dict[str, Any]:
    """DB row 를 페이지가 기대하는 키/타입으로 정규화.

    - 모든 None 은 그대로 None 유지 (프런트에서 처리).
    - seq 만 int 강제, 나머지는 문자열/None.
    - created_at 는 repositories.postgres 에서 이미 str 화 되어 있을 가능성이 큼.
    """
    def _s(v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        try:
            return str(v)
        except Exception:
            return None

    seq_v = r.get("seq")
    seq_int: int | None
    if seq_v is None:
        seq_int = None
    else:
        try:
            seq_int = int(seq_v)
        except (TypeError, ValueError):
            seq_int = None

    return {
        "conversation_id": _s(r.get("conversation_id")) or "",
        "id":              _s(r.get("id")) or "",
        "seq":             seq_int,
        "role":            _s(r.get("role")) or "",
        "content":         _s(r.get("content")) or "",
        "trace":           _normalize_trace(_s(r.get("trace"))),
        "created_at":      _s(r.get("created_at")) or "",
        "parent_id":       _s(r.get("parent_id")),
        "user_id":         _s(r.get("user_id")) or "",
    }

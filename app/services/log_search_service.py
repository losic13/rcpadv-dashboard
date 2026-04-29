"""Log Search 서비스.

화이트리스트(LOG_SEARCH_QUERIES)에 정의된 모든 쿼리를 단일 검색 파라미터
(`param`) 로 동시 실행한 뒤, 결과를 통합 테이블 형식의 단일 응답으로 합쳐
반환한다.

응답 형태(라우터 → JS):
    {
        "param": "...",
        "columns": ["source", "table", "root_lot_wf_id", ...extras..., "path"],
        "rows": [
            {"source": "vnand", "table": "vnand.parsing_results",
             "root_lot_wf_id": "...", "product": "...", "tkin_time": "...",
             "path": "/abs/path/to/file"},
            ...
        ],
        "row_count": int,
        "elapsed_ms": int,
        "tables": [
            {"label": "vnand.parsing_results", "source": "vnand",
             "row_count": 12, "elapsed_ms": 35, "ok": true},
            {"label": "dram.parsing_results", "source": "dram",
             "row_count": 0,  "elapsed_ms": 12, "ok": true,
             "error": null},
            ...
        ],
    }

설계 메모:
  - 각 화이트리스트 쿼리를 to_thread 로 병렬 실행한다(asyncio.gather).
  - 한 테이블이 실패해도 다른 테이블 결과는 그대로 반환한다(부분 실패 허용).
  - 결과 컬럼은 `source`, `table`, SEARCH_COLUMN, *(extras 합집합)*, `path`
    순으로 정렬되어 합쳐진다(없는 컬럼은 None).
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.config import settings
from app.logger import get_logger
from app.queries.log_search_queries import (
    LOG_SEARCH_QUERIES,
    SEARCH_COLUMN,
    LogSearchQueryDef,
)
from app.repositories import mariadb

log = get_logger("service.log_search")


# ============================================================
# 입력 검증
# ============================================================
# 사용자 요구사항:
#   - 1~19 글자
#   - 허용: 영문 대소문자, 숫자, '-', '_', '@', '.'
# 길이는 한 곳(MAX_PARAM_LEN)에서 관리. 정규식과 별개로 길이 체크.
MIN_PARAM_LEN = 1
MAX_PARAM_LEN = 19
_PARAM_PATTERN = re.compile(r"^[A-Za-z0-9._@\-]+$")


class InvalidParamError(ValueError):
    """검색 파라미터가 유효하지 않을 때."""


def validate_param(raw: str | None) -> str:
    """입력 파라미터 정규화 + 검증.

    - 양쪽 공백 제거
    - 길이/문자셋 검증
    - 통과하면 정규화된 문자열 반환, 아니면 InvalidParamError
    """
    if raw is None:
        raise InvalidParamError("검색어가 비어 있습니다.")
    s = raw.strip()
    if len(s) < MIN_PARAM_LEN:
        raise InvalidParamError("검색어가 비어 있습니다.")
    if len(s) > MAX_PARAM_LEN:
        raise InvalidParamError(
            f"검색어가 너무 깁니다 (최대 {MAX_PARAM_LEN}자, 입력 {len(s)}자)."
        )
    if not _PARAM_PATTERN.match(s):
        raise InvalidParamError(
            "허용 문자만 입력 가능: 영문/숫자/하이픈(-)/언더바(_)/골뱅이(@)/마침표(.)"
        )
    return s


# ============================================================
# 단일 화이트리스트 쿼리 실행
# ============================================================
def _run_single(qdef: LogSearchQueryDef, param: str) -> dict[str, Any]:
    """한 항목 실행. 실패해도 예외 던지지 않고 result dict 안에 ok=False 로 표기."""
    started = time.perf_counter()
    try:
        columns, rows = mariadb.execute(
            qdef.source, qdef.sql, {"param": param}
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.warning(
            "[log_search] %s 실패 (%dms): %s", qdef.table_label, elapsed_ms, e
        )
        return {
            "qdef": qdef,
            "ok": False,
            "error": str(e),
            "columns": [],
            "rows": [],
            "elapsed_ms": elapsed_ms,
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # path_column → path 정규화. 원본 컬럼은 살려두지 않고 path 로만 노출
    # (UI 가 항상 row.path 를 다운로드 링크로 사용하기 위함).
    if qdef.path_column not in columns:
        log.error(
            "[log_search] %s: path_column '%s' 가 SELECT 결과에 없음",
            qdef.table_label, qdef.path_column,
        )
        return {
            "qdef": qdef,
            "ok": False,
            "error": (
                f"쿼리 정의 오류: path_column '{qdef.path_column}' 이 "
                f"SELECT 결과에 포함되지 않았습니다."
            ),
            "columns": [],
            "rows": [],
            "elapsed_ms": elapsed_ms,
        }

    log.info(
        "[log_search] %s 완료: %d행, %dms",
        qdef.table_label, len(rows), elapsed_ms,
    )
    return {
        "qdef": qdef,
        "ok": True,
        "error": None,
        "columns": columns,
        "rows": rows,
        "elapsed_ms": elapsed_ms,
    }


# ============================================================
# 통합 실행 (페이지에서 호출)
# ============================================================
async def search_all(param: str) -> dict[str, Any]:
    """전체 화이트리스트를 병렬 실행하고 통합 결과 반환.

    - 입력은 이미 validate_param 을 통과했다고 가정.
    - 화이트리스트가 비어 있으면 빈 결과를 그대로 돌려준다.
    """
    if not LOG_SEARCH_QUERIES:
        return {
            "param": param,
            "columns": ["source", "table", SEARCH_COLUMN, "path"],
            "rows": [],
            "row_count": 0,
            "elapsed_ms": 0,
            "tables": [],
        }

    overall_started = time.perf_counter()

    # 각 쿼리는 to_thread 로 풀에 던지고 wait_for 로 타임아웃.
    async def _run_with_timeout(qdef: LogSearchQueryDef) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_run_single, qdef, param),
                timeout=settings.QUERY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.error("[log_search] %s 타임아웃 (>%ds)",
                      qdef.table_label, settings.QUERY_TIMEOUT_SECONDS)
            return {
                "qdef": qdef,
                "ok": False,
                "error": f"타임아웃 (>{settings.QUERY_TIMEOUT_SECONDS}초)",
                "columns": [],
                "rows": [],
                "elapsed_ms": settings.QUERY_TIMEOUT_SECONDS * 1000,
            }

    results = await asyncio.gather(
        *[_run_with_timeout(q) for q in LOG_SEARCH_QUERIES]
    )

    # ---- 컬럼 결합 정책 ----
    # 표시 순서:
    #   source, table, SEARCH_COLUMN, *(extra_columns 합집합), path
    extras_seen: list[str] = []
    extras_set: set[str] = set()
    for q in LOG_SEARCH_QUERIES:
        for c in q.extra_columns:
            if c == SEARCH_COLUMN or c == q.path_column:
                continue  # 별도 슬롯에 들어가므로 중복 표시 X
            if c not in extras_set:
                extras_set.add(c)
                extras_seen.append(c)

    out_columns = ["source", "table", SEARCH_COLUMN, *extras_seen, "path"]

    # ---- 행 통합 ----
    out_rows: list[dict[str, Any]] = []
    tables_meta: list[dict[str, Any]] = []
    for r in results:
        qdef: LogSearchQueryDef = r["qdef"]
        tables_meta.append({
            "label": qdef.table_label,
            "source": qdef.source,
            "row_count": len(r["rows"]),
            "elapsed_ms": r["elapsed_ms"],
            "ok": r["ok"],
            "error": r["error"],
        })
        if not r["ok"]:
            continue

        for row in r["rows"]:
            unified = {
                "source": qdef.source,
                "table": qdef.table_label,
                SEARCH_COLUMN: row.get(SEARCH_COLUMN),
                "path": row.get(qdef.path_column),
            }
            for c in extras_seen:
                unified[c] = row.get(c)
            out_rows.append(unified)

    elapsed_ms = int((time.perf_counter() - overall_started) * 1000)
    log.info(
        "[log_search] 통합 완료: param=%r, %d테이블 → %d행, %dms",
        param, len(tables_meta), len(out_rows), elapsed_ms,
    )

    return {
        "param": param,
        "columns": out_columns,
        "rows": out_rows,
        "row_count": len(out_rows),
        "elapsed_ms": elapsed_ms,
        "tables": tables_meta,
    }

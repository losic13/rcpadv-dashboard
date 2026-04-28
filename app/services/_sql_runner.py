"""VNAND/DRAM 공통 SQL 실행 헬퍼.

서비스별 차이가 거의 없으므로 공통 로직을 모아둠 (소스 식별자만 다름).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from app.config import settings
from app.logger import get_logger
from app.queries._base import SqlQueryDef
from app.repositories import mariadb

log = get_logger("service.sql")


def list_queries(queries: dict[str, SqlQueryDef]) -> list[dict[str, Any]]:
    """UI 셀렉터용 쿼리 메타 목록."""
    return [
        {
            "id": q.id,
            "title": q.title,
            "description": q.description,
            "params": [p.__dict__ for p in q.params],
        }
        for q in queries.values()
    ]


def list_dashboard_queries(queries: dict[str, SqlQueryDef]) -> list[SqlQueryDef]:
    return [q for q in queries.values() if q.show_in_dashboard]


def _filter_params(query: SqlQueryDef, params: dict[str, Any] | None) -> dict[str, Any]:
    """쿼리에 정의된 파라미터 중, 입력으로 들어온 것만 바인딩.

    SQL 쪽은 COALESCE 등으로 None 을 처리하도록 작성되어 있는 것을 권장.
    """
    bound: dict[str, Any] = {}
    for p in query.params:
        if params and p.name in params and params[p.name] not in (None, ""):
            bound[p.name] = params[p.name]
        else:
            bound[p.name] = None
    return bound


async def run_query(
    source: str,
    queries: dict[str, SqlQueryDef],
    query_id: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """쿼리 실행 후 표준 응답 dict 반환.

    응답:
      {
        "query_id": str,
        "title": str,
        "columns": [..],
        "rows": [{...}, ...],
        "row_count": int,
        "elapsed_ms": int,
      }
    """
    if query_id not in queries:
        raise KeyError(f"Unknown {source} query: {query_id}")

    qdef = queries[query_id]
    bound = _filter_params(qdef, params)

    log.info("[%s] 쿼리 실행 시작: %s", source, query_id)
    start = time.perf_counter()
    try:
        columns, rows = await asyncio.wait_for(
            asyncio.to_thread(mariadb.execute, source, qdef.sql, bound),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[%s] 쿼리 타임아웃: %s (>%ds)", source, query_id, settings.QUERY_TIMEOUT_SECONDS)
        raise
    except Exception as e:
        log.error("[%s] 쿼리 실패: %s — %s", source, query_id, e)
        raise

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    log.info("[%s] 쿼리 완료: %s (%d행, %dms)", source, query_id, len(rows), elapsed_ms)

    return {
        "query_id": query_id,
        "title": qdef.title,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "elapsed_ms": elapsed_ms,
    }

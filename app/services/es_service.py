"""Elasticsearch 서비스.

DSL 응답을 (columns, rows) 형태로 정규화하여 클라이언트에서 DataTables 가
공통 포맷으로 처리할 수 있게 한다.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from app.config import settings
from app.logger import get_logger
from app.queries import es_queries
from app.queries._base import EsQueryDef
from app.repositories import es_client

log = get_logger("service.es")

SOURCE = "es"
SOURCE_LABEL = "Elasticsearch"


def list_queries() -> list[dict[str, Any]]:
    return [
        {"id": q.id, "title": q.title, "description": q.description, "params": []}
        for q in es_queries.QUERIES.values()
    ]


def list_dashboard_queries() -> list[EsQueryDef]:
    return [q for q in es_queries.QUERIES.values() if q.show_in_dashboard]


async def run(query_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if query_id not in es_queries.QUERIES:
        raise KeyError(f"Unknown ES query: {query_id}")
    qdef = es_queries.QUERIES[query_id]

    log.info("[es] 쿼리 실행 시작: %s (index=%s)", query_id, qdef.index)
    start = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(es_client.search, qdef.index, qdef.body),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es] 쿼리 타임아웃: %s (>%ds)", query_id, settings.QUERY_TIMEOUT_SECONDS)
        raise
    except Exception as e:
        log.error("[es] 쿼리 실패: %s — %s", query_id, e)
        raise

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    columns, rows = _normalize(resp)
    log.info("[es] 쿼리 완료: %s (%d행, %dms)", query_id, len(rows), elapsed_ms)

    return {
        "query_id": query_id,
        "title": qdef.title,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "elapsed_ms": elapsed_ms,
    }


def _normalize(resp: dict[str, Any]) -> tuple[list[str], list[dict]]:
    """ES 응답을 테이블 포맷으로 변환.

    1) hits 가 있으면 _source 의 키들을 컬럼으로
    2) hits 가 비어 있고 aggregations 가 있으면 첫 번째 terms agg 의 buckets 를 표로
    """
    hits = resp.get("hits", {}).get("hits", [])
    if hits:
        rows = []
        all_keys: list[str] = []
        seen = set()
        for h in hits:
            src = h.get("_source") or {}
            row = {"_id": h.get("_id")}
            for k, v in src.items():
                row[k] = _stringify(v)
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)
            rows.append(row)
        columns = ["_id"] + all_keys
        # 누락된 키 보정
        for r in rows:
            for c in columns:
                r.setdefault(c, None)
        return columns, rows

    aggs = resp.get("aggregations") or {}
    if aggs:
        # 첫 번째 agg 만 표로 변환 (키, doc_count)
        first_name = next(iter(aggs.keys()))
        agg = aggs[first_name]
        buckets = agg.get("buckets")
        if isinstance(buckets, list):
            rows = [{"key": b.get("key"), "doc_count": b.get("doc_count")} for b in buckets]
            return ["key", "doc_count"], rows

    return [], []


def _stringify(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, dict)):
        # 복합 타입은 그대로 (DataTables 에서 stringify 해서 표시)
        return v
    try:
        return str(v)
    except Exception:
        return None

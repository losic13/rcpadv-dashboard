"""VNAND 서비스. 쿼리 메타/실행 인터페이스 제공."""
from __future__ import annotations

from typing import Any

from app.queries import vnand_queries
from app.services import _sql_runner

SOURCE = "vnand"
SOURCE_LABEL = "VNAND DB"


def list_queries() -> list[dict[str, Any]]:
    return _sql_runner.list_queries(vnand_queries.QUERIES)


def list_dashboard_queries():
    return _sql_runner.list_dashboard_queries(vnand_queries.QUERIES)


async def run(query_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _sql_runner.run_query(SOURCE, vnand_queries.QUERIES, query_id, params)

"""AMAT 설비관리 서비스. 쿼리 메타/실행 인터페이스 제공.

AMAT 테이블들은 DRAM DB 안에 존재하므로 실제 엔진은 source="dram" 으로 호출한다.
다만 UI/라우팅 상으로는 AMAT 페이지가 별도 페이지(/amat) 이고, 페이지 내부에서
일반 SELECT 외에도 DML 작업이 들어가기 때문에 dram_service 와 별도로 분리한다.
"""
from __future__ import annotations

from typing import Any

from app.queries import amat_queries
from app.services import _sql_runner

# 실제 DB 엔진 식별자 — AMAT 테이블은 DRAM DB 안에 있으므로 "dram" 그대로 사용.
DB_SOURCE = "dram"

# UI 노출용 라벨/식별자 (사이드바, 페이지 헤더 등)
SOURCE = "amat"
SOURCE_LABEL = "AMAT 설비관리"


def list_queries() -> list[dict[str, Any]]:
    return _sql_runner.list_queries(amat_queries.QUERIES)


def list_dashboard_queries():
    return _sql_runner.list_dashboard_queries(amat_queries.QUERIES)


async def run(query_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    # 엔진은 DRAM, 쿼리 정의는 amat_queries 에서 가져온다.
    return await _sql_runner.run_query(DB_SOURCE, amat_queries.QUERIES, query_id, params)

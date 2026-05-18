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

# Abnormal Step 결과에 ES current_state 표시용 컬럼을 끼워넣을 대상 query_id.
# 두 탭(no_treat / all)은 같은 amat_abnormal_step 테이블을 보며 es_id 컬럼이 있으므로
# 둘 다 대상이다. ES 일괄 조회는 클라이언트에서 별도 fetch 로 채우고, 백엔드는
# 컬럼 자리(es_state)만 미리 비워둔다 — 정렬/검색이 동작하는 정식 컬럼이 되도록.
_ABNORMAL_STEP_QUERY_IDS: frozenset[str] = frozenset({
    "amat_abnormal_steps_no_treat",
    "amat_abnormal_steps_all",
})

# 새 컬럼 이름 — 클라이언트의 columnRenderOverrides 키와 정확히 일치해야 함.
ES_STATE_COLUMN = "es_state"


def list_queries() -> list[dict[str, Any]]:
    return _sql_runner.list_queries(amat_queries.QUERIES)


def list_dashboard_queries():
    return _sql_runner.list_dashboard_queries(amat_queries.QUERIES)


async def run(query_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    # 엔진은 DRAM, 쿼리 정의는 amat_queries 에서 가져온다.
    result = await _sql_runner.run_query(
        DB_SOURCE, amat_queries.QUERIES, query_id, params,
    )

    # ── Abnormal Step 결과에 ES-STATE 자리(빈 컬럼) 끼워넣기 ─────────────
    #   클라이언트가 페이지 로드 시 /es/bulk-current-state 로 일괄 조회해서
    #   채워 넣는다. 백엔드는 컬럼 헤더를 명시적으로 만들어 두기만 한다.
    #
    #   왜 백엔드에서 미리 자리를 만드는가:
    #     - DataTables 가 thead 를 columns 배열 그대로 그려서 동적 추가가 어려움
    #     - 정렬/검색 등 DataTables 기능이 정식 컬럼에서만 동작
    #     - 클라이언트는 row[ES_STATE_COLUMN] 만 채우면 되므로 변경 폭이 최소
    if query_id in _ABNORMAL_STEP_QUERY_IDS:
        cols = result.get("columns") or []
        rows = result.get("rows") or []
        if ES_STATE_COLUMN not in cols:
            # 위치: STATUS 컬럼 바로 우측 (사용자 요청). STATUS 가 없으면 맨 뒤.
            try:
                # 대소문자 무관 매칭 — driver 에 따라 'status' / 'STATUS' 어느 쪽도 가능.
                lower = [str(c).lower() for c in cols]
                pos = lower.index("status") + 1
            except ValueError:
                pos = len(cols)
            cols.insert(pos, ES_STATE_COLUMN)
            for r in rows:
                # None 으로 초기화 — UI 는 "…" placeholder 로 표시하다가
                # bulk fetch 결과가 도착하면 redraw 하면서 실제 값으로 채운다.
                r[ES_STATE_COLUMN] = None
            result["columns"] = cols
            result["rows"] = rows

    return result

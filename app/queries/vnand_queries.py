"""VNAND DB 쿼리 모음.

새 쿼리를 추가할 때:
  1) QUERIES 딕셔너리에 SqlQueryDef 추가
  2) 끝. (라우터/템플릿 수정 불필요 — 사이드바 메뉴/쿼리 셀렉터에 자동 노출)
"""
from app.queries._base import ParamDef, SqlQueryDef

QUERIES: dict[str, SqlQueryDef] = {
    "recent_errors": SqlQueryDef(
        id="recent_errors",
        title="최근 에러 로그 (24h)",
        description="최근 24시간 동안 발생한 에러 목록.",
        sql="""
            SELECT
                id,
                occurred_at,
                error_code,
                message
            FROM error_log
            WHERE occurred_at >= NOW() - INTERVAL 1 DAY
            ORDER BY occurred_at DESC
            LIMIT 1000
        """,
        show_in_dashboard=True,
    ),
    "wafer_yield": SqlQueryDef(
        id="wafer_yield",
        title="웨이퍼 수율 조회",
        description="기간을 입력하지 않으면 최근 7일 자동 적용.",
        sql="""
            SELECT
                lot_id,
                wafer_id,
                yield_pct,
                measured_at
            FROM wafer_yield
            WHERE measured_at BETWEEN
                COALESCE(:start_date, NOW() - INTERVAL 7 DAY)
                AND COALESCE(:end_date, NOW())
            ORDER BY measured_at DESC
            LIMIT 1000
        """,
        params=[
            ParamDef(name="start_date", label="시작일시", type="datetime"),
            ParamDef(name="end_date", label="종료일시", type="datetime"),
        ],
    ),
}

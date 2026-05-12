"""DRAM DB 쿼리 모음."""
from app.queries._base import ParamDef, SqlQueryDef

# ── 키워드 관리 전용 쿼리 (source_page 탭 외부에서 직접 사용) ──────────────
KEYWORD_LIST_SQL = """
    SELECT id, name FROM amat_keyword ORDER BY id
"""

QUERIES: dict[str, SqlQueryDef] = {
    "amat_abnormal_step_new": SqlQueryDef(
        id="amat_abnormal_step_new",
        title="AMAT 설비 Abnormal Step List (New)",
        description="AMAT 설비 Abnormal Step 신규 목록. FILE_PATH 컬럼 옆 [확인]/[⬇] 버튼으로 파일 다운로드 가능.",
        sql="""
            SELECT
                idx,
                es_id,
                file_path,
                reason,
                insert_datetime,
                status
            FROM amat_abnormal_step
            ORDER BY insert_datetime DESC
            LIMIT 1000
        """,
    ),
    "recent_test_results": SqlQueryDef(
        id="recent_test_results",
        title="최근 테스트 결과 (24h)",
        description="최근 24시간 DRAM 테스트 결과.",
        sql="""
            SELECT
                test_id,
                module_id,
                test_type,
                result,
                tested_at
            FROM test_result
            WHERE tested_at >= NOW() - INTERVAL 1 DAY
            ORDER BY tested_at DESC
            LIMIT 1000
        """,
        show_in_dashboard=True,
    ),
    "fail_summary": SqlQueryDef(
        id="fail_summary",
        title="불량 요약 (모듈별)",
        description="모듈별 최근 30일 불량 건수.",
        sql="""
            SELECT
                module_id,
                COUNT(*) AS fail_count
            FROM test_result
            WHERE result = 'FAIL'
              AND tested_at >= NOW() - INTERVAL 30 DAY
            GROUP BY module_id
            ORDER BY fail_count DESC
            LIMIT 1000
        """,
    ),
}

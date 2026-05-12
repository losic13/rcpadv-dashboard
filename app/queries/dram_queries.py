"""DRAM DB 쿼리 모음."""
from app.queries._base import ParamDef, SqlDmlDef, SqlQueryDef

# ── SELECT 쿼리 ──────────────────────────────────────────────────────────────
QUERIES: dict[str, SqlQueryDef] = {
    "amat_keyword_list": SqlQueryDef(
        id="amat_keyword_list",
        title="AMAT Abnormal Keyword",
        description="amat_keyword 테이블 전체 조회.",
        sql="""
            SELECT id, name FROM amat_keyword ORDER BY id
        """,
        hidden=True,  # source_page 일반 탭에서 제외 — special_tab(panel-amat-keyword)으로 표시
    ),
    "amat_abnormal_step_new": SqlQueryDef(
        id="amat_abnormal_step_new",
        title="AMAT 설비 Abnormal Step List (New)",
        description="AMAT 설비 Abnormal Step 신규 목록. FILE_PATH 컬럼 옆 [확인]/[⬇] 버튼으로 파일 다운로드 가능. STATUS 셀에서 직접 변경 후 SAVE.",
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
    "amat_abnormal_step_all": SqlQueryDef(
        id="amat_abnormal_step_all",
        title="AMAT 설비 Abnormal Step List (All)",
        description="AMAT 설비 Abnormal Step 전체 목록. STATUS 셀에서 직접 변경 후 SAVE.",
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

# ── DML 쿼리 (INSERT / UPDATE / DELETE) ──────────────────────────────────────
DML_QUERIES: dict[str, SqlDmlDef] = {
    "amat_keyword_insert": SqlDmlDef(
        id="amat_keyword_insert",
        description="amat_keyword 테이블에 name 값을 INSERT.",
        sql="INSERT INTO amat_keyword (name) VALUES (:name)",
    ),
    "amat_abnormal_step_update_status": SqlDmlDef(
        id="amat_abnormal_step_update_status",
        description="amat_abnormal_step 테이블의 status를 idx 기준으로 UPDATE.",
        sql="UPDATE amat_abnormal_step SET status = :status WHERE idx = :idx",
    ),
}

"""AMAT 설비관리 페이지 쿼리 모음.

배경:
  AMAT 관련 테이블(amat_abnormal_step, amat_keyword)은 물리적으로는 DRAM DB 에
  속해 있지만, "단순 조회"가 전부인 VNAND/DRAM 페이지와 달리 AMAT 설비관리
  페이지에서는 STATUS 인라인 편집/SAVE 같은 작업이 들어간다. 따라서
  /amat 라우터 + 전용 페이지 + 전용 쿼리 모듈로 분리해 관리한다.

DB 연결:
  - source 식별자는 그대로 "dram" 을 사용 (mariadb._get_engine("dram")).
  - 즉, AMAT 쿼리는 DRAM DB 엔진에서 실행된다.

STATUS 값 집합 (PR ②):
  - amat_abnormal_step.status 는 'ERROR' / 'CHECKED' / 'SUCCESS' 셋 중 하나.
  - "미처리" 의 정의 = status <> 'SUCCESS'.
"""
from app.queries._base import SqlDmlDef, SqlQueryDef


# AbnormalStep 공통 SELECT — no_treat / all 둘 다 같은 컬럼/정렬을 쓰도록 한 곳에서 관리.
#   * idx          : PK (UPDATE 의 바인딩 키, 프론트에서 select 의 data-idx)
#   * status       : 인라인 편집 대상
#   * 그 외 컬럼들은 표시용
_AMAT_ABNORMAL_STEP_COLUMNS = """
    idx,
    es_id,
    file_path,
    reason,
    insert_datetime,
    status
"""

# ── SELECT 쿼리 ──────────────────────────────────────────────────────────────
QUERIES: dict[str, SqlQueryDef] = {
    # ① 미처리 목록 — status <> 'SUCCESS' 만. 페이지 첫 진입 / 대시보드 카드 점프 대상.
    "amat_abnormal_steps_no_treat": SqlQueryDef(
        id="amat_abnormal_steps_no_treat",
        title="AMAT 비정상 스텝 (미처리)",
        description="status 가 SUCCESS 가 아닌 AMAT 비정상 스텝 목록. STATUS 셀에서 직접 변경 후 SAVE.",
        sql=f"""
            SELECT
                {_AMAT_ABNORMAL_STEP_COLUMNS}
            FROM amat_abnormal_step
            WHERE status <> 'SUCCESS'
            ORDER BY insert_datetime DESC
            LIMIT 1000
        """,
    ),

    # ② 전체 목록 — SUCCESS 포함. 과거 건의 STATUS 정정도 가능.
    "amat_abnormal_steps_all": SqlQueryDef(
        id="amat_abnormal_steps_all",
        title="AMAT 비정상 스텝 (전체)",
        description="AMAT 비정상 스텝 전체 목록 (SUCCESS 포함). STATUS 셀에서 직접 변경 후 SAVE.",
        sql=f"""
            SELECT
                {_AMAT_ABNORMAL_STEP_COLUMNS}
            FROM amat_abnormal_step
            ORDER BY insert_datetime DESC
            LIMIT 1000
        """,
    ),

    # ③ AMAT Keyword 목록 — special_tab(panel-amat-keyword) 으로만 표시되므로 hidden=True.
    #    일반 쿼리 탭 목록에서는 제외되고, /amat/keyword/list 엔드포인트에서 sql 만 재사용한다.
    "amat_keyword_list": SqlQueryDef(
        id="amat_keyword_list",
        title="AMAT Abnormal Keyword",
        description="amat_keyword 테이블 전체 조회.",
        sql="""
            SELECT id, name FROM amat_keyword ORDER BY id
        """,
        hidden=True,
    ),
}


# ── DML 쿼리 (INSERT / UPDATE / DELETE) ──────────────────────────────────────
#   `amat_abnormal_step_update_status` 는 PR ② 에서 추가됨.
#   API 측에서 한 트랜잭션 안에서 N건을 모두 적용하고, 한 건이라도 실패하면
#   전체 ROLLBACK 한다 (all-or-nothing — 사용자 요구).
DML_QUERIES: dict[str, SqlDmlDef] = {
    "amat_keyword_insert": SqlDmlDef(
        id="amat_keyword_insert",
        description="amat_keyword 테이블에 name 값을 INSERT.",
        sql="INSERT INTO amat_keyword (name) VALUES (:name)",
    ),
    "amat_abnormal_step_update_status": SqlDmlDef(
        id="amat_abnormal_step_update_status",
        description=(
            "amat_abnormal_step 의 status 를 idx 기준으로 UPDATE. "
            "status 는 'ERROR' / 'CHECKED' / 'SUCCESS' 셋 중 하나 — "
            "허용값 검증은 API 레이어 (app/routers/amat.py) 의 화이트리스트에서 수행한다."
        ),
        sql="UPDATE amat_abnormal_step SET status = :status WHERE idx = :idx",
    ),
}

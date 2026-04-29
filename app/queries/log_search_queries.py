"""Log Search 페이지에서 사용하는 쿼리 화이트리스트.

============================================================
사용자(운영자)가 직접 수정하는 파일입니다.
============================================================

목적:
  사이드바의 "Log Search" 페이지에서 입력한 1개의 문자열 파라미터
  (`root_lot_wf_id` 등)를 기준으로, **여러 테이블**을 한 번에 조회해
  결과를 통합 DataTable 한 개로 보여준다. 각 행에는 파일 절대경로
  컬럼(`path`)이 포함되며, 행의 다운로드 아이콘을 클릭하면
  `/files/download?path=...` 로 실제 파일을 다운로드한다.

설계 약속(중요):
  - 모든 검색 대상 테이블은 검색 컬럼 이름이 동일해야 한다.
    기본값은 `root_lot_wf_id` 이며 SEARCH_COLUMN 으로 한 번에 바꿀 수 있다.
  - SQL 은 항상 `:param` 바인딩으로만 사용한다(인젝션 방지).
  - SELECT 컬럼에는 반드시 절대경로를 담은 컬럼 한 개가 있어야 하며,
    그 컬럼 이름은 `path_column` 으로 지정한다(테이블마다 달라도 됨).
    내부적으로는 항상 `path` alias 로 정규화된다.
  - 결과 행 폭주를 막기 위해 SQL 끝에 LIMIT 을 두는 것을 권장한다.

새 테이블 추가/수정 방법:
  1) LOG_SEARCH_QUERIES 리스트에 LogSearchQueryDef 항목을 추가한다.
  2) 서버 재시작. 끝.

예시:
    LogSearchQueryDef(
        source="vnand",                 # "vnand" | "dram"
        table_label="vnand.parsing_results",
        path_column="file_path",        # 결과의 절대경로 컬럼명
        sql='''
            SELECT
                root_lot_wf_id,
                product,
                tkin_time,
                file_path
            FROM parsing_results
            WHERE root_lot_wf_id = :param
            ORDER BY tkin_time DESC
            LIMIT 1000
        ''',
    ),
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ------------------------------------------------------------
# 검색 파라미터 컬럼 이름
#
# 사용자 답변에 따라 모든 검색 대상 테이블이 동일한 컬럼명을 가진다고
# 가정. 만약 이름을 바꾸려면 이 한 곳만 고치면 된다.
# (실제 SQL 의 WHERE 절에는 :param 바인딩으로 들어가므로 컬럼명은
#  WHERE 절 작성에만 영향. SQL 자체에 직접 적어두면 됨.)
# ------------------------------------------------------------
SEARCH_COLUMN: str = "root_lot_wf_id"

Source = Literal["vnand", "dram"]


@dataclass
class LogSearchQueryDef:
    """Log Search 화이트리스트 항목.

    필드:
        source       : 어느 DB 인지 ("vnand" | "dram")
        table_label  : UI/결과의 source 컬럼에 함께 표시될 라벨.
                       보통 "vnand.parsing_results" 처럼 db.table 형태.
        path_column  : 결과 row 에서 절대경로가 들어 있는 컬럼명.
                       (서비스 단계에서 항상 path 라는 alias 로 정규화됨)
        sql          : SQL 본문. 반드시 `:param` 바인딩 1개를 사용한다.
        extra_columns: UI 통합 테이블에 함께 보여줄 추가 컬럼명 목록.
                       비어 있으면 source/table/path 만 보여준다.
                       (지정하지 않은 컬럼은 통합 테이블에 노출되지 않음)
    """
    source: Source
    table_label: str
    path_column: str
    sql: str
    extra_columns: list[str] = field(default_factory=list)


# ============================================================
# 검색 대상 화이트리스트 — **운영 환경에 맞게 직접 수정**
# ============================================================
#
# 아래 항목들은 placeholder 예시입니다. 실제 운영 DB 의 테이블/컬럼명을
# 확인 후 SQL 을 적절히 고쳐 주세요. 행의 일부 또는 전부를 지워도 됩니다.
#
# 주의:
#   - 각 SQL 의 끝에는 LIMIT 을 두는 것을 권장합니다(파일 수 폭주 방지).
#   - SELECT 한 컬럼 중 하나는 path_column 으로 지정한 컬럼이어야 합니다.
#   - 통합 테이블에 노출하려는 부가 정보는 extra_columns 에 적어 주세요.
# ============================================================
LOG_SEARCH_QUERIES: list[LogSearchQueryDef] = [
    # ---------- VNAND ----------
    LogSearchQueryDef(
        source="vnand",
        table_label="vnand.parsing_results",
        path_column="file_path",
        sql="""
            SELECT
                root_lot_wf_id,
                product,
                tkin_time,
                file_path
            FROM parsing_results
            WHERE root_lot_wf_id = :param
            ORDER BY tkin_time DESC
            LIMIT 1000
        """,
        extra_columns=["product", "tkin_time"],
    ),

    # ---------- DRAM ----------
    LogSearchQueryDef(
        source="dram",
        table_label="dram.parsing_results",
        path_column="file_path",
        sql="""
            SELECT
                root_lot_wf_id,
                product,
                tkin_time,
                file_path
            FROM parsing_results
            WHERE root_lot_wf_id = :param
            ORDER BY tkin_time DESC
            LIMIT 1000
        """,
        extra_columns=["product", "tkin_time"],
    ),

    # 필요한 만큼 항목 추가...
    # LogSearchQueryDef(
    #     source="dram",
    #     table_label="dram.amat_steps",
    #     path_column="abs_path",
    #     sql='''
    #         SELECT
    #             root_lot_wf_id,
    #             step_name,
    #             abs_path
    #         FROM amat_steps
    #         WHERE root_lot_wf_id = :param
    #         LIMIT 1000
    #     ''',
    #     extra_columns=["step_name"],
    # ),
]

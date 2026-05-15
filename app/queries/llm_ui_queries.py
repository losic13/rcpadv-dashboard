"""LLM UI 사용 이력 페이지(/llm-ui-history)에서 사용하는 SQL 정의.

login_history_queries.py 와 동일한 화이트리스트 패턴.

설계 메모:
  - 쿼리는 :start, :end 두 개의 datetime 바인딩을 사용한다.
    [start, end) 반-개방 구간 — end 는 포함하지 않음.
  - PostgreSQL 에 저장된 timestamp 값을 *그대로* 사용한다. 타임존 변환은
    적용하지 않는다 — login_history 와 동일한 정책 (사용자 요청).
  - SELECT 결과 컬럼 (login_history 와 동일 형태로 정규화 필요):
      day        : 'YYYY-MM-DD' (DATE() / date_trunc('day') 등 사용)
      user_id    : 원본 사용자 ID (개발자/고객 분류는 파이썬에서 처리)
      use_count  : 해당 (day, user_id) 의 LLM UI 사용 횟수

  - 두 쿼리:
      LLM_UI_USAGE_SQL          : 전체 로그 기반 집계
      (현재는 한 쿼리 결과를 파이썬에서 전체 / 고객(개발자 제외) 두 시리즈로
       나눠 그리므로 SQL 은 한 본만 있으면 충분하다 — login_history 와 동일.)

  - **사용자가 직접 SQL 을 채워 넣을 때까지 placeholder 로 둔다.**
    실제 운영용 SQL 로 교체할 때 결과 컬럼명 ``day``, ``user_id``,
    ``use_count`` 만 맞춰 주면 서비스 코드는 그대로 동작한다.
"""
from __future__ import annotations

# ============================================================
# DB 소스
# ============================================================
# PostgreSQL 엔진 식별자 (app.repositories.postgres._get_engine 와 매칭).
LLM_UI_SOURCE = "llm_pg"


# ============================================================
# SQL — (day, user_id, use_count) 단위로 미리 GROUP BY
# ============================================================
# TODO(user): 운영 테이블/컬럼명에 맞춰 SQL 을 작성해 주세요.
#
# 기대하는 결과 스키마 (서비스 레이어가 그대로 가정합니다):
#   day        : DATE   — 'YYYY-MM-DD' 로 그루핑된 일자
#   user_id    : TEXT   — 원본 사용자 ID
#   use_count  : INTEGER — 해당 (day, user_id) 의 사용 횟수
#
# 바인딩 파라미터:
#   :start (timestamp, 포함)
#   :end   (timestamp, 미포함 — end 다음날 0시)
#
# 예시 (참고용):
#   SELECT
#       (date_time)::date  AS day,
#       user_id,
#       COUNT(*)           AS use_count
#   FROM llm_ui.usage_log
#   WHERE date_time >= :start
#     AND date_time <  :end
#   GROUP BY 1, 2
#   ORDER BY 1 ASC, 2 ASC
LLM_UI_USAGE_SQL = """
    -- TODO: 운영 SQL 로 교체하세요. 결과 컬럼은 (day, user_id, use_count).
    SELECT
        CAST(NULL AS DATE)    AS day,
        CAST(NULL AS TEXT)    AS user_id,
        CAST(NULL AS INTEGER) AS use_count
    WHERE :start IS NOT NULL
      AND :end   IS NOT NULL
      AND 1 = 0
"""

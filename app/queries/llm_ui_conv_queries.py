"""LLM UI 사용 이력(/llm-ui-conversations) 페이지에서 사용하는 SQL 정의.

이 페이지는 LLM 대화 메시지 원본 행을 ``created_at`` 범위로 조회한 뒤,
파이썬 레이어에서 다음 두 가지 뷰로 가공해 보여준다:
    1) 타임라인 뷰  : 사용자 구분 없이 created_at 시간순으로 모든 행을 정렬
    2) 사용자별 뷰  : user_id → conversation_id → (seq 순) 메시지로 그룹

기대 결과 컬럼 (서비스 레이어가 그대로 가정):
    conversation_id : TEXT — 대화 묶음 ID
    id              : TEXT — 메시지 ID
    seq             : INTEGER — 대화 내 메시지 순서
    role            : TEXT — 'user' 또는 'assistant'
    content         : TEXT — 메시지 본문
    trace           : TEXT/JSONB — 메시지 trace (raw JSON; 화면에서 모달로 표시)
    created_at      : TIMESTAMP — 메시지 생성 시각
    parent_id       : TEXT — 부모 메시지 id (없으면 NULL)
    user_id         : TEXT — 사용자 ID

바인딩 파라미터:
    :start (timestamp, 포함)
    :end   (timestamp, 미포함 — 페이지에서 받은 end 다음날 0시)

설계 메모:
  - PostgreSQL timestamp 값을 *그대로* 사용한다 (login_history / llm_ui_history
    와 동일한 정책 — 별도 타임존 변환 없음).
  - 사용자 결정(Q3=C): 행 수 **제한 없음**. SQL 에 LIMIT 을 두지 않는다.
    운영 데이터가 폭증하면 추후 페이지네이션을 도입할 것.
  - 사용자가 직접 SQL 을 채워 넣을 때까지 placeholder 로 둔다.
    실제 운영용 SQL 로 교체할 때 결과 컬럼명 9개만 맞춰 주면 서비스 코드는
    그대로 동작한다.
"""
from __future__ import annotations

# ============================================================
# DB 소스
# ============================================================
# PostgreSQL 엔진 식별자 (app.repositories.postgres._get_engine 와 매칭).
# 기존 llm_ui_history 와 동일 인스턴스를 재사용한다.
LLM_UI_CONV_SOURCE = "llm_pg"


# ============================================================
# SQL — 대화 메시지 원본 행 조회
# ============================================================
# TODO(user): 운영 테이블/컬럼명에 맞춰 SQL 을 작성해 주세요.
#
# 기대하는 결과 스키마 (서비스 레이어가 그대로 가정합니다):
#   conversation_id : TEXT
#   id              : TEXT
#   seq             : INTEGER
#   role            : TEXT       — 'user' / 'assistant'
#   content         : TEXT
#   trace           : TEXT/JSONB — 원본 그대로 (모달에서 pretty-print)
#   created_at      : TIMESTAMP
#   parent_id       : TEXT (nullable)
#   user_id         : TEXT
#
# 바인딩 파라미터:
#   :start (timestamp, 포함)
#   :end   (timestamp, 미포함 — end 다음날 0시)
#
# 예시 (참고용):
#   SELECT
#       conversation_id,
#       id,
#       seq,
#       role,
#       content,
#       trace,
#       created_at,
#       parent_id,
#       user_id
#   FROM llm_ui.messages
#   WHERE created_at >= :start
#     AND created_at <  :end
#   ORDER BY created_at ASC, conversation_id ASC, seq ASC
LLM_UI_CONV_SQL = """
    -- TODO: 운영 SQL 로 교체하세요.
    -- 결과 컬럼: conversation_id, id, seq, role, content, trace,
    --           created_at, parent_id, user_id
    SELECT
        CAST(NULL AS TEXT)      AS conversation_id,
        CAST(NULL AS TEXT)      AS id,
        CAST(NULL AS INTEGER)   AS seq,
        CAST(NULL AS TEXT)      AS role,
        CAST(NULL AS TEXT)      AS content,
        CAST(NULL AS TEXT)      AS trace,
        CAST(NULL AS TIMESTAMP) AS created_at,
        CAST(NULL AS TEXT)      AS parent_id,
        CAST(NULL AS TEXT)      AS user_id
    WHERE :start IS NOT NULL
      AND :end   IS NOT NULL
      AND 1 = 0
"""

"""사용자 접속 이력 페이지(/login-history)에서 사용하는 SQL 정의.

화이트리스트 형태로 한 곳에 모아 두며, 라우터/서비스에서 참조한다.

설계 메모:
  - 쿼리는 :start, :end 두 개의 datetime 바인딩을 사용한다.
    [start, end) 반-개방 구간 — end 는 포함하지 않음.
  - 시간대(KST) 변환은 SELECT 시점에 처리. DB 에는 datetime 컬럼이 어떤
    타임존으로 들어가 있든, KST(+09:00) 기준 날짜로 묶이도록
    `CONVERT_TZ(datetime, '+00:00', '+09:00')` 를 사용한다.
    *운영 DB 의 datetime 이 이미 KST 로 저장되어 있다면* 결과적으로
    UTC 로 9시간 빼고 다시 9시간 더하는 셈이 되어 같은 값이 나온다.
    (→ 정확한 동작은 운영 DB 컨벤션에 따라 SELECT 절을 조정하면 됨.)
  - SELECT 결과 컬럼:
      day        : 'YYYY-MM-DD' (KST 기준)
      user_id    : 원본 user_id (개발자/고객 분류는 파이썬에서 처리)
      login_count: 해당 (day, user_id) 의 login 액션 횟수
"""
from __future__ import annotations

# ============================================================
# DB 소스 / 테이블
# ============================================================
LOGIN_HISTORY_SOURCE = "vnand"  # advisor.app_server_user_log 가 위치한 DB

# ============================================================
# SQL — (day, user_id, login_count) 단위로 미리 GROUP BY
# ============================================================
# 한 사용자가 같은 날 N 번 로그인한 경우:
#   - "중복 포함 (총 로그인 수)" = SUM(login_count)
#   - "중복 제거 (고유 사용자 수)" = COUNT(DISTINCT user_id)
# 두 지표 모두 (day, user_id, login_count) 단위 결과로부터 파이썬에서
# 단순 집계로 계산 가능하다. → DB 단에서는 행 수를 줄여 전송 비용 감소.
LOGIN_HISTORY_SQL = """
    SELECT
        DATE(CONVERT_TZ(`datetime`, '+00:00', '+09:00')) AS day,
        user_id,
        COUNT(*)                                          AS login_count
    FROM advisor.app_server_user_log
    WHERE action = 'login'
      AND `datetime` >= :start
      AND `datetime` <  :end
    GROUP BY day, user_id
    ORDER BY day ASC, user_id ASC
"""

"""사용자 접속 이력 페이지(/login-history)에서 사용하는 SQL 정의.

화이트리스트 형태로 한 곳에 모아 두며, 라우터/서비스에서 참조한다.

설계 메모:
  - 쿼리는 :start, :end 두 개의 datetime 바인딩을 사용한다.
    [start, end) 반-개방 구간 — end 는 포함하지 않음.
  - DB 의 `date_time` 컬럼 값을 *그대로* 사용한다. 타임존 변환(CONVERT_TZ)
    은 적용하지 않는다 — DB 에 저장된 벽시계 값을 그대로 읽어 그 기준으로
    그루핑/필터링한다. (운영 정책상 date_time 의 타임존 해석은 호출 측이
    책임지지 않으며, 사용자가 입력한 일자 = DB 의 date_time 일자 그대로.)
  - SELECT 결과 컬럼:
      day        : 'YYYY-MM-DD' (DB date_time 의 DATE() 값)
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
#
# *타임존 변환은 의도적으로 하지 않는다.* DB 에 적힌 date_time 값을 그대로
# 비교/그루핑한다. (사용자 요청)
LOGIN_HISTORY_SQL = """
    SELECT
        DATE(`date_time`) AS day,
        user_id,
        COUNT(*)          AS login_count
    FROM advisor.app_server_user_log
    WHERE action = 'login'
      AND `date_time` >= :start
      AND `date_time` <  :end
    GROUP BY day, user_id
    ORDER BY day ASC, user_id ASC
"""

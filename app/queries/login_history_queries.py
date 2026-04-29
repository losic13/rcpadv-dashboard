"""사용자 접속 이력 페이지(/login-history)에서 사용하는 SQL 정의.

화이트리스트 형태로 한 곳에 모아 두며, 라우터/서비스에서 참조한다.

설계 메모:
  - 쿼리는 :start, :end 두 개의 datetime 바인딩을 사용한다.
    [start, end) 반-개방 구간 — end 는 포함하지 않음.
    *바인딩 값은 KST 벽시계 기준의 naive datetime* 으로 들어온다.
    (예: KST 2026-04-29 00:00 ~ 2026-04-30 00:00)
  - DB 의 `date_time` 컬럼은 UTC 로 저장된다고 가정한다 (운영 컨벤션).
    그래서 WHERE 절에서도 `CONVERT_TZ(date_time, '+00:00', '+09:00')`
    으로 KST 로 변환한 값과 비교한다. 이렇게 해야 KST 의 하루 경계가
    DB 의 UTC 행과 정확히 매칭된다 (예: KST 04-29 02:00 = UTC 04-28 17:00).
    이전 버전은 WHERE 가 raw `date_time` 을 KST 벽시계 값과 직접 비교했기
    때문에 KST 0~9시 사이의 로그인이 누락(=다음날로 밀림)되는 버그가 있었다.
    → "통합 대시보드 오늘 카드는 0인데 사용자 접속 이력 페이지에는 보임"
       증상의 근본 원인.
  - SELECT 의 `DATE(CONVERT_TZ(...))` 는 일자 그루핑용. WHERE 의 변환은
    범위 매칭용으로 별도 적용 (인덱스 범위 활용은 손해를 보지만, 정확도 우선).
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
        DATE(CONVERT_TZ(`date_time`, '+00:00', '+09:00')) AS day,
        user_id,
        COUNT(*)                                           AS login_count
    FROM advisor.app_server_user_log
    WHERE action = 'login'
      AND CONVERT_TZ(`date_time`, '+00:00', '+09:00') >= :start
      AND CONVERT_TZ(`date_time`, '+00:00', '+09:00') <  :end
    GROUP BY day, user_id
    ORDER BY day ASC, user_id ASC
"""

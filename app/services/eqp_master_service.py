"""eqp_master 'valid 설비' 조회 SQL 호출 결과 합집합 서비스.

용도
────
/es/history (종합 처리 이력) 페이지의 parsing-index-1 쿼리에 'eqp_id 필터'
를 동적으로 주입하기 위해, vnand / dram 두 DB 에서 각각

    settings.ES_HISTORY_VALID_EQP_CALL_SQL
        (기본: ``CALL eqp_master.prc_get_valid_equipment(:param)``)

을 실행하고 결과의 eqp_id 컬럼을 합집합(∪) 으로 반환한다.

호출 SQL 은 ``.env`` 의 ``ES_HISTORY_VALID_EQP_CALL_SQL`` 로 자유롭게
교체 가능하다 (프로시저 이름/스키마 변경, SELECT 로 임시 대체 등).
반드시 ``:param`` 바인딩 자리표시자 1개를 포함해야 한다.

정책 (사용자 결정 사항)
─────────────────────
- Q4: 캐시 없음 — 매 호출 시 두 DB 의 SQL 을 직접 실행한다.
- Q5: 빈 결과/실패도 그대로 노출 — 둘 다 실패하면 빈 set 반환,
        caller (es_service.run_history_overview) 는 빈 set 이어도
        terms 필터를 그대로 주입하여 ES 결과가 0건이 되도록 한다.
- Q3: 프로시저 인자는 settings.ES_HISTORY_VALID_EQP_PARAM (기본 3).
- Q2: vnand ∪ dram (합집합, 중복 제거).

반환 컨벤션
──────────
``get_valid_eqp_ids() -> tuple[set[str], dict[str, str | None]]``

- 첫 번째: 합집합 set[str] — eqp_id 들. 부분 성공이면 성공한 쪽만 포함.
- 두 번째: per-source 에러 메시지 dict, 예 ``{"vnand": None, "dram": "..."}``
            (None = 성공)

이 모듈은 SQL 결과 컬럼 이름이 ``eqp_id`` / ``EQP_ID`` /
``EQUIPMENT_ID`` 등 어느 것이든, 또는 단일 컬럼이면 그 컬럼을 안전하게
추출한다.
"""
from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.logger import get_logger
from app.repositories import mariadb

log = get_logger("service.eqp_master")

# 허용 컬럼 이름 (case-insensitive). 위→아래 우선순위로 검색.
# 결과 컬럼은 운영 DB 구현에 따라 ``eqp_id`` / ``EQP_ID`` / ``EQUIPMENT_ID``
# 중 무엇이든 올 수 있어, _pick_eqp_value() 에서 첫 컬럼/표준 컬럼명을 모두 시도.
_EQP_ID_COLS = ("eqp_id", "EQP_ID", "EquipmentId", "equipment_id", "EQUIPMENT_ID")


def _pick_eqp_value(row: dict[str, Any], columns: list[str]) -> str | None:
    """row 에서 eqp_id 컬럼 하나를 안전하게 추출.

    1순위: 알려진 컬럼명 (대소문자 변형 포함)
    2순위: 컬럼이 정확히 1개면 그 단일 컬럼
    그 외: None (스킵)
    """
    # 1) 정해진 후보 컬럼명
    for cand in _EQP_ID_COLS:
        if cand in row and row[cand] is not None:
            v = str(row[cand]).strip()
            return v or None
    # case-insensitive 매칭 한 번 더
    lower_map = {c.lower(): c for c in columns}
    for cand in _EQP_ID_COLS:
        actual = lower_map.get(cand.lower())
        if actual and row.get(actual) is not None:
            v = str(row[actual]).strip()
            return v or None
    # 2) 단일 컬럼 fallback
    if len(columns) == 1:
        v = row.get(columns[0])
        if v is not None:
            s = str(v).strip()
            return s or None
    return None


def _fetch_one_source(source: str, param: int) -> tuple[set[str], str | None]:
    """단일 DB(``vnand`` 또는 ``dram``) 에서 SQL 호출 → eqp_id set 반환.

    호출 SQL 은 ``settings.ES_HISTORY_VALID_EQP_CALL_SQL`` 을 그대로 사용.
    ``:param`` 자리표시자는 항상 ``{"param": <int>}`` 로 바인딩된다.

    실패 시 (빈 set, error_message) 를 반환하여 caller 가 부분 성공을
    처리할 수 있게 한다.
    """
    sql = settings.ES_HISTORY_VALID_EQP_CALL_SQL
    t0 = time.perf_counter()
    try:
        columns, rows = mariadb.execute(source, sql, {"param": int(param)})
    except Exception as e:
        log.error("[eqp_master] %s 호출 실패: %s (sql=%r)", source, e, sql)
        return set(), str(e)

    out: set[str] = set()
    for r in rows:
        v = _pick_eqp_value(r, columns)
        if v:
            out.add(v)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    log.info(
        "[eqp_master] %s 호출 OK — %d rows → %d unique eqp_id (%dms, cols=%s)",
        source, len(rows), len(out), elapsed_ms, columns,
    )
    return out, None


def get_valid_eqp_ids(
    param: int | None = None,
) -> tuple[set[str], dict[str, str | None]]:
    """vnand + dram 두 DB 의 프로시저 결과 합집합을 반환.

    인자
    ────
    param: 프로시저에 넘길 정수 인자. None 이면 settings 의 기본값을 사용.

    반환
    ────
    (eqp_ids: set[str], errors: dict[str, str | None])

    - 둘 다 성공: errors == {"vnand": None, "dram": None}
    - 부분 성공: 성공한 쪽만 포함되고, 실패한 쪽 errors 에 메시지
    - 둘 다 실패: 빈 set, 양쪽 모두 에러 메시지
    """
    p = int(settings.ES_HISTORY_VALID_EQP_PARAM if param is None else param)

    s_vnand, err_vnand = _fetch_one_source("vnand", p)
    s_dram, err_dram = _fetch_one_source("dram", p)

    union = s_vnand | s_dram
    errors = {"vnand": err_vnand, "dram": err_dram}

    log.info(
        "[eqp_master] union: %d (vnand=%d, dram=%d, errors=%s)",
        len(union), len(s_vnand), len(s_dram),
        {k: (v[:80] if v else None) for k, v in errors.items()},
    )
    return union, errors

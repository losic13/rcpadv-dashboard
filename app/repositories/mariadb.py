"""MariaDB 커넥션/실행 계층.

- VNAND, DRAM 두 엔진을 lazy-init 으로 보관
- SQLAlchemy 풀(size=5) 사용
- 단순한 execute() 함수 하나만 제공: (sql, params) -> (columns, rows)
- 쿼리 타임아웃은 app 레벨에서 제어 (asyncio 사용 측에서 wait_for)
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Row

from app.config import settings


# ---- 엔진 (lazy-init 싱글턴) ----
_engines: dict[str, Engine] = {}


def _get_engine(source: str) -> Engine:
    if source in _engines:
        return _engines[source]

    if source == "vnand":
        url = settings.vnand_db_url()
    elif source == "dram":
        url = settings.dram_db_url()
    else:
        raise ValueError(f"Unknown source: {source}")

    engine = create_engine(
        url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
        future=True,
    )
    _engines[source] = engine
    return engine


def execute(source: str, sql: str, params: dict[str, Any] | None = None) -> tuple[list[str], list[dict]]:
    """SQL을 실행하고 (columns, rows-as-dicts) 를 반환.

    - source: "vnand" | "dram"
    - params: None 이면 바인딩 없이 실행
    - SELECT 결과만 가공. 행 수 제한은 SQL 자체의 LIMIT 으로 강제하는 것을 권장.
    """
    engine = _get_engine(source)
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        columns: list[str] = list(result.keys())
        rows: list[dict] = [_row_to_dict(r, columns) for r in result.fetchall()]
        return columns, rows


def _row_to_dict(row: Row, columns: list[str]) -> dict:
    """Row -> dict (datetime 등 JSON 직렬화 가능하게 문자열로)."""
    out = {}
    for col, val in zip(columns, row):
        if val is None:
            out[col] = None
        elif isinstance(val, (str, int, float, bool)):
            out[col] = val
        else:
            # datetime, date, Decimal, bytes 등은 문자열로
            try:
                out[col] = str(val)
            except Exception:
                out[col] = None
    return out


def execute_dml(source: str, sql: str, params: dict[str, Any] | None = None) -> int:
    """DML(INSERT/UPDATE/DELETE) 실행 후 커밋. 영향받은 행 수를 반환."""
    engine = _get_engine(source)
    with engine.begin() as conn:           # begin() → 자동 COMMIT / 예외 시 ROLLBACK
        result = conn.execute(text(sql), params or {})
        return result.rowcount


def execute_dml_many(
    source: str,
    sql: str,
    params_list: list[dict[str, Any]],
) -> int:
    """동일한 DML(SQL) 을 N건의 파라미터로 **단일 트랜잭션** 에서 실행.

    - 한 건이라도 예외가 발생하면 전체 ROLLBACK (all-or-nothing).
    - 정상 완료 시 영향받은 총 행 수를 반환 (Σ rowcount).
    - params_list 가 비어 있으면 0 을 반환하고 아무 것도 실행하지 않는다.

    사용 예: AMAT Abnormal Step 의 STATUS 다중 UPDATE — 사용자가 SAVE 버튼을
    누르면 변경된 행 N건을 한 번에 보내고, 한 건이라도 실패하면 모두 폐기한다.
    """
    if not params_list:
        return 0
    engine = _get_engine(source)
    stmt = text(sql)
    total = 0
    with engine.begin() as conn:           # 단일 트랜잭션 — 예외 시 자동 ROLLBACK
        for params in params_list:
            result = conn.execute(stmt, params)
            total += (result.rowcount or 0)
    return total


def dispose_all() -> None:
    """앱 종료 시 호출."""
    for eng in _engines.values():
        eng.dispose()
    _engines.clear()

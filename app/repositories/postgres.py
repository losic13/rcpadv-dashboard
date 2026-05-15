"""PostgreSQL 커넥션/실행 계층.

- LLM UI 사용 이력(/llm-ui-history) 페이지가 사용하는 PG DB 용.
- MariaDB(:mod:`app.repositories.mariadb`) 와 동일한 패턴:
    - SQLAlchemy 풀(size=5) sync engine 을 lazy-init 으로 보관
    - 단순한 ``execute()`` 함수 하나로 (columns, rows) 반환
- 드라이버는 psycopg2 (``postgresql+psycopg2://...``).

타임존:
    DB 의 timestamp 값을 별도 변환 없이 그대로 비교/그루핑한다 — login_history
    페이지와 동일한 정책 (사용자 요청).
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

    if source == "llm_pg":
        url = settings.llm_pg_db_url()
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


def execute(
    source: str,
    sql: str,
    params: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict]]:
    """SQL 을 실행하고 (columns, rows-as-dicts) 를 반환.

    - source: 현재 ``"llm_pg"`` 만 지원
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


def dispose_all() -> None:
    """앱 종료 시 호출."""
    for eng in _engines.values():
        eng.dispose()
    _engines.clear()

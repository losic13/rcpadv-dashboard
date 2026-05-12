"""쿼리 정의 공통 타입."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParamType = Literal["string", "int", "date", "datetime"]


@dataclass
class ParamDef:
    """쿼리 파라미터 정의 (대부분의 쿼리는 사용 안 함)."""
    name: str
    label: str
    type: ParamType = "string"
    default: Any = None
    required: bool = False


@dataclass
class SqlQueryDef:
    """MariaDB SELECT 쿼리 정의."""
    id: str
    title: str                      # UI 표시 한글 제목
    sql: str
    description: str = ""
    params: list[ParamDef] = field(default_factory=list)
    show_in_dashboard: bool = False  # 통합 대시보드 카드 노출
    hidden: bool = False             # True면 source_page 탭 목록에서 제외 (special_tab 등)


@dataclass
class SqlDmlDef:
    """MariaDB DML(INSERT/UPDATE/DELETE) 쿼리 정의."""
    id: str
    description: str    # 용도 설명 (유지관리용)
    sql: str            # SQLAlchemy :param 바인딩 형식


@dataclass
class EsQueryDef:
    """Elasticsearch DSL 쿼리 정의."""
    id: str
    title: str
    index: str
    body: dict[str, Any]
    description: str = ""
    params: list[ParamDef] = field(default_factory=list)
    show_in_dashboard: bool = False

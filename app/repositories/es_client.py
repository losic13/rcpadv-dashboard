"""Elasticsearch 8.x 클라이언트.

- DSL(JSON) 쿼리 실행만 담당
- search() / get() / update() 호출 결과를 그대로 dict 로 반환 (가공은 service 에서)
"""
from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from app.config import settings


_client: Elasticsearch | None = None


def get_client() -> Elasticsearch:
    global _client
    if _client is not None:
        return _client

    kwargs: dict[str, Any] = {
        "hosts": settings.es_hosts_list(),
        "verify_certs": settings.ES_VERIFY_CERTS,
        "request_timeout": settings.QUERY_TIMEOUT_SECONDS,
    }
    if settings.ES_USERNAME:
        kwargs["basic_auth"] = (settings.ES_USERNAME, settings.ES_PASSWORD)

    _client = Elasticsearch(**kwargs)
    return _client


def search(index: str, body: dict[str, Any]) -> dict[str, Any]:
    """DSL 쿼리를 실행하고 raw response(dict)를 반환."""
    client = get_client()
    return client.search(index=index, body=body).body


def get_doc(index: str, doc_id: str) -> dict[str, Any]:
    """단일 Document를 _id 로 조회. 존재하지 않으면 NotFoundError 발생."""
    client = get_client()
    return client.get(index=index, id=doc_id).body


def update_doc(index: str, doc_id: str, partial: dict[str, Any]) -> dict[str, Any]:
    """Partial update — ES의 doc 파라미터로 지정한 필드만 덮어쓴다."""
    client = get_client()
    return client.update(index=index, id=doc_id, body={"doc": partial}).body


def close() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None

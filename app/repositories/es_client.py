"""Elasticsearch 8.x 클라이언트.

- DSL(JSON) 쿼리 실행만 담당
- search() 호출 결과를 그대로 dict 로 반환 (가공은 service 에서)
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


def close() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None

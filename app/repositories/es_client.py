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


def get_doc(index: str, doc_id: str) -> dict[str, Any]:
    """단일 _id 조회 (GET /<index>/_doc/<id>).

    인덱스 패턴(와일드카드) 도 허용된다.  client 가 모든 인덱스를 살펴
    가장 매치되는 doc 을 반환한다.  doc 이 없으면 NotFoundError 가 발생.

    반환은 raw response (dict) 그대로:
        { "_index": "...", "_id": "...", "_source": {...}, "found": true, ... }
    """
    client = get_client()
    return client.get(index=index, id=doc_id).body


def update_doc(index: str, doc_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    """단일 _id partial update (POST /<index>/_update/<id>).

    `index` 는 반드시 **구체 인덱스 이름** 이어야 한다 (와일드카드 불가).
    호출하는 쪽에서 사전에 search/get 으로 응답의 `_index` 를 얻어 그대로
    전달하는 패턴을 권장.

    `doc` 은 partial source 로 머지된다 (Elasticsearch update API 의 표준 동작).
    """
    client = get_client()
    return client.update(index=index, id=doc_id, body={"doc": doc}).body


def close() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None

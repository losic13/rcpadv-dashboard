"""Elasticsearch DSL 쿼리 모음.

각 쿼리는 (index, body) 형태. body 는 ES DSL 그대로.
"""
from app.queries._base import EsQueryDef

QUERIES: dict[str, EsQueryDef] = {
    "recent_logs": EsQueryDef(
        id="recent_logs",
        title="최근 로그 (1h)",
        description="최근 1시간 로그 — timestamp 내림차순 1000건.",
        index="logs-*",
        body={
            "size": 1000,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "range": {
                    "@timestamp": {"gte": "now-1h", "lte": "now"}
                }
            },
            "_source": ["@timestamp", "level", "service", "message"],
        },
        show_in_dashboard=True,
    ),
    "error_count_by_service": EsQueryDef(
        id="error_count_by_service",
        title="서비스별 에러 카운트 (24h)",
        description="최근 24시간 ERROR 레벨 로그를 service.keyword 별 집계.",
        index="logs-*",
        body={
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"level": "ERROR"}},
                        {"range": {"@timestamp": {"gte": "now-24h"}}},
                    ]
                }
            },
            "aggs": {
                "by_service": {
                    "terms": {"field": "service.keyword", "size": 50}
                }
            },
        },
    ),
}

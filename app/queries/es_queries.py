"""Elasticsearch DSL 쿼리 모음.

각 쿼리는 (index, body) 형태. body 는 ES DSL 그대로.

[Overview 전용 쿼리 — es_service.run_overview_*() 에서 직접 참조]
  OVERVIEW_INDEX1_AGG  : parsing-index-1-* · FILE_LAST_TIME 날짜별 집계
  OVERVIEW_INDEX2_AGG  : parsing-index-2-* · FILE_LAST_TIME 날짜별 집계
  OVERVIEW_TKIN_AGG    : parsing-index-2-* · meta.tkin_time 최근 2주 날짜별 집계

  ※ DSL은 테스트용이므로 실 환경에 맞게 덮어쓸 것.

[범용 쿼리 QUERIES — /es 탭 페이지(source_page.html)에서 사용]
"""
from app.queries._base import EsQueryDef

# ──────────────────────────────────────────────────────────────
# Overview Section A — parsing-index-1-* vs parsing-index-2-*
#   기준 필드: kafka.FILE_LAST_TIME (epoch_millis Long)
#   집계 단위: 날짜(day), 최근 30일
# ──────────────────────────────────────────────────────────────

OVERVIEW_INDEX1_AGG = EsQueryDef(
    id="overview_index1_agg",
    title="index-1 날짜별 집계",
    description="parsing-index-1-* · kafka.FILE_LAST_TIME 기준 날짜별 doc_count (최근 30일, 테스트 DSL)",
    index="parsing-index-1-*",
    body={
        "size": 0,
        "query": {
            "range": {
                "kafka.FILE_LAST_TIME": {
                    "gte": "now-30d/d",
                    "lte": "now/d",
                    "format": "epoch_millis",
                }
            }
        },
        "aggs": {
            "by_date": {
                "date_histogram": {
                    "field": "kafka.FILE_LAST_TIME",
                    "calendar_interval": "day",
                    "format": "yyyy-MM-dd",
                    "order": {"_key": "asc"},
                }
            }
        },
    },
)

OVERVIEW_INDEX2_AGG = EsQueryDef(
    id="overview_index2_agg",
    title="index-2 날짜별 집계",
    description="parsing-index-2-* · kafka.FILE_LAST_TIME 기준 날짜별 doc_count (최근 30일, 테스트 DSL)",
    index="parsing-index-2-*",
    body={
        "size": 0,
        "query": {
            "range": {
                "kafka.FILE_LAST_TIME": {
                    "gte": "now-30d/d",
                    "lte": "now/d",
                    "format": "epoch_millis",
                }
            }
        },
        "aggs": {
            "by_date": {
                "date_histogram": {
                    "field": "kafka.FILE_LAST_TIME",
                    "calendar_interval": "day",
                    "format": "yyyy-MM-dd",
                    "order": {"_key": "asc"},
                }
            }
        },
    },
)

# ──────────────────────────────────────────────────────────────
# Overview Section B — parsing-index-2-* · meta.tkin_time
#   기준 필드: meta.tkin_time (epoch_millis Long)
#   집계 단위: 날짜(day), 최근 14일(2주)
# ──────────────────────────────────────────────────────────────

OVERVIEW_TKIN_AGG = EsQueryDef(
    id="overview_tkin_agg",
    title="index-2 tkin_time 날짜별 집계",
    description="parsing-index-2-* · meta.tkin_time 기준 최근 2주 날짜별 doc_count (테스트 DSL)",
    index="parsing-index-2-*",
    body={
        "size": 0,
        "query": {
            "range": {
                "meta.tkin_time": {
                    "gte": "now-14d/d",
                    "lte": "now/d",
                    "format": "epoch_millis",
                }
            }
        },
        "aggs": {
            "by_date": {
                "date_histogram": {
                    "field": "meta.tkin_time",
                    "calendar_interval": "day",
                    "format": "yyyy-MM-dd",
                    "order": {"_key": "asc"},
                }
            }
        },
    },
)

# ──────────────────────────────────────────────────────────────
# 범용 쿼리 — /es 탭 페이지 (source_page.html)
# ──────────────────────────────────────────────────────────────
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

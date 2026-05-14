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

# ──────────────────────────────────────────────────────────────
# 설비별 처리현황 — product / maker / eqp_id × 날짜 매트릭스
#   페이지: /es/eqp-status
#   서비스: es_service.run_eqp_log_count_per_day()
#
#   ※ 아래 body 는 더미 템플릿이다. 사용자가 실제 운영 환경에 맞춰
#     인덱스 / 필드명 / 날짜 범위 / size 등을 직접 수정해 사용한다.
#
#   서비스 코드는 다음 4-Tier 중첩 aggregation 구조를 가정하고
#   flatten 한다 (이름은 반드시 그대로 유지):
#
#       aggregations
#         └ by_product       (terms)
#             └ by_maker     (terms)
#                 └ by_eqp_id  (terms)
#                     └ by_day   (date_histogram, format=yyyy-MM-dd,
#                                 min_doc_count=0)
#
#   min_doc_count: 0 으로 두면 데이터가 없는 날짜도 0 으로 채워진다.
# ──────────────────────────────────────────────────────────────

EQP_LOG_COUNT_PER_DAY = EsQueryDef(
    id="eqp_log_count_per_day",
    title="설비별 일자별 처리 건수",
    description="product × maker × eqp_id × 날짜 매트릭스 (더미 DSL — 운영 환경에 맞게 덮어쓸 것)",
    index="parsing-index-2-*",
    body={
        # ── ⚠️ 아래 DSL 은 더미. 실제 필드명/범위/사이즈는 수정 필요 ──
        "size": 0,
        "query": {
            "range": {
                "meta.tkin_time": {
                    "gte": "now-7d/d",
                    "lte": "now/d",
                    "format": "epoch_millis",
                }
            }
        },
        "aggs": {
            "by_product": {
                "terms": {"field": "product.keyword", "size": 100},
                "aggs": {
                    "by_maker": {
                        "terms": {"field": "maker.keyword", "size": 100},
                        "aggs": {
                            "by_eqp_id": {
                                "terms": {"field": "eqp_id.keyword", "size": 500},
                                "aggs": {
                                    "by_day": {
                                        "date_histogram": {
                                            "field": "meta.tkin_time",
                                            "calendar_interval": "day",
                                            "format": "yyyy-MM-dd",
                                            "min_doc_count": 0,
                                            "extended_bounds": {
                                                "min": "now-7d/d",
                                                "max": "now/d",
                                            },
                                            "order": {"_key": "asc"},
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
            }
        },
    },
)


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
# /es/pending-delay  (작업 대기 및 지연)
#
# 응답 구조 (사용자 합의 형식):
#
#   aggregations:
#     current_state_distribution:
#       buckets:
#         - {key: "WAITING", doc_count: 123}
#         - {key: "RUNNING", doc_count: 456}
#         - ...
#
#   서비스 측에서 settings.es_pending_delay_display_keys() 로
#   [(key, label)] 리스트를 가져와, buckets 를 그 순서대로 정렬/필터링
#   해 차트와 표에 표시한다.  응답에 없는 key 는 doc_count=0 으로 채움.
#
# ⚠️ 아래 body 는 더미 — 사용자가 실 운영용 DSL 로 덮어쓸 것.
#    중요한 것은 ``aggregations.current_state_distribution.buckets[]``
#    구조와 ``key``/``doc_count`` 필드명을 유지하는 것.
# ──────────────────────────────────────────────────────────────
PENDING_AND_DELAY_DIST = EsQueryDef(
    id="pending_and_delay_dist",
    title="작업 대기/지연 상태 분포",
    description=(
        "current_state_distribution 단일 terms 집계 (더미 DSL — "
        "운영 환경에 맞게 덮어쓸 것). 응답 형식: "
        "aggregations.current_state_distribution.buckets[].key/doc_count"
    ),
    index="parsing-index-2-*",
    body={
        # ── ⚠️ 아래 DSL 은 더미. 실제 필드명/range 는 수정 필요 ──
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "meta.tkin_time": {
                                "gte": "now-1d/d",
                                "lte": "now/d",
                                "format": "epoch_millis",
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
            "current_state_distribution": {
                "terms": {
                    "field": "current_state.keyword",
                    "size": 100,
                    "order": {"_count": "desc"},
                }
            }
        },
    },
)

# ──────────────────────────────────────────────────────────────
# /es/history  (종합 처리 이력)
#
# 최근 N일(=ES_HISTORY_DAYS) 동안 (product × maker × 날짜) 매트릭스를
# 만들기 위한 두 쿼리.  각 셀에는 미니 차트가 그려지며, 한 셀에는
# Series A (index-1 단일막대) + Series B (index-2 의 current_state 별
# 누적막대) 가 함께 그려진다.
#
# 사용자가 합의한 응답 구조:
#
# [HISTORY_INDEX1_AGG  — parsing-index-1, current_state 없음]
#
#   aggregations:
#     group_by_date:
#       buckets:
#         - key_as_string: "yyyy-MM-dd"
#           doc_count:      <int>
#           group_by_product:
#             buckets:
#               - key:       <product>
#                 doc_count: <int>
#                 group_by_maker:
#                   buckets:
#                     - key:       <maker>
#                       doc_count: <int>
#
# [HISTORY_INDEX2_AGG  — parsing-index-2, current_state 포함]
#
# ⚠️ index-2 는 index-1 과 달리 ``group_by_date`` 위에 ``last_7_days``
#    래퍼 단일 버킷이 한 단계 더 들어간다.  서비스는 이 경로를 따라
#    내려가도록 구현되어 있다.
#
#   aggregations:
#     last_7_days:                # filter / date_range 등 단일 버킷
#       doc_count: <int>
#       group_by_date:
#         buckets:
#           - key_as_string: "yyyy-MM-dd"
#             doc_count:      <int>
#             group_by_current_state:
#               buckets:
#                 - key:       <state>
#                   doc_count: <int>
#                   group_by_product:
#                     buckets:
#                       - key:       <product>
#                         doc_count: <int>
#                         group_by_maker:
#                           buckets:
#                             - key:       <maker>
#                               doc_count: <int>
#
# ⚠️ 아래 두 body 는 더미 — 사용자가 실 운영용 DSL 로 덮어쓸 것.
#    서비스 코드가 다음 이름들을 그대로 참조하므로 유지해야 함:
#      [index-1] group_by_date / group_by_product / group_by_maker
#      [index-2] last_7_days / group_by_date / group_by_current_state /
#                group_by_product / group_by_maker
#    + buckets 의 ``key_as_string`` / ``key`` / ``doc_count`` 필드명
# ──────────────────────────────────────────────────────────────

HISTORY_INDEX1_AGG = EsQueryDef(
    id="history_index1_agg",
    title="종합 처리 이력 — parsing-index-1",
    description=(
        "parsing-index-1-* · 최근 N일 동안 날짜 × product × maker 매트릭스 "
        "(current_state 없음). 더미 DSL — 운영 환경에 맞게 덮어쓸 것."
    ),
    index="parsing-index-1-*",
    body={
        # ── ⚠️ 아래 DSL 은 더미. 실제 필드명/range/size 는 수정 필요 ──
        "size": 0,
        "query": {
            "range": {
                "@timestamp": {
                    "gte": "now-7d/d",
                    "lte": "now/d",
                }
            }
        },
        "aggs": {
            "group_by_date": {
                "date_histogram": {
                    "field": "@timestamp",
                    "calendar_interval": "day",
                    "format": "yyyy-MM-dd",
                    "min_doc_count": 0,
                    "extended_bounds": {
                        "min": "now-7d/d",
                        "max": "now/d",
                    },
                    "order": {"_key": "asc"},
                },
                "aggs": {
                    "group_by_product": {
                        "terms": {"field": "product.keyword", "size": 100},
                        "aggs": {
                            "group_by_maker": {
                                "terms": {"field": "maker.keyword", "size": 100},
                            }
                        },
                    }
                },
            }
        },
    },
)

HISTORY_INDEX2_AGG = EsQueryDef(
    id="history_index2_agg",
    title="종합 처리 이력 — parsing-index-2",
    description=(
        "parsing-index-2-* · 최근 N일 동안 날짜 × current_state × product × "
        "maker 매트릭스. 더미 DSL — 운영 환경에 맞게 덮어쓸 것."
    ),
    index="parsing-index-2-*",
    body={
        # ── ⚠️ 아래 DSL 은 더미. 실제 필드명/range/size 는 수정 필요 ──
        # 응답 구조:
        #   aggregations.last_7_days.group_by_date.buckets[…]
        # ``last_7_days`` 는 단일 버킷 (filter / date_range 등) 으로
        # group_by_date 를 한 번 더 감싸는 래퍼다.  서비스 코드도 이
        # 경로를 따라 내려간다.
        "size": 0,
        "aggs": {
            "last_7_days": {
                "filter": {
                    "range": {
                        "@timestamp": {
                            "gte": "now-7d/d",
                            "lte": "now/d",
                        }
                    }
                },
                "aggs": {
                    "group_by_date": {
                        "date_histogram": {
                            "field": "@timestamp",
                            "calendar_interval": "day",
                            "format": "yyyy-MM-dd",
                            "min_doc_count": 0,
                            "extended_bounds": {
                                "min": "now-7d/d",
                                "max": "now/d",
                            },
                            "order": {"_key": "asc"},
                        },
                        "aggs": {
                            "group_by_current_state": {
                                "terms": {"field": "current_state.keyword", "size": 100},
                                "aggs": {
                                    "group_by_product": {
                                        "terms": {"field": "product.keyword", "size": 100},
                                        "aggs": {
                                            "group_by_maker": {
                                                "terms": {"field": "maker.keyword", "size": 100},
                                            }
                                        },
                                    }
                                },
                            }
                        },
                    }
                },
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

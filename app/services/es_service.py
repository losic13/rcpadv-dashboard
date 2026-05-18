"""Elasticsearch 서비스.

DSL 응답을 (columns, rows) 형태로 정규화하여 클라이언트에서 DataTables 가
공통 포맷으로 처리할 수 있게 한다.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from app.config import settings
from app.logger import get_logger
from app.queries import es_queries
from app.queries._base import EsQueryDef
from app.repositories import es_client

log = get_logger("service.es")

SOURCE = "es"
SOURCE_LABEL = "Elasticsearch"


def list_queries() -> list[dict[str, Any]]:
    return [
        {"id": q.id, "title": q.title, "description": q.description, "params": []}
        for q in es_queries.QUERIES.values()
    ]


def list_dashboard_queries() -> list[EsQueryDef]:
    return [q for q in es_queries.QUERIES.values() if q.show_in_dashboard]


async def run(query_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if query_id not in es_queries.QUERIES:
        raise KeyError(f"Unknown ES query: {query_id}")
    qdef = es_queries.QUERIES[query_id]

    log.info("[es] 쿼리 실행 시작: %s (index=%s)", query_id, qdef.index)
    start = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(es_client.search, qdef.index, qdef.body),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es] 쿼리 타임아웃: %s (>%ds)", query_id, settings.QUERY_TIMEOUT_SECONDS)
        raise
    except Exception as e:
        log.error("[es] 쿼리 실패: %s — %s", query_id, e)
        raise

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    columns, rows = _normalize(resp)
    log.info("[es] 쿼리 완료: %s (%d행, %dms)", query_id, len(rows), elapsed_ms)

    return {
        "query_id": query_id,
        "title": qdef.title,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "elapsed_ms": elapsed_ms,
    }


# ============================================================
# Overview 전용 — Section A: index-1 vs index-2 날짜별 비교
# ============================================================

async def run_overview_comparison() -> dict[str, Any]:
    """parsing-index-1-* / parsing-index-2-* 날짜별 건수 비교.

    반환:
        {
          "ok": bool,
          "rows": [
              {"date": "2024-01-01", "index1": 1000, "index2": 950, "pct": 95.0},
              ...
          ],
          "elapsed_ms": int,
          "error": str | None,
        }
    """
    qdef1 = es_queries.OVERVIEW_INDEX1_AGG
    qdef2 = es_queries.OVERVIEW_INDEX2_AGG

    log.info("[es/overview] index-1 vs index-2 비교 쿼리 시작")
    start = time.perf_counter()
    try:
        resp1, resp2 = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(es_client.search, qdef1.index, qdef1.body),
                asyncio.to_thread(es_client.search, qdef2.index, qdef2.body),
            ),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es/overview] 비교 쿼리 타임아웃")
        return {"ok": False, "rows": [], "elapsed_ms": 0, "error": "쿼리 타임아웃"}
    except Exception as e:
        log.error("[es/overview] 비교 쿼리 실패: %s", e)
        return {"ok": False, "rows": [], "elapsed_ms": 0, "error": str(e)}

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # date_histogram buckets → dict[date_str -> count]
    def _buckets_to_map(resp: dict) -> dict[str, int]:
        buckets = (
            resp.get("aggregations", {})
                .get("by_date", {})
                .get("buckets", [])
        )
        return {b["key_as_string"]: b["doc_count"] for b in buckets}

    map1 = _buckets_to_map(resp1)
    map2 = _buckets_to_map(resp2)

    # index-1 기준으로 날짜 목록 정렬, index-2 건수 매칭
    all_dates = sorted(set(map1) | set(map2))
    rows = []
    for date in all_dates:
        cnt1 = map1.get(date, 0)
        cnt2 = map2.get(date, 0)
        pct = round(cnt2 / cnt1 * 100, 2) if cnt1 > 0 else None
        rows.append({"date": date, "index1": cnt1, "index2": cnt2, "pct": pct})

    log.info("[es/overview] 비교 완료: %d 날짜, %dms", len(rows), elapsed_ms)
    return {
        "ok": True,
        "rows": rows,
        "elapsed_ms": elapsed_ms,
        "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": None,
    }


# ============================================================
# Overview 전용 — Section B: index-2 tkin_time 최근 2주 카운트
# ============================================================

async def run_overview_tkin() -> dict[str, Any]:
    """parsing-index-2-* 에서 meta.tkin_time 기준 최근 2주 날짜별 카운트.

    반환:
        {
          "ok": bool,
          "rows": [
              {"date": "2024-01-01", "count": 1234},
              ...
          ],
          "elapsed_ms": int,
          "error": str | None,
        }
    """
    qdef = es_queries.OVERVIEW_TKIN_AGG

    log.info("[es/overview] tkin_time 최근 2주 집계 시작")
    start = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(es_client.search, qdef.index, qdef.body),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es/overview] tkin_time 쿼리 타임아웃")
        return {"ok": False, "rows": [], "elapsed_ms": 0, "error": "쿼리 타임아웃"}
    except Exception as e:
        log.error("[es/overview] tkin_time 쿼리 실패: %s", e)
        return {"ok": False, "rows": [], "elapsed_ms": 0, "error": str(e)}

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    buckets = (
        resp.get("aggregations", {})
            .get("by_date", {})
            .get("buckets", [])
    )
    rows = [
        {"date": b["key_as_string"], "count": b["doc_count"]}
        for b in buckets
    ]

    log.info("[es/overview] tkin_time 완료: %d 날짜, %dms", len(rows), elapsed_ms)
    return {
        "ok": True,
        "rows": rows,
        "elapsed_ms": elapsed_ms,
        "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": None,
    }


# ============================================================
# Document 조회 — _id terms 쿼리 (Document 조회 페이지)
# ============================================================
#
# 인덱스 이름 / 한도는 app.config.settings 로 옮겼다.
#   - settings.ES_DOCUMENT_LOOKUP_INDEX   (.env: ES_DOCUMENT_LOOKUP_INDEX)
#   - settings.ES_DOCUMENT_LOOKUP_MAX_IDS (.env: ES_DOCUMENT_LOOKUP_MAX_IDS)
# 운영에서 인덱스/한도를 바꿔야 할 때 코드를 건드리지 않고 .env 만 수정한다.


async def run_document_lookup(ids: list[str]) -> dict[str, Any]:
    """입력된 _id 목록으로 ES_DOCUMENT_LOOKUP_INDEX 에서 doc 조회 (terms 쿼리).

    동작:
        - 중복 _id 는 입력 순서를 유지하면서 제거.
        - ES terms 쿼리로 한 번에 조회 (size = len(ids)).
        - 결과 rows 는 입력 순서대로 재정렬 (ES 응답 순서는 보장되지 않음).
        - 미발견 _id 도 함께 반환해 UI 에서 사용자에게 알려줄 수 있게 함.

    반환:
        {
          "ok": bool,
          "columns": [...],
          "rows": [...],
          "requested": int,         # 중복 제거 후 입력 개수
          "found": int,             # 실제 조회된 doc 수
          "missing_ids": [...],     # 미발견 _id 목록 (전체)
          "missing_count": int,
          "elapsed_ms": int,
          "queried_at": str,
          "index": str,             # 실행에 사용된 인덱스 (settings 값 그대로)
          "error": str | None,
        }
    """
    index = settings.ES_DOCUMENT_LOOKUP_INDEX
    max_ids = settings.ES_DOCUMENT_LOOKUP_MAX_IDS

    # 입력 순서를 유지하면서 중복 제거
    seen: set[str] = set()
    unique_ids: list[str] = []
    for raw in ids:
        s = (raw or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        unique_ids.append(s)

    if not unique_ids:
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "requested": 0,
            "found": 0,
            "missing_ids": [],
            "missing_count": 0,
            "elapsed_ms": 0,
            "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "index": index,
            "error": "조회할 _id 가 없습니다.",
        }

    if len(unique_ids) > max_ids:
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "requested": len(unique_ids),
            "found": 0,
            "missing_ids": [],
            "missing_count": 0,
            "elapsed_ms": 0,
            "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "index": index,
            "error": f"최대 {max_ids} 건까지만 조회 가능합니다 (입력 {len(unique_ids)} 건).",
        }

    body = {
        "size": len(unique_ids),
        "query": {"terms": {"_id": unique_ids}},
    }

    log.info(
        "[es/document] _id terms 조회 시작: index=%s, ids=%d",
        index, len(unique_ids),
    )
    start = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(es_client.search, index, body),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es/document] 쿼리 타임아웃 (>%ds)", settings.QUERY_TIMEOUT_SECONDS)
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "requested": len(unique_ids),
            "found": 0,
            "missing_ids": [],
            "missing_count": 0,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "index": index,
            "error": "쿼리 타임아웃",
        }
    except Exception as e:
        log.error("[es/document] 쿼리 실패: %s", e)
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "requested": len(unique_ids),
            "found": 0,
            "missing_ids": [],
            "missing_count": 0,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "index": index,
            "error": str(e),
        }

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    columns, rows = _normalize(resp)

    # ── 입력 순서대로 재정렬 + 미발견 추적 ──
    found_map: dict[str, dict] = {r.get("_id"): r for r in rows if r.get("_id")}
    ordered_rows: list[dict] = []
    missing_ids: list[str] = []
    for _id in unique_ids:
        if _id in found_map:
            ordered_rows.append(found_map[_id])
        else:
            missing_ids.append(_id)

    log.info(
        "[es/document] 완료: index=%s, 입력=%d, 발견=%d, 미발견=%d, %dms",
        index, len(unique_ids), len(ordered_rows),
        len(missing_ids), elapsed_ms,
    )

    return {
        "ok": True,
        "columns": columns,
        "rows": ordered_rows,
        "requested": len(unique_ids),
        "found": len(ordered_rows),
        "missing_ids": missing_ids,
        "missing_count": len(missing_ids),
        "elapsed_ms": elapsed_ms,
        "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "index": index,
        "error": None,
    }


# ============================================================
# 설비별 처리현황 — product × maker × eqp_id × 날짜 매트릭스
# ============================================================

async def run_eqp_log_count_per_day() -> dict[str, Any]:
    """es_queries.EQP_LOG_COUNT_PER_DAY 실행 후 4-Tier 버킷을 flat 테이블로.

    응답 변환:
        by_product → by_maker → by_eqp_id → by_day 의 중첩 buckets 를
        product/maker/eqp_id 별 한 행 + 날짜 컬럼들로 펼친다.
        min_doc_count=0 이므로 모든 (eqp,날짜) 조합은 최소 0 으로 채워짐.

    반환:
        {
          "ok": bool,
          "columns": ["product", "maker", "eqp_id", "YYYY-MM-DD", ..., "합계"],
          "rows": [
              {"product": "...", "maker": "...", "eqp_id": "...",
               "YYYY-MM-DD": 123, ..., "합계": 1234},
              ...
          ],
          "date_columns": ["YYYY-MM-DD", ...],   # 날짜만 분리해 클라이언트 sticky 처리 등에 활용
          "totals_by_date": {"YYYY-MM-DD": 12345, ...},  # 열 합계 (footer)
          "total": 99999,                         # 전체 합계
          "row_count": int,
          "elapsed_ms": int,
          "queried_at": str,
          "index": str,
          "error": str | None,
        }
    """
    qdef = es_queries.EQP_LOG_COUNT_PER_DAY
    log.info("[es/eqp-status] 쿼리 시작: index=%s", qdef.index)
    start = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(es_client.search, qdef.index, qdef.body),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es/eqp-status] 쿼리 타임아웃 (>%ds)", settings.QUERY_TIMEOUT_SECONDS)
        return {
            "ok": False,
            "columns": [], "rows": [], "date_columns": [],
            "totals_by_date": {}, "total": 0, "row_count": 0,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "index": qdef.index,
            "error": "쿼리 타임아웃",
        }
    except Exception as e:
        log.error("[es/eqp-status] 쿼리 실패: %s", e)
        return {
            "ok": False,
            "columns": [], "rows": [], "date_columns": [],
            "totals_by_date": {}, "total": 0, "row_count": 0,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "index": qdef.index,
            "error": str(e),
        }

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # ── 버킷 walk ──────────────────────────────────────────
    # 모든 (product, maker, eqp_id) 행을 펼치면서, 그 안의 by_day buckets 를
    # 펼친 행 dict 에 채워넣는다. 날짜 컬럼 집합은 처음 등장 순서로 유지.
    rows: list[dict[str, Any]] = []
    all_dates: list[str] = []
    seen_dates: set[str] = set()
    totals_by_date: dict[str, int] = {}
    grand_total = 0

    product_buckets = (
        resp.get("aggregations", {})
            .get("by_product", {})
            .get("buckets", [])
    )
    for pb in product_buckets:
        product_key = pb.get("key")
        maker_buckets = (pb.get("by_maker") or {}).get("buckets", [])
        for mb in maker_buckets:
            maker_key = mb.get("key")
            eqp_buckets = (mb.get("by_eqp_id") or {}).get("buckets", [])
            for eb in eqp_buckets:
                eqp_key = eb.get("key")
                row: dict[str, Any] = {
                    "product": product_key,
                    "maker":   maker_key,
                    "eqp_id":  eqp_key,
                }
                row_sum = 0
                day_buckets = (eb.get("by_day") or {}).get("buckets", [])
                for db in day_buckets:
                    # date_histogram 은 key_as_string 이 yyyy-MM-dd
                    date_key = db.get("key_as_string") or str(db.get("key"))
                    cnt = int(db.get("doc_count") or 0)
                    if date_key not in seen_dates:
                        seen_dates.add(date_key)
                        all_dates.append(date_key)
                    row[date_key] = cnt
                    row_sum += cnt
                    totals_by_date[date_key] = totals_by_date.get(date_key, 0) + cnt
                row["합계"] = row_sum
                grand_total += row_sum
                rows.append(row)

    # 날짜 컬럼은 오름차순(과거 → 최근) 정렬
    date_columns = sorted(all_dates)

    # 모든 행에 모든 날짜 키 채우기 (min_doc_count=0 가정이지만 안전망)
    for r in rows:
        for d in date_columns:
            r.setdefault(d, 0)

    columns: list[str] = ["product", "maker", "eqp_id"] + date_columns + ["합계"]

    log.info(
        "[es/eqp-status] 완료: %d행 × %d일, total=%d, %dms",
        len(rows), len(date_columns), grand_total, elapsed_ms,
    )

    return {
        "ok": True,
        "columns": columns,
        "rows": rows,
        "date_columns": date_columns,
        "totals_by_date": totals_by_date,
        "total": grand_total,
        "row_count": len(rows),
        "elapsed_ms": elapsed_ms,
        "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "index": qdef.index,
        "error": None,
    }


# ============================================================
# /es/pending-delay  (작업 대기 및 지연)
# ============================================================

async def run_pending_and_delay_dist() -> dict[str, Any]:
    """es_queries.PENDING_AND_DELAY_DIST 실행 후 'key 선택+정렬' 적용.

    settings.es_pending_delay_display_keys() 가 반환하는 [(key, label), ...]
    리스트를 기준으로:
        1) 응답의 buckets 를 key → doc_count 맵으로 만든다.
        2) display_keys 순서대로 행을 만들고, 응답에 없는 key 는 0.
        3) display_keys 가 비어 있으면 응답 전체를 응답 순서 그대로 노출
           (label = key).

    반환:
        {
          "ok": bool,
          "rows": [
              {"key": "WAITING", "label": "대기",   "doc_count": 123, "pct": 12.3},
              ...
          ],
          "total":      int,           # 표시되는 키들의 합계 (전체가 아님)
          "raw_total":  int,           # 응답에 있던 buckets 의 합계 (참고용)
          "shown_count": int,          # rows 길이
          "elapsed_ms": int,
          "queried_at": str,
          "index":      str,
          "agg_name":   "current_state_distribution",
          "error":      str | None,
        }
    """
    qdef = es_queries.PENDING_AND_DELAY_DIST
    log.info("[es/pending-delay] 쿼리 시작: index=%s", qdef.index)
    start = time.perf_counter()

    def _empty(err: str | None) -> dict[str, Any]:
        return {
            "ok": err is None,
            "rows": [],
            "total": 0,
            "raw_total": 0,
            "shown_count": 0,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "index": qdef.index,
            "agg_name": "current_state_distribution",
            "error": err,
        }

    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(es_client.search, qdef.index, qdef.body),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es/pending-delay] 쿼리 타임아웃 (>%ds)", settings.QUERY_TIMEOUT_SECONDS)
        return _empty("쿼리 타임아웃")
    except Exception as e:
        log.error("[es/pending-delay] 쿼리 실패: %s", e)
        return _empty(str(e))

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # 응답 buckets → {key: doc_count} 맵
    buckets = (
        resp.get("aggregations", {})
            .get("current_state_distribution", {})
            .get("buckets", [])
    ) or []
    counts: dict[str, int] = {}
    response_order: list[str] = []
    raw_total = 0
    for b in buckets:
        k = b.get("key")
        if k is None:
            continue
        c = int(b.get("doc_count") or 0)
        # 동일 key 가 중복 등장하는 경우 합산 (그래야 안전)
        if k in counts:
            counts[k] += c
        else:
            counts[k] = c
            response_order.append(str(k))
        raw_total += c

    # 표시 키 정의 로드.  비어 있으면 응답 전체를 응답 순서대로 노출.
    display_pairs = settings.es_pending_delay_display_keys()
    if not display_pairs:
        display_pairs = [(k, k) for k in response_order]

    # 표시 키 순서대로 행 구성 — 응답에 없으면 0.
    rows: list[dict[str, Any]] = []
    shown_total = 0
    for key, label in display_pairs:
        dc = int(counts.get(key, 0))
        rows.append({"key": key, "label": label, "doc_count": dc})
        shown_total += dc

    # 비율(pct) 계산 — 표시된 합계 기준 (100% = 표시된 키 합계)
    for r in rows:
        r["pct"] = (r["doc_count"] / shown_total * 100.0) if shown_total > 0 else 0.0

    log.info(
        "[es/pending-delay] 완료: shown=%d/%d keys, total=%d (raw_total=%d), %dms",
        len(rows), len(buckets), shown_total, raw_total, elapsed_ms,
    )

    return {
        "ok": True,
        "rows": rows,
        "total": shown_total,
        "raw_total": raw_total,
        "shown_count": len(rows),
        "elapsed_ms": elapsed_ms,
        "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "index": qdef.index,
        "agg_name": "current_state_distribution",
        "error": None,
    }


# ============================================================
# /es/history  (종합 처리 이력)
# ============================================================

def _history_date_list(days: int) -> list[str]:
    """오늘을 포함한 최근 ``days`` 일을 ``yyyy-MM-dd`` 문자열 오름차순으로 반환."""
    from datetime import date, timedelta

    today = date.today()
    return [
        (today - timedelta(days=days - 1 - i)).isoformat()
        for i in range(days)
    ]


def _history_parse_index1(resp: dict[str, Any]) -> dict[str, int]:
    """parsing-index-1 응답을 ``{date: count}`` 로 평탄화.

    응답 구조 가정 (index-1, index-2 동일하게 ``last_7_days`` 래퍼 포함):

        aggregations.last_7_days.group_by_date.buckets[…]
    """
    out: dict[str, int] = {}
    date_buckets = (
        resp.get("aggregations", {})
            .get("last_7_days", {})
            .get("group_by_date", {})
            .get("buckets", [])
    ) or []
    for db in date_buckets:
        d = str(db.get("key_as_string") or "")
        if not d:
            continue
        out[d] = int(db.get("doc_count") or 0)
    return out


def _history_parse_index2(resp: dict[str, Any]) -> dict[str, dict[str, int]]:
    """parsing-index-2 응답을 ``{date: {state: count}}`` 로 평탄화.

    응답 구조 가정:

        aggregations.last_7_days.group_by_date.buckets[].group_by_current_state.buckets[]
    """
    out: dict[str, dict[str, int]] = {}
    date_buckets = (
        resp.get("aggregations", {})
            .get("last_7_days", {})
            .get("group_by_date", {})
            .get("buckets", [])
    ) or []
    for db in date_buckets:
        d = str(db.get("key_as_string") or "")
        if not d:
            continue
        by_state: dict[str, int] = out.setdefault(d, {})
        for sb in (db.get("group_by_current_state", {}).get("buckets", []) or []):
            state = str(sb.get("key") or "")
            if not state:
                continue
            c = int(sb.get("doc_count") or 0)
            by_state[state] = by_state.get(state, 0) + c
    return out


async def run_history_overview() -> dict[str, Any]:
    """parsing-index-1 + parsing-index-2 를 병렬 조회해 종합 처리 이력 데이터 생성.

    응답 구조 (날짜별 단일 큰 차트용, product/maker 차원 없음):

        {
          "ok": bool,
          "dates":     ["2026-05-08", ...],          # 오름차순 N일
          "states":    [                              # ES_HISTORY_STATE_KEYS 순서
            {"key": "WAITING", "label": "대기", "attr": "stage"},
            ...
          ],
          "attr_order": ["stage", "normal", "complete", "check", ""],
                        # 보조 테이블/표에서 attr 그룹을 노출할 순서.
                        # "" 는 미지정(강조 없음) 그룹.
          "index1_by_date": {"2026-05-08": 123, ...},
                                                       # parsing-index-1 일자별 카운트
          "index2_by_date": {                          # parsing-index-2 일자×state 카운트
            "2026-05-08": {"WAITING": 10, "RUNNING": 20, ...}, ...
          },
          "index2_by_date_attr": {                     # 일자별 attr 그룹 합계
            "2026-05-08": {"stage": 30, "normal": 0, "complete": 0,
                            "check": 0, "": 0}, ...
          },
          "totals": {
            "index1": int,
            "index2": int,                             # filtered state 합
            "by_state": {"WAITING": 100, ...},
            "by_attr":  {"stage": 100, "normal": 50, ...,
                          "": 0},                      # attr 그룹 합계 (""=미지정)
          },
          "index1":     str,    # index 이름
          "index2":     str,
          "days":       int,
          "elapsed_ms": int,
          "queried_at": str,
          "error":      str | None,
          "errors":     {"index1": str|None, "index2": str|None},
        }
    """
    q1 = es_queries.HISTORY_INDEX1_AGG
    q2 = es_queries.HISTORY_INDEX2_AGG
    days = max(1, int(settings.ES_HISTORY_DAYS or 7))
    dates = _history_date_list(days)
    # [(key, label, attr)] — attr ∈ {"stage","normal","complete","check",""}
    state_triples = settings.es_history_state_keys()

    # attr 노출 순서 — 미지정("")은 항상 마지막
    ATTR_ORDER = ["stage", "normal", "complete", "check", ""]

    log.info(
        "[es/history] 쿼리 시작: days=%d index1=%s index2=%s states=%d",
        days, q1.index, q2.index, len(state_triples),
    )
    start = time.perf_counter()

    async def _one(qdef: EsQueryDef, tag: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(es_client.search, qdef.index, qdef.body),
                timeout=settings.QUERY_TIMEOUT_SECONDS,
            )
            return resp, None
        except asyncio.TimeoutError:
            log.error("[es/history] %s 쿼리 타임아웃 (>%ds)", tag, settings.QUERY_TIMEOUT_SECONDS)
            return None, "쿼리 타임아웃"
        except Exception as e:
            log.error("[es/history] %s 쿼리 실패: %s", tag, e)
            return None, str(e)

    (resp1, err1), (resp2, err2) = await asyncio.gather(
        _one(q1, "index1"),
        _one(q2, "index2"),
    )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    queried_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _states_payload(triples: list[tuple[str, str, str]]) -> list[dict[str, str]]:
        return [{"key": k, "label": lab, "attr": at} for k, lab, at in triples]

    base_payload: dict[str, Any] = {
        "ok": (err1 is None and err2 is None),
        "dates": dates,
        "states": _states_payload(state_triples),
        "attr_order": ATTR_ORDER,
        "index1_by_date": {d: 0 for d in dates},
        "index2_by_date": {d: {} for d in dates},
        "index2_by_date_attr": {d: {a: 0 for a in ATTR_ORDER} for d in dates},
        "totals": {
            "index1": 0,
            "index2": 0,
            "by_state": {k: 0 for k, _, _ in state_triples},
            "by_attr":  {a: 0 for a in ATTR_ORDER},
        },
        "index1": q1.index,
        "index2": q2.index,
        "days": days,
        "elapsed_ms": elapsed_ms,
        "queried_at": queried_at,
        "error": err1 or err2,
        "errors": {"index1": err1, "index2": err2},
    }

    # 둘 다 실패하면 빈 결과로 종료
    if resp1 is None and resp2 is None:
        return base_payload

    # 응답 평탄화
    by_date_idx1 = _history_parse_index1(resp1) if resp1 else {}
    by_date_idx2 = _history_parse_index2(resp2) if resp2 else {}

    # state_triples 가 비어 있으면 → 응답에 등장한 state 를 attr=""(미지정)로 사용
    if not state_triples:
        seen_states: list[str] = []
        seen_set: set[str] = set()
        for by_state in by_date_idx2.values():
            for st in by_state.keys():
                if st not in seen_set:
                    seen_set.add(st)
                    seen_states.append(st)
        state_triples = [(s, s, "") for s in seen_states]
        base_payload["states"] = _states_payload(state_triples)
        base_payload["totals"]["by_state"] = {k: 0 for k, _, _ in state_triples}

    # key → attr 매핑
    attr_of: dict[str, str] = {k: at for k, _, at in state_triples}

    # 날짜별 카운트 채움 — dates 순서대로 모두 채우되, 응답에 없는 날짜는 0
    index1_by_date: dict[str, int] = {}
    index2_by_date: dict[str, dict[str, int]] = {}
    index2_by_date_attr: dict[str, dict[str, int]] = {}
    total_idx1 = 0
    total_idx2 = 0
    total_by_state: dict[str, int] = {k: 0 for k, _, _ in state_triples}
    total_by_attr: dict[str, int] = {a: 0 for a in ATTR_ORDER}

    for d in dates:
        v1 = int(by_date_idx1.get(d, 0))
        index1_by_date[d] = v1
        total_idx1 += v1

        states_map_raw = by_date_idx2.get(d, {}) or {}
        # state_triples 순서대로 값을 채워 dict 직렬화 시 순서 안정성 확보
        states_map: dict[str, int] = {}
        attr_map: dict[str, int] = {a: 0 for a in ATTR_ORDER}
        for k, _, at in state_triples:
            c = int(states_map_raw.get(k, 0))
            states_map[k] = c
            total_by_state[k] += c
            total_idx2 += c
            # attr 그룹 누적 (허용값 외이면 ""(미지정) 으로 묶임 — 파서에서 이미 정규화됨)
            bucket = at if at in attr_map else ""
            attr_map[bucket] += c
            total_by_attr[bucket] += c
        index2_by_date[d] = states_map
        index2_by_date_attr[d] = attr_map

    base_payload["index1_by_date"] = index1_by_date
    base_payload["index2_by_date"] = index2_by_date
    base_payload["index2_by_date_attr"] = index2_by_date_attr
    base_payload["totals"] = {
        "index1": total_idx1,
        "index2": total_idx2,
        "by_state": total_by_state,
        "by_attr": total_by_attr,
    }

    log.info(
        "[es/history] 완료: %d days × %d states, idx1=%d idx2=%d, %dms (err1=%s, err2=%s)",
        len(dates), len(state_triples), total_idx1, total_idx2,
        elapsed_ms, err1, err2,
    )

    return base_payload


# ============================================================
# Document State 변경 페이지 (/es/document-state)
# ============================================================
#
# 두 가지 작업을 제공:
#   1) run_document_state_lookup(_id)
#        ES_DOCUMENT_LOOKUP_INDEX 에서 단일 _id 의 doc 을 GET 한 뒤
#        UI 가 필요한 핵심 필드들을 정리해 반환.
#        업데이트 시 사용할 구체 인덱스(`_index`) 도 같이 반환한다.
#   2) run_document_state_update(_id, new_state, concrete_index)
#        다음 3 가지를 한 번에 partial update:
#          · current_state       ← new_state
#          · pipeline_state      ← 기존 dict 을 그대로 두고 [new_state] 키만
#                                  {"updated_at": now, "comment": ...} 로 덮어쓰기
#          · updated_at          ← now
#        그 후 다시 GET 해서 갱신된 doc 을 반환.

# state 변경 시 pipeline_state 의 entry 에 같이 남길 comment.
# 운영 추적용 — 어떤 채널로 변경된 건지 식별 가능하게 한다.
DOCUMENT_STATE_COMMENT = "document-state-change(web)"


def _document_state_now_str() -> str:
    """`pipeline_state[*].updated_at` 및 doc.updated_at 에 사용할 시각 문자열.

    포맷: ``YYYY-MM-DD HH:MM:SS`` (로컬 시간) — 기존 페이지들의 컨벤션과 일치.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def run_document_state_lookup(doc_id: str) -> dict[str, Any]:
    """_id 1개 조회 — Document State 변경 페이지 전용.

    반환 스키마:
        {
          "ok": bool,
          "_id": str,
          "_index": str,        # 실제 구체 인덱스 — 후속 update 호출에 그대로 사용
          "current_state":  Any | None,
          "pipeline_state": Any | None,
          "edip_kafka_msg": Any | None,
          "meta":           Any | None,
          "created_at":     Any | None,
          "updated_at":     Any | None,
          "source":         dict,    # 그 외 모든 _source (위 6개 필드 제외)
          "allowed_states": [str, ...],   # 화이트리스트 (.env)
          "elapsed_ms": int,
          "queried_at": str,
          "error":      str | None,
        }

    오류 매핑:
        · 빈 _id        → ok=False, error="조회할 _id 가 없습니다."
        · NotFound      → ok=False, error="not_found"
        · 그 외 예외/타임아웃은 ok=False + 에러 메시지
    """
    index_pattern = settings.ES_DOCUMENT_LOOKUP_INDEX
    allowed = settings.es_document_state_allowed()
    _id = (doc_id or "").strip()

    base_meta: dict[str, Any] = {
        "ok": False,
        "_id": _id,
        "_index": None,
        "current_state": None,
        "pipeline_state": None,
        "edip_kafka_msg": None,
        "meta": None,
        "created_at": None,
        "updated_at": None,
        "source": {},
        "allowed_states": allowed,
        "elapsed_ms": 0,
        "queried_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": None,
    }

    if not _id:
        return {**base_meta, "error": "조회할 _id 가 없습니다."}

    # ── 조회 전략: `search` 의 term 쿼리로 _id 1건을 가져온다 ──────────
    #   왜 client.get() 이 아니라 search() 인가:
    #     · ES 의 `GET /<index>/_doc/<id>` API 는 인덱스 와일드카드를 지원하지 않는다
    #       (illegal_argument_exception:
    #          "the action indices:data/read/get does not support wildcards;
    #           the provided index expressions [my-index-*] is not allowed").
    #     · ES_DOCUMENT_LOOKUP_INDEX 는 일반적으로 와일드카드 패턴(예: "parsing-index-2-*")
    #       이므로 동일한 .env 설정으로 동작하려면 search 를 써야 한다.
    #     · `search` 의 term 쿼리는 와일드카드 인덱스 패턴을 자연스럽게 지원하며,
    #       응답 hit 의 `_index` 로 후속 update 에 쓸 구체 인덱스 이름을 얻을 수 있다.
    body = {
        "size": 1,
        "query": {"term": {"_id": _id}},
    }
    log.info("[es/document-state] 조회 시작: index=%s, _id=%s", index_pattern, _id)
    start = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(es_client.search, index_pattern, body),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("[es/document-state] 쿼리 타임아웃 (>%ds)", settings.QUERY_TIMEOUT_SECONDS)
        return {
            **base_meta,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": "쿼리 타임아웃",
        }
    except Exception as e:
        log.error("[es/document-state] 조회 실패: %s", e)
        return {
            **base_meta,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": str(e),
        }

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    hits = (resp.get("hits") or {}).get("hits") or []
    if not hits:
        # 인덱스는 존재하지만 해당 _id 가 없는 정상 케이스 → not_found.
        log.info("[es/document-state] not_found: _id=%s", _id)
        return {
            **base_meta,
            "elapsed_ms": elapsed_ms,
            "error": "not_found",
        }
    hit = hits[0]
    concrete_index = hit.get("_index")
    src = hit.get("_source") or {}

    # 핵심/부가 필드를 명시적으로 꺼내고, 나머지는 source 에 그대로 담는다.
    KEY_FIELDS = ("current_state", "pipeline_state",
                   "edip_kafka_msg", "meta", "created_at", "updated_at")
    extras = {k: v for k, v in src.items() if k not in KEY_FIELDS}

    log.info(
        "[es/document-state] 완료: index=%s, _id=%s, current_state=%r, %dms",
        concrete_index, _id, src.get("current_state"), elapsed_ms,
    )
    return {
        "ok": True,
        "_id": _id,
        "_index": concrete_index,
        "current_state":  src.get("current_state"),
        "pipeline_state": src.get("pipeline_state"),
        "edip_kafka_msg": src.get("edip_kafka_msg"),
        "meta":           src.get("meta"),
        "created_at":     src.get("created_at"),
        "updated_at":     src.get("updated_at"),
        "source":         extras,
        "allowed_states": allowed,
        "elapsed_ms":     elapsed_ms,
        "queried_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error":          None,
    }


async def run_document_state_update(
    doc_id: str,
    new_state: str,
    concrete_index: str,
) -> dict[str, Any]:
    """current_state 변경 + pipeline_state 누적 + updated_at 갱신.

    인자:
        doc_id          : 대상 _id
        new_state       : 새 current_state 값. 화이트리스트에 있어야 함.
        concrete_index  : 와일드카드가 아닌 **구체 인덱스 이름**. 호출하는 쪽이
                          이전 조회 응답의 ``_index`` 를 그대로 넘겨주는 패턴.

    반환:
        {
          "ok": bool,
          "_id": str,
          "_index": str,
          "prev_state":  Any | None,    # 변경 전 current_state
          "new_state":   str,
          "updated":     dict,          # 변경 후 다시 GET 한 doc (lookup 과 같은 스키마)
          "elapsed_ms":  int,
          "updated_at_used": str,       # 이번에 기록한 시각
          "error":       str | None,
        }
    """
    allowed = settings.es_document_state_allowed()
    _id = (doc_id or "").strip()
    state = (new_state or "").strip()
    index = (concrete_index or "").strip()

    base: dict[str, Any] = {
        "ok": False,
        "_id": _id,
        "_index": index or None,
        "prev_state": None,
        "new_state": state,
        "updated": None,
        "elapsed_ms": 0,
        "updated_at_used": None,
        "error": None,
    }

    # 1) 입력 검증
    if not _id:
        return {**base, "error": "변경할 _id 가 없습니다."}
    if not state:
        return {**base, "error": "new_state 가 비어 있습니다."}
    if not index:
        return {**base, "error": "concrete_index 가 비어 있습니다."}
    if allowed and state not in allowed:
        return {
            **base,
            "error": f"허용되지 않은 state 입니다: {state!r} (허용: {', '.join(allowed) or '없음'})",
        }
    # 와일드카드 보호 — update API 는 와일드카드 인덱스를 받지 않음.
    if "*" in index or "," in index:
        return {**base, "error": f"구체 인덱스 이름이 필요합니다 (받은 값: {index!r})."}

    start = time.perf_counter()

    # 2) 현재 doc 조회 (prev_state / pipeline_state 머지를 위해 필요)
    log.info("[es/document-state] update GET: index=%s, _id=%s, new=%s", index, _id, state)
    try:
        cur = await asyncio.wait_for(
            asyncio.to_thread(es_client.get_doc, index, _id),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {**base, "elapsed_ms": int((time.perf_counter() - start) * 1000), "error": "쿼리 타임아웃"}
    except Exception as e:
        msg = str(e)
        if "NotFoundError" in type(e).__name__ or "404" in msg or "not_found" in msg.lower():
            return {
                **base,
                "elapsed_ms": int((time.perf_counter() - start) * 1000),
                "error": "not_found",
            }
        log.error("[es/document-state] update 전 조회 실패: %s", e)
        return {**base, "elapsed_ms": int((time.perf_counter() - start) * 1000), "error": msg}

    src = cur.get("_source") or {}
    prev_state = src.get("current_state")

    # 3) pipeline_state 머지 — 기존 dict 보존, state 키만 덮어쓰기
    existing_pipeline = src.get("pipeline_state")
    if isinstance(existing_pipeline, dict):
        merged_pipeline = dict(existing_pipeline)
    else:
        # dict 가 아니거나 null 이면 새로 만든다 (기존 값은 무시되며 새 dict 로 치환).
        merged_pipeline = {}
    now_str = _document_state_now_str()
    merged_pipeline[state] = {
        "updated_at": now_str,
        "comment":    DOCUMENT_STATE_COMMENT,
    }

    partial_doc = {
        "current_state":  state,
        "pipeline_state": merged_pipeline,
        "updated_at":     now_str,
    }

    # 4) update 실행
    log.info(
        "[es/document-state] update DO: index=%s, _id=%s, %r → %r",
        index, _id, prev_state, state,
    )
    try:
        await asyncio.wait_for(
            asyncio.to_thread(es_client.update_doc, index, _id, partial_doc),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {
            **base,
            "prev_state": prev_state,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": "update 타임아웃",
        }
    except Exception as e:
        log.error("[es/document-state] update 실패: %s", e)
        return {
            **base,
            "prev_state": prev_state,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": str(e),
        }

    # 5) 변경 후 다시 GET 해서 화면에 보여줄 최신 doc 을 만든다.
    #    내부적으로 lookup 헬퍼를 재사용 — 동일한 응답 스키마 보장.
    fresh = await run_document_state_lookup(_id)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return {
        "ok": True,
        "_id": _id,
        "_index": index,
        "prev_state": prev_state,
        "new_state": state,
        "updated": fresh,
        "elapsed_ms": elapsed_ms,
        "updated_at_used": now_str,
        "error": None,
    }


# ============================================================
# 공통 내부 유틸
# ============================================================

def _normalize(resp: dict[str, Any]) -> tuple[list[str], list[dict]]:
    """ES 응답을 테이블 포맷으로 변환.

    1) hits 가 있으면 _source 의 키들을 컬럼으로
    2) hits 가 비어 있고 aggregations 가 있으면 첫 번째 terms agg 의 buckets 를 표로
    """
    hits = resp.get("hits", {}).get("hits", [])
    if hits:
        rows = []
        all_keys: list[str] = []
        seen = set()
        for h in hits:
            src = h.get("_source") or {}
            row = {"_id": h.get("_id")}
            for k, v in src.items():
                row[k] = _stringify(v)
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)
            rows.append(row)
        columns = ["_id"] + all_keys
        for r in rows:
            for c in columns:
                r.setdefault(c, None)
        return columns, rows

    aggs = resp.get("aggregations") or {}
    if aggs:
        first_name = next(iter(aggs.keys()))
        agg = aggs[first_name]
        buckets = agg.get("buckets")
        if isinstance(buckets, list):
            rows = [{"key": b.get("key"), "doc_count": b.get("doc_count")} for b in buckets]
            return ["key", "doc_count"], rows

    return [], []


def _stringify(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, dict)):
        return v
    try:
        return str(v)
    except Exception:
        return None

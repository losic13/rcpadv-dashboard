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

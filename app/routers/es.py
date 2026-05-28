"""Elasticsearch 페이지/API."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates
from app.services import es_service

router = APIRouter(prefix="/es")
log = get_logger("router.es")


# ── Pydantic 모델: Document 조회 (POST body) ────────────────────────────
class DocumentLookupBody(BaseModel):
    """`POST /es/document/lookup` 요청 본문.

    - ids: 사용자가 입력한 _id 목록. 중복 제거 / 빈 값 제거는 서비스 레이어에서 수행.
    """
    ids: list[str] = Field(default_factory=list, description="조회할 _id 목록")


# ── Pydantic 모델: Document State 변경 페이지 (POST body 2종) ───────────
class DocumentStateLookupBody(BaseModel):
    """`POST /es/document-state/lookup` 요청 본문.

    - _id: 단일 _id (양옆 공백은 서버에서 strip).
    """
    id: str = Field(..., description="조회할 _id 단일 값")


class DocumentStateUpdateBody(BaseModel):
    """`POST /es/document-state/update` 요청 본문.

    - id            : 변경 대상 _id
    - new_state     : 새 current_state 값 (서버 화이트리스트 검증)
    - concrete_index: 직전 lookup 응답의 `_index` (와일드카드 불가)
    """
    id: str = Field(..., description="변경 대상 _id")
    new_state: str = Field(..., description="새 current_state — 화이트리스트만 허용")
    concrete_index: str = Field(..., description="구체 인덱스 이름 (와일드카드 불가)")


class BulkCurrentStateBody(BaseModel):
    """`POST /es/bulk-current-state` 요청 본문.

    - ids: 일괄 조회할 _id 목록 (서비스 레이어에서 중복/공백 제거 + 한도 검사).
    AMAT Abnormal Step List 의 ES-STATE 컬럼 채우기 전용으로 사용.
    """
    ids: list[str] = Field(default_factory=list, description="조회할 _id 목록")


# ── 기존: /es (소스 탭 페이지) ──────────────────────────────────────────
@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "source_page.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es",
            "page_title": es_service.SOURCE_LABEL,
            "source": es_service.SOURCE,
            "queries": es_service.list_queries(),
        },
    )


@router.get("/query/{query_id}")
async def run_query(query_id: str, request: Request):
    params = dict(request.query_params)
    try:
        result = await es_service.run(query_id, params)
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_id}")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"쿼리 실패: {e}")


# ── 신규: /es/document (Document 조회 — _id terms 쿼리) ──────────────────
@router.get("/document")
def document_page(request: Request, ids: str | None = None):
    """Document 조회 페이지 — _id 목록으로 ES_DOCUMENT_LOOKUP_INDEX doc 조회.

    인덱스 이름 / 한도는 settings (.env) 에서 가져온다.

    URL 파라미터:
        ids : 쉼표/공백/세미콜론으로 구분된 _id 목록 (선택).
              값이 있으면 페이지 로드 직후 textarea 에 채우고 자동 조회한다.
              · 다른 페이지(예: /amat 의 ES_ID 컬럼 링크)에서 점프할 때 사용.
              · 클라이언트의 파싱 규칙(/[\\s,;]+/) 과 호환되도록 그대로 전달.
    """
    return templates.TemplateResponse(
        request,
        "es_document.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_document",
            "page_title": "Document 조회",
            "lookup_index": settings.ES_DOCUMENT_LOOKUP_INDEX,
            "lookup_max_ids": settings.ES_DOCUMENT_LOOKUP_MAX_IDS,
            # 다른 페이지에서 ?ids= 로 점프해 온 경우, 템플릿이 textarea 초기값 + 자동 조회 트리거에 사용.
            "initial_ids": (ids or "").strip(),
        },
    )


@router.post("/document/lookup")
async def document_lookup(body: DocumentLookupBody):
    """_id terms 쿼리 실행. 빈 입력 / 한도 초과는 422 로 반환."""
    if not body.ids:
        raise HTTPException(status_code=422, detail="조회할 _id 가 비어 있습니다.")

    result = await es_service.run_document_lookup(body.ids)

    # 서비스에서 한도 초과 / 빈 입력 정규화 후 ok=False 로 떨어지면 422 매핑.
    if not result["ok"]:
        err = result.get("error") or "조회 실패"
        # 한도 초과 / 빈 입력은 client error
        if "최대" in err or "비어" in err:
            raise HTTPException(status_code=422, detail=err)
        # 타임아웃은 504
        if "타임아웃" in err:
            raise HTTPException(status_code=504, detail=err)
        # 그 외는 500
        raise HTTPException(status_code=500, detail=err)

    return JSONResponse(result)


# ── 신규: /es/document-state (Document State 변경) ──────────────────────
@router.get("/document-state")
def document_state_page(request: Request, id: str | None = None):
    """Document State 변경 페이지 — _id 1개 조회 + current_state 변경.

    설정:
        · ES_DOCUMENT_LOOKUP_INDEX     : 조회 인덱스 패턴(와일드카드 가능)
        · ES_DOCUMENT_STATE_ALLOWED    : 변경 가능한 state 화이트리스트
                                          (콤보박스 옵션, 콤마 구분)

    파라미터:
        · id : 외부 페이지(예: AMAT Abnormal Step List 의 ES_ID 컬럼) 에서
               점프해 올 때 사용. 비어 있지 않으면 템플릿이 input 을 자동
               으로 채우고 페이지 로드시 즉시 조회를 트리거한다.
    """
    return templates.TemplateResponse(
        request,
        "es_document_state.html",
        {
            "nav_items":  NAV_ITEMS,
            "active_nav": "es_document_state",
            "page_title": "Document State 변경",
            "lookup_index":   settings.ES_DOCUMENT_LOOKUP_INDEX,
            "allowed_states": settings.es_document_state_allowed(),
            # 외부 진입(?id=...) — 비어 있으면 빈 문자열.
            "initial_id":     (id or "").strip(),
        },
    )


@router.post("/document-state/lookup")
async def document_state_lookup(body: DocumentStateLookupBody):
    """_id 1개로 doc 을 조회 — UI 필요한 필드만 정리해 반환."""
    _id = (body.id or "").strip()
    if not _id:
        raise HTTPException(status_code=422, detail="조회할 _id 가 비어 있습니다.")

    result = await es_service.run_document_state_lookup(_id)

    if not result["ok"]:
        err = result.get("error") or "조회 실패"
        if err == "not_found":
            # 사용자가 검색 결과 없음을 자연스럽게 보도록 200 으로 ok=false 그대로 반환.
            #  - 4xx 로 던지면 fetch.ok=false 가 되어 프론트에서 에러 배너로 처리됨.
            #  - 여기서는 "조회 결과 없음" 메시지를 그대로 화면에 보여주기 위해 200 유지.
            return JSONResponse(result, status_code=200)
        if "타임아웃" in err:
            raise HTTPException(status_code=504, detail=err)
        if "비어" in err:
            raise HTTPException(status_code=422, detail=err)
        raise HTTPException(status_code=500, detail=err)

    return JSONResponse(result)


@router.post("/document-state/update")
async def document_state_update(body: DocumentStateUpdateBody):
    """current_state 변경 + pipeline_state[new_state] 기록 + updated_at 갱신.

    동작:
        1) concrete_index 의 _id 를 GET (prev_state 확인 + 화이트리스트 검증)
        2) 새 current_state / 머지된 pipeline_state / 새 updated_at 으로
           ES partial update
        3) 변경 후 doc 을 다시 GET 해서 응답에 포함 (UI 자동 갱신용)

    에러 코드:
        422 — 빈 _id / 빈 new_state / 빈 concrete_index / 화이트리스트 외 state
        422 — concrete_index 가 와일드카드/콤마 포함
        404 — doc not_found
        504 — 타임아웃
        500 — 그 외
    """
    result = await es_service.run_document_state_update(
        doc_id=body.id,
        new_state=body.new_state,
        concrete_index=body.concrete_index,
    )

    if not result["ok"]:
        err = result.get("error") or "변경 실패"
        if err == "not_found":
            raise HTTPException(status_code=404, detail="대상 문서를 찾을 수 없습니다.")
        if "타임아웃" in err:
            raise HTTPException(status_code=504, detail=err)
        # 입력 검증 실패 / 와일드카드 / 화이트리스트 외 등은 모두 클라이언트 잘못
        if (
            "비어" in err
            or "구체 인덱스" in err
            or "허용되지 않은" in err
        ):
            raise HTTPException(status_code=422, detail=err)
        raise HTTPException(status_code=500, detail=err)

    return JSONResponse(result)


# ── 신규: /es/bulk-current-state (AMAT ES-STATE 컬럼 채우기 전용) ────────
@router.post("/bulk-current-state")
async def bulk_current_state(body: BulkCurrentStateBody):
    """여러 _id 의 ``current_state`` 값을 한 번에 묶어서 반환.

    AMAT Abnormal Step List 의 ES-STATE 컬럼이 한 페이지(또는 전체) 행의
    es_id 들을 모아 호출하는 가벼운 lookup. 빈 입력은 200 + 빈 맵으로,
    한도 초과는 422 로, 타임아웃은 504 로 매핑한다.
    """
    result = await es_service.run_bulk_current_state(body.ids)
    if not result["ok"]:
        err = result.get("error") or "조회 실패"
        if "최대" in err:
            raise HTTPException(status_code=422, detail=err)
        if "타임아웃" in err:
            raise HTTPException(status_code=504, detail=err)
        raise HTTPException(status_code=500, detail=err)
    return JSONResponse(result)


# ── 신규: /es/eqp-status (설비별 처리현황) ───────────────────────────────
@router.get("/eqp-status")
def eqp_status_page(request: Request):
    """설비별 처리현황 페이지 — product × maker × eqp_id × 날짜 매트릭스."""
    return templates.TemplateResponse(
        request,
        "es_eqp_status.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_eqp_status",
            "page_title": "설비별 처리현황",
        },
    )


@router.get("/eqp-status/data")
async def eqp_status_data(request: Request):
    """설비별 처리현황 데이터 API."""
    result = await es_service.run_eqp_log_count_per_day()
    status = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status)


# ── 신규: /es/pending-delay (작업 대기 및 지연) ──────────────────────────
@router.get("/pending-delay")
def pending_delay_page(request: Request):
    """작업 대기 및 지연 페이지 — current_state_distribution 막대 차트 + 표.

    표시 대상 키 (key, label) 은 .env 의
    ``ES_PENDING_DELAY_DISPLAY_KEYS`` 로 빌드 시점에 결정.
    """
    from app.config import settings
    display_pairs = settings.es_pending_delay_display_keys()
    return templates.TemplateResponse(
        request,
        "es_pending_delay.html",
        {
            "nav_items":  NAV_ITEMS,
            "active_nav": "es_pending_delay",
            "page_title": "작업 대기 및 지연",
            # 표시 키 정의 — 차트 초기 X 축 라벨/순서 표시용
            "display_keys": [{"key": k, "label": l} for k, l in display_pairs],
        },
    )


@router.get("/pending-delay/data")
async def pending_delay_data(request: Request):
    """작업 대기 및 지연 데이터 API (JSON)."""
    result = await es_service.run_pending_and_delay_dist()
    status = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status)


# ── 신규: /es/history (종합 처리 이력) ────────────────────────────────────
@router.get("/history")
def history_page(request: Request):
    """종합 처리 이력 페이지 — 최근 N일 일자별 처리량.

    하나의 큰 grouped-stacked 막대 차트로 표시한다 (날짜 = X축):
        Series A: parsing-index-1 단일 막대 (전체 처리량)
        Series B: parsing-index-2 의 current_state 별 누적 막대
    하단 보조 테이블로 정확한 수치도 확인 가능.

    설정:
        - ``ES_HISTORY_DAYS``        : 최근 N일 (기본 7, 오늘 포함)
        - ``ES_HISTORY_STATE_KEYS``  : Series B 에 노출할 state (key,label)
        - ``ES_HISTORY_INDEX1/2``    : 각 인덱스 패턴
    """
    from datetime import date, timedelta
    from app.config import settings

    days = max(1, int(settings.ES_HISTORY_DAYS or 7))
    today = date.today()
    dates = [
        (today - timedelta(days=days - 1 - i)).isoformat()
        for i in range(days)
    ]
    state_triples = settings.es_history_state_keys()
    return templates.TemplateResponse(
        request,
        "es_history.html",
        {
            "nav_items":  NAV_ITEMS,
            "active_nav": "es_history",
            "page_title": "종합 처리 이력",
            "days":       days,
            "dates":      dates,
            # [(key, label, attr)] → JSON 직렬화 가능한 dict 로
            "states":     [{"key": k, "label": lab, "attr": at}
                            for k, lab, at in state_triples],
            "attr_order": ["stage", "normal", "complete", "check", ""],
            "index1":     settings.ES_HISTORY_INDEX1,
            "index2":     settings.ES_HISTORY_INDEX2,
        },
    )


@router.get("/history/data")
async def history_data(request: Request):
    """종합 처리 이력 데이터 API (JSON).

    parsing-index-1 + parsing-index-2 두 쿼리를 병렬로 실행해
    날짜별 처리량을 반환한다 (product/maker 차원 없음).
    응답 스키마는 :func:`app.services.es_service.run_history_overview` 참고.
    """
    result = await es_service.run_history_overview()
    status = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status)


# ── 준비 중 페이지 (나중에 구현) ─────────────────────────────────────────
@router.get("/anomaly")
def anomaly_page(request: Request):
    return templates.TemplateResponse(
        request,
        "es_stub.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "es_anomaly",
            "page_title": "이상 발생 현황",
        },
    )

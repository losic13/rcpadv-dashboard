"""AMAT 설비관리 페이지/API.

URL prefix: /amat

탭 구성:
  - 일반 쿼리 탭 : amat_abnormal_steps_no_treat (미처리)
                  amat_abnormal_steps_all      (전체)
                  → 두 탭 모두에서 STATUS 인라인 편집 + SAVE 가능
  - special 탭   : AMAT Abnormal Keyword       (panel-amat-keyword)

STATUS 일괄 업데이트는 POST /amat/abnormal-step/status (all-or-nothing) 사용.

DB 엔진은 DRAM 을 사용 — amat_service.DB_SOURCE 참조.
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.logger import get_logger
from app.queries.amat_queries import DML_QUERIES as AMAT_DML, QUERIES as AMAT_QUERIES
from app.repositories.mariadb import (
    execute as db_execute,
    execute_dml,
    execute_dml_many,
)
from app.routers._templating import NAV_ITEMS, templates
from app.services import amat_service

router = APIRouter(prefix="/amat")
log = get_logger("router.amat")

# AMAT Abnormal Step 의 status 허용값 — DML 실행 전 화이트리스트로 한 번 더 검증.
# Pydantic Literal 로도 1차 검증되지만, 명시적으로 set 형태로도 둬서 향후 확장 시 추적이 쉽도록.
ALLOWED_STATUSES: set[str] = {"ERROR", "CHECKED", "SUCCESS"}


@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "amat_page.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "amat",
            "page_title": amat_service.SOURCE_LABEL,
            "source": amat_service.SOURCE,
            "queries": amat_service.list_queries(),
            # 특수 탭: 전용 패널을 가진 탭 목록 (일반 쿼리 탭 뒤에 렌더링)
            "special_tabs": [
                {
                    "id": "amat-keyword",
                    "title": "AMAT Abnormal Keyword",
                    "description": "amat_keyword 테이블 조회 및 신규 키워드 등록.",
                    "panel_id": "panel-amat-keyword",
                },
            ],
        },
    )


@router.get("/query/{query_id}")
async def run_query(query_id: str, request: Request):
    """일반 쿼리 실행 — source_page.html / amat_page.html 의 QueryRunner 에서 호출."""
    params = dict(request.query_params)
    try:
        result = await amat_service.run(query_id, params)
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_id}")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"쿼리 실패: {e}")


# ── AMAT Keyword 관리 ────────────────────────────────────────────────────────
#   기존 /dram/keyword/* 에서 통째로 이전한 엔드포인트.

@router.get("/keyword/list")
async def keyword_list():
    """amat_keyword 테이블 전체 조회. No. 컬럼은 클라이언트에서 부여."""
    try:
        columns, rows = await asyncio.wait_for(
            asyncio.to_thread(
                db_execute,
                amat_service.DB_SOURCE,
                AMAT_QUERIES["amat_keyword_list"].sql,
            ),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
        return JSONResponse({"columns": columns, "rows": rows, "row_count": len(rows)})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        log.error("keyword_list 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"조회 실패: {e}")


class KeywordRegisterBody(BaseModel):
    name: str


@router.post("/keyword/register")
async def keyword_register(body: KeywordRegisterBody):
    """amat_keyword 테이블에 name 값을 INSERT."""
    name = body.name
    if not name:
        raise HTTPException(status_code=422, detail="name 값이 비어 있습니다.")
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                execute_dml,
                amat_service.DB_SOURCE,
                AMAT_DML["amat_keyword_insert"].sql,
                {"name": name},
            ),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
        log.info("keyword 등록 완료: %r", name)
        return JSONResponse({"ok": True, "name": name})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        log.error("keyword_register 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"등록 실패: {e}")


# ── AMAT Abnormal Step STATUS 일괄 업데이트 ─────────────────────────────────
#
# 동작 요약:
#   - 프론트(amat_page.html) 의 AbnormalStep 탭에서 STATUS 셀을 select 로 바꾼
#     뒤 SAVE 버튼을 누르면 변경 행 N건이 이 엔드포인트로 한 번에 전송된다.
#   - 본 엔드포인트는 **all-or-nothing**: 한 건이라도 실패하면 모든 변경을
#     ROLLBACK 한다 (execute_dml_many 가 단일 트랜잭션으로 묶음).
#   - 같은 idx 가 여러 번 들어오면 마지막 status 가 최종 값이 되는 셈이지만,
#     프론트가 dirty map(Map<idx, status>) 으로 중복을 이미 제거해 보낼 것이라
#     서버는 들어온 순서대로 그대로 실행한다.

class StatusUpdateItem(BaseModel):
    """STATUS 변경 한 행 — PK(idx) + 새 status."""
    idx: int = Field(..., description="amat_abnormal_step.idx (PK)")
    status: Literal["ERROR", "CHECKED", "SUCCESS"]


class StatusUpdateBody(BaseModel):
    items: list[StatusUpdateItem] = Field(default_factory=list)


@router.post("/abnormal-step/status")
async def abnormal_step_update_status(body: StatusUpdateBody):
    """N건의 STATUS 를 한 트랜잭션에서 UPDATE. 한 건이라도 실패하면 전체 ROLLBACK."""
    items = body.items
    if not items:
        # 빈 요청은 422 로 명확히 거부 (사용자가 SAVE 를 눌렀는데 dirty 가 0인 케이스).
        raise HTTPException(status_code=422, detail="변경 항목이 없습니다.")

    # 화이트리스트 재검증 (Pydantic Literal 통과한 값에 대한 방어적 한 번 더)
    bad = [it for it in items if it.status not in ALLOWED_STATUSES]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=f"허용되지 않은 status 값 포함: {sorted({it.status for it in bad})}",
        )

    # SQLAlchemy bind 파라미터 형태로 변환
    params_list = [{"idx": it.idx, "status": it.status} for it in items]
    sql = AMAT_DML["amat_abnormal_step_update_status"].sql

    try:
        total = await asyncio.wait_for(
            asyncio.to_thread(
                execute_dml_many,
                amat_service.DB_SOURCE,
                sql,
                params_list,
            ),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("abnormal_step_update_status 타임아웃 (n=%d)", len(items))
        raise HTTPException(status_code=504, detail="쿼리 타임아웃 — 모든 변경이 롤백되었습니다.")
    except Exception as e:
        log.error("abnormal_step_update_status 실패 (n=%d): %s", len(items), e)
        # execute_dml_many 가 트랜잭션 안에서 던졌다면 이미 ROLLBACK 된 상태.
        raise HTTPException(status_code=500, detail=f"STATUS 업데이트 실패 — 모든 변경이 롤백되었습니다: {e}")

    log.info("abnormal_step_update_status OK — 요청 %d건, 영향 %d행", len(items), total)
    return JSONResponse({
        "ok": True,
        "requested": len(items),
        "affected_rows": total,
    })

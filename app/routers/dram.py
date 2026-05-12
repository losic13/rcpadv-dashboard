"""DRAM DB 페이지/API."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.logger import get_logger
from app.queries.dram_queries import DML_QUERIES as DRAM_DML, QUERIES as DRAM_QUERIES
from app.repositories.mariadb import execute as db_execute, execute_dml, execute_dml_many
from app.routers._templating import NAV_ITEMS, templates
from app.services import dram_service

router = APIRouter(prefix="/dram")
log = get_logger("router.dram")


@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "source_page.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "dram",
            "page_title": dram_service.SOURCE_LABEL,
            "source": dram_service.SOURCE,
            "queries": dram_service.list_queries(),
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
    params = dict(request.query_params)
    try:
        result = await dram_service.run(query_id, params)
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_id}")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"쿼리 실패: {e}")


# ── AMAT Keyword 관리 ────────────────────────────────────────────────────────

@router.get("/keyword/list")
async def keyword_list():
    """amat_keyword 테이블 전체 조회. No. 컬럼은 클라이언트에서 부여."""
    try:
        columns, rows = await asyncio.wait_for(
            asyncio.to_thread(db_execute, "dram", DRAM_QUERIES["amat_keyword_list"].sql),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
        return JSONResponse({"columns": columns, "rows": rows, "row_count": len(rows)})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        log.error("keyword_list 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"조회 실패: {e}")


# ── AMAT Abnormal Step STATUS 일괄 저장 ──────────────────────────────────────

ALLOWED_STATUSES = {"ERROR", "CHECKED", "SUCCESS"}


class AbnormalStepStatusItem(BaseModel):
    idx: int
    status: str


class AbnormalStepSaveBody(BaseModel):
    changes: list[AbnormalStepStatusItem]


@router.post("/abnormal-step/save")
async def abnormal_step_save(body: AbnormalStepSaveBody):
    """변경된 amat_abnormal_step row들의 status를 idx 기준으로 일괄 UPDATE."""
    if not body.changes:
        raise HTTPException(status_code=422, detail="변경 항목이 없습니다.")

    # status 값 화이트리스트 검증
    invalid = [c for c in body.changes if c.status not in ALLOWED_STATUSES]
    if invalid:
        bad = ", ".join(f"{c.idx}:{c.status}" for c in invalid)
        raise HTTPException(status_code=422, detail=f"허용되지 않은 status 값: {bad}")

    params_list = [{"idx": c.idx, "status": c.status} for c in body.changes]
    sql = DRAM_DML["amat_abnormal_step_update_status"].sql

    try:
        updated = await asyncio.wait_for(
            asyncio.to_thread(execute_dml_many, "dram", sql, params_list),
            timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
        log.info("abnormal_step status 저장 완료: %d건", updated)
        return JSONResponse({"ok": True, "updated": updated})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="쿼리 타임아웃")
    except Exception as e:
        log.error("abnormal_step_save 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"저장 실패: {e}")


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
                "dram",
                DRAM_DML["amat_keyword_insert"].sql,
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

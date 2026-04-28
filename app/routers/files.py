"""Log File Download 페이지/API.

서버(=백엔드 호스트) 로컬 디스크의 임의 경로를 입력받아
- 파일이 존재하면 다운로드(Content-Disposition: attachment) 응답
- 존재하지 않으면 404 + 한국어 안내 메시지
- 디렉토리이거나 일반 파일이 아니면 400

인하우스 도구이므로 인증/권한은 두지 않는다는 전제에 따라
경로 화이트리스트도 별도로 강제하지 않는다(요청 사양 그대로).
필요하면 settings 에 ALLOWED_ROOTS 를 추가해 화이트리스트 처리 가능.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates

router = APIRouter(prefix="/files")
log = get_logger("router.files")


# ============================================================
# 페이지
# ============================================================
@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "files.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "files",
            "page_title": "Log File Download",
        },
    )


# ============================================================
# API: 파일 존재 여부 확인 (선택)
#   GET /files/check?path=...
# ============================================================
@router.get("/check")
def check(path: str = Query(..., description="확인할 절대/상대 경로")):
    p = _resolve_path(path)
    if not p.exists():
        return JSONResponse(
            {"exists": False, "path": str(p), "message": "파일이 존재하지 않습니다."},
            status_code=404,
        )
    if not p.is_file():
        return JSONResponse(
            {
                "exists": True,
                "is_file": False,
                "path": str(p),
                "message": "지정한 경로는 일반 파일이 아닙니다(디렉토리이거나 특수 파일).",
            },
            status_code=400,
        )

    try:
        size = p.stat().st_size
    except OSError:
        size = None

    return {
        "exists": True,
        "is_file": True,
        "path": str(p),
        "name": p.name,
        "size_bytes": size,
    }


# ============================================================
# API: 파일 다운로드
#   GET /files/download?path=...
# ============================================================
@router.get("/download")
def download(path: str = Query(..., description="다운로드할 파일 경로")):
    p = _resolve_path(path)

    if not p.exists():
        log.warning("파일 다운로드 실패 — 존재하지 않음: %s", p)
        raise HTTPException(
            status_code=404,
            detail=f"파일이 존재하지 않습니다: {p}",
        )
    if not p.is_file():
        log.warning("파일 다운로드 실패 — 일반 파일 아님: %s", p)
        raise HTTPException(
            status_code=400,
            detail=f"지정한 경로는 일반 파일이 아닙니다: {p}",
        )

    log.info("파일 다운로드 시작: %s", p)
    # RFC 5987 으로 한글/유니코드 파일명 안전 처리
    filename = p.name
    quoted = quote(filename)
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{filename}\"; "
            f"filename*=UTF-8''{quoted}"
        )
    }
    return FileResponse(
        path=str(p),
        filename=filename,
        media_type="application/octet-stream",
        headers=headers,
    )


# ============================================================
# 유틸
# ============================================================
def _resolve_path(raw: str) -> Path:
    """입력 경로를 정규화한 Path 로 변환.

    - 양끝 공백 제거
    - 사용자 홈(~) 확장
    - 환경변수($VAR / %VAR%) 확장
    - resolve() 까지는 호출하지 않음 — 심볼릭 링크는 그대로 따른다
    """
    if raw is None:
        raise HTTPException(status_code=400, detail="경로가 비어 있습니다.")
    s = raw.strip().strip('"').strip("'")
    if not s:
        raise HTTPException(status_code=400, detail="경로가 비어 있습니다.")

    # ~, $VAR, %VAR% 확장
    s = os.path.expanduser(s)
    s = os.path.expandvars(s)

    return Path(s)

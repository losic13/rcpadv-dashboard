"""Disk 용량 확인 페이지 / API.

`df -h /M_ADVISOR` 명령 결과를 파싱해
- 페이지: Jinja2 템플릿 (파이차트 + 표)
- API:    GET /disk-usage/data  →  JSON (JS fetch 용)
"""
from __future__ import annotations

import shlex
import subprocess
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.routers._templating import NAV_ITEMS, templates

router = APIRouter(prefix="/disk-usage")
log = get_logger("router.disk_usage")

# df 로 확인할 경로
DF_TARGET = "/M_ADVISOR"


# ============================================================
# 내부 헬퍼
# ============================================================

def _run_df(path: str = DF_TARGET) -> dict:
    """``df -h <path>`` 를 실행하고 파싱한 결과를 반환한다.

    반환 구조::

        {
          "ok": True,
          "path": "/M_ADVISOR",
          "raw": "Filesystem  Size  Used  Avail  Use%  Mounted on\\n...",
          "filesystem": "...",
          "size":        "100G",
          "used":        "45G",
          "available":   "55G",
          "use_pct":     45,          # int (%)
          "mounted_on":  "/M_ADVISOR",
          "size_bytes":  107374182400,   # None 이면 파싱 실패
          "used_bytes":  ...,
          "avail_bytes": ...,
        }

    오류 시::

        {"ok": False, "error": "...", "raw": "..."}
    """
    queried_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cmd = ["df", "-h", path]
    log.info("df 실행: %s", shlex.join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        raw = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        log.error("df 타임아웃: %s", path)
        return {"ok": False, "error": "df 명령 타임아웃(10초)", "raw": "", "queried_at": queried_at}
    except Exception as exc:  # noqa: BLE001
        log.error("df 실행 오류: %s", exc)
        return {"ok": False, "error": str(exc), "raw": "", "queried_at": queried_at}

    if result.returncode != 0:
        log.warning("df 비정상 종료 (rc=%d): %s", result.returncode, raw.strip())
        return {"ok": False, "error": raw.strip(), "raw": raw, "queried_at": queried_at}

    # ── 파싱 ────────────────────────────────────────────────
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        return {"ok": False, "error": "df 출력을 파싱할 수 없습니다.", "raw": raw}

    # df -h 헤더: Filesystem Size Used Avail Use% Mounted on
    # 실제 데이터 줄이 여러 줄로 래핑될 수 있으므로 split() 로 처리
    data_line = " ".join(lines[1:])  # 줄바꿈 래핑 대응
    parts = data_line.split()
    if len(parts) < 6:
        return {"ok": False, "error": f"파싱 실패 (컬럼 부족): {data_line!r}", "raw": raw}

    filesystem  = parts[0]
    size        = parts[1]
    used        = parts[2]
    available   = parts[3]
    use_pct_str = parts[4].rstrip("%")
    mounted_on  = parts[5]

    try:
        use_pct = int(use_pct_str)
    except ValueError:
        use_pct = 0

    # 바이트 환산 (파이차트용)
    def _to_bytes(human: str) -> int | None:
        """'45G' → 48318382080, '500M' → 524288000 등."""
        human = human.strip()
        if not human or human in ("-", "0"):
            return 0
        units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
        suffix = human[-1].upper()
        try:
            num = float(human[:-1])
            return int(num * units.get(suffix, 1))
        except ValueError:
            return None

    size_bytes  = _to_bytes(size)
    used_bytes  = _to_bytes(used)
    avail_bytes = _to_bytes(available)

    return {
        "ok":          True,
        "path":        path,
        "raw":         raw.strip(),
        "filesystem":  filesystem,
        "size":        size,
        "used":        used,
        "available":   available,
        "use_pct":     use_pct,
        "mounted_on":  mounted_on,
        "size_bytes":  size_bytes,
        "used_bytes":  used_bytes,
        "avail_bytes": avail_bytes,
        "queried_at":  queried_at,
    }


# ============================================================
# 페이지  GET /disk-usage
# ============================================================

@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "disk_usage.html",
        {
            "nav_items":  NAV_ITEMS,
            "active_nav": "disk_usage",
            "page_title": "Disk 용량 확인",
        },
    )


# ============================================================
# API  GET /disk-usage/data
# ============================================================

@router.get("/data")
def data():
    """df -h /M_ADVISOR 결과를 JSON 으로 반환. 프론트 fetch 용."""
    info = _run_df(DF_TARGET)
    status_code = 200 if info["ok"] else 500
    log.info(
        "disk-usage 응답: ok=%s path=%s used=%s/%s (%s%%)",
        info.get("ok"), info.get("path"),
        info.get("used"), info.get("size"), info.get("use_pct"),
    )
    return JSONResponse(content=info, status_code=status_code)

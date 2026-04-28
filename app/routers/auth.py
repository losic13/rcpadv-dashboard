"""로그인/로그아웃 라우터.

- 단일 비밀번호 기반 로그인 (settings.APP_PASSWORD)
- starlette SessionMiddleware 가 서명된 쿠키에 세션을 저장.
  request.session["authenticated"] = True 로 표시.
- 미인증 사용자가 보호된 페이지에 접속하면 /login 으로 리다이렉트.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.logger import get_logger
from app.routers._templating import templates

log = get_logger(__name__)

router = APIRouter()

# ---- 인증 우회 허용 경로 ----
# 미인증 상태에서도 접근 가능한 prefix 들. 정적 자원/로그인 자체/헬스 등.
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/login",
    "/logout",
    "/static/",
    "/favicon",
)


def is_authenticated(request: Request) -> bool:
    """현재 요청이 인증된 세션을 가졌는지."""
    try:
        return bool(request.session.get("authenticated"))
    except AssertionError:
        # SessionMiddleware 가 등록되지 않은 경우(테스트 등) 안전하게 False
        return False


def is_public_path(path: str) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


@router.get("/login")
def login_page(request: Request, next: str = "/", error: str | None = None):
    # 이미 로그인된 상태면 next 로 보냄
    if is_authenticated(request):
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "next": next or "/",
            "error": error,
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/"),
):
    # 타이밍 공격 회피용 상수시간 비교
    expected = settings.APP_PASSWORD or ""
    ok = hmac.compare_digest(password or "", expected)
    if not ok:
        log.warning("로그인 실패 (잘못된 비밀번호) from %s", request.client.host if request.client else "?")
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next or "/",
                "error": "비밀번호가 올바르지 않습니다.",
            },
            status_code=401,
        )

    request.session["authenticated"] = True
    log.info("로그인 성공 from %s", request.client.host if request.client else "?")
    # open redirect 방지: 외부 URL/스킴 차단, 같은 사이트 경로만 허용
    target = next or "/"
    if not target.startswith("/") or target.startswith("//"):
        target = "/"
    return RedirectResponse(url=target, status_code=303)


@router.get("/logout")
@router.post("/logout")
def logout(request: Request):
    try:
        request.session.clear()
    except AssertionError:
        pass
    return RedirectResponse(url="/login", status_code=303)

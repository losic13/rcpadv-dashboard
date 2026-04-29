"""EQP I/F Manager 페이지.

사이드바에서 "EQP I/F Manager" 를 누르면, settings.EQP_IF_MANAGER_URL 로
지정된 외부 사이트를 iframe 으로 임베드해 보여준다.

URL 은 .env 의 EQP_IF_MANAGER_URL 로 운영자가 직접 지정한다.
페이지 제목도 EQP_IF_MANAGER_TITLE 로 커스터마이즈 가능.

[제약사항]
  대상 사이트가 X-Frame-Options=DENY 또는 Content-Security-Policy:
  frame-ancestors 'none' 을 내려주는 경우 iframe 로드는 브라우저가
  거부한다(예: google.com 메인은 일반적으로 iframe 임베드 차단).
  이 경우 사용자에게 안내 메시지 + 새 창으로 열기 링크를 함께
  표시해 두어야 한다 — 템플릿이 이를 처리한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.routers._templating import NAV_ITEMS, templates

router = APIRouter(prefix="/eqp-if")


@router.get("")
def page(request: Request):
    return templates.TemplateResponse(
        request,
        "eqp_if.html",
        {
            "nav_items": NAV_ITEMS,
            "active_nav": "eqp_if",
            "page_title": settings.EQP_IF_MANAGER_TITLE or "EQP I/F Manager",
            "embed_url": (settings.EQP_IF_MANAGER_URL or "").strip(),
        },
    )

"""Jinja2 템플릿 인스턴스 - 모든 라우터에서 공유."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# ------------------------------------------------------------
# 정적 자원 캐시 무효화용 버전 문자열.
#
# 배경:
#   업데이트를 배포해도 브라우저가 /static/js/app.js, /static/css/app.css 를
#   캐시한 채 보고 있으면 새 클래스(CountCard 등)가 정의되지 않아
#   inline 스크립트가 ReferenceError 로 멈추고, "새로고침 버튼을 눌러도
#   클릭 이벤트가 안 먹힌다" 같은 증상이 나온다.
#
# 해결:
#   서버 부팅 시 핵심 정적 파일의 mtime 을 모아 짧은 해시를 만들어
#   템플릿에서 `<script src="/static/js/app.js?v={{ asset_version }}">`
#   처럼 붙인다. 코드를 새로 배포해 mtime 이 바뀌면 URL 도 바뀌어
#   브라우저가 자동으로 최신 파일을 받아 간다.
# ------------------------------------------------------------
def _compute_asset_version() -> str:
    paths = [
        STATIC_DIR / "js" / "app.js",
        STATIC_DIR / "css" / "app.css",
    ]
    parts = []
    for p in paths:
        try:
            parts.append(str(int(p.stat().st_mtime)))
        except OSError:
            parts.append("0")
    # 너무 길면 보기 싫으니 마지막 8자리만
    return "-".join(parts)[-12:]


ASSET_VERSION = _compute_asset_version()

# 모든 템플릿에서 {{ asset_version }} 으로 참조 가능
templates.env.globals["asset_version"] = ASSET_VERSION

# 사이드바 등에서 공유할 메뉴 정보
NAV_ITEMS = [
    {"key": "home",       "label": "RcpAdv 통합 대시보드",  "url": "/"},
    {"key": "files",      "label": "File Download", "url": "/files"},
    {"key": "log_search", "label": "Log Search",    "url": "/log-search"},
    {"key": "vnand",      "label": "VNAND DB",      "url": "/vnand"},
    {"key": "dram",       "label": "DRAM DB",       "url": "/dram"},
    {"key": "es",         "label": "Elasticsearch", "url": "/es"},
    {"key": "eqp_if",     "label": "EQP I/F Manager", "url": "/eqp-if"},
]

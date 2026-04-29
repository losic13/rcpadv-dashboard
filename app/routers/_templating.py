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
    # 앱 자산 + 주요 vendor 자산의 mtime 을 모두 반영해 버전을 만든다.
    # vendor 파일의 sourceMappingURL 주석을 떼는 등 vendor 파일이 바뀐
    # 경우에도 사용자 브라우저가 캐시된 옛 파일을 그대로 잡는 일이 없도록
    # base.html 의 vendor <script>/<link> 에도 ?v={{asset_version}} 을 붙인다.
    paths = [
        STATIC_DIR / "js" / "app.js",
        STATIC_DIR / "css" / "app.css",
        STATIC_DIR / "vendor" / "bootstrap" / "bootstrap.min.css",
        STATIC_DIR / "vendor" / "bootstrap" / "bootstrap.bundle.min.js",
        STATIC_DIR / "vendor" / "datatables" / "datatables.min.css",
        STATIC_DIR / "vendor" / "datatables" / "datatables.min.js",
        STATIC_DIR / "vendor" / "chartjs" / "chart.umd.min.js",
        STATIC_DIR / "vendor" / "jquery" / "jquery.min.js",
    ]
    parts = []
    for p in paths:
        try:
            parts.append(str(int(p.stat().st_mtime)))
        except OSError:
            parts.append("0")
    # 너무 길면 보기 싫으니 마지막 12자리만
    return "-".join(parts)[-12:]


ASSET_VERSION = _compute_asset_version()

# 모든 템플릿에서 {{ asset_version }} 으로 참조 가능
templates.env.globals["asset_version"] = ASSET_VERSION

# 사이드바 등에서 공유할 메뉴 정보
#
# 메뉴 정렬 규칙:
#   - 통합 대시보드 → 사용자 접속 이력 → Log Search → File Download
#     → VNAND DB → DRAM DB → EQP I/F Manager
#   - Elasticsearch 는 임시로 숨김 (라우터/페이지는 유지). 다시 노출하려면
#     아래 NAV_ITEMS_HIDDEN 의 "es" 항목을 NAV_ITEMS 로 옮기면 된다.
NAV_ITEMS = [
    {"key": "home",          "label": "통합 대시보드",     "url": "/"},
    {"key": "login_history", "label": "사용자 접속 이력",   "url": "/login-history"},
    {"key": "log_search",    "label": "Log Search",       "url": "/log-search"},
    {"key": "files",         "label": "File Download",    "url": "/files"},
    {"key": "vnand",         "label": "VNAND DB",         "url": "/vnand"},
    {"key": "dram",          "label": "DRAM DB",          "url": "/dram"},
    {"key": "eqp_if",        "label": "EQP I/F Manager",  "url": "/eqp-if"},
]

# 라우터/페이지는 살려두지만 사이드바에는 노출하지 않는 메뉴.
# 직접 URL 로 접근하면 동작하며, 다시 보이게 하려면 NAV_ITEMS 로 옮긴다.
NAV_ITEMS_HIDDEN = [
    {"key": "es", "label": "Elasticsearch", "url": "/es"},
]

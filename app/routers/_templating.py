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

# ============================================================
# 사이드바 2Tier 메뉴 구조
#
# 각 항목은 두 가지 타입:
#   - 단독 링크:  {"type": "link",     "key": ..., "label": ..., "url": ...}
#   - 카테고리:   {"type": "category", "label": ..., "icon": ..., "children": [...]}
#       children 각 항목: {"key": ..., "label": ..., "url": ..., "disabled": bool(선택)}
#
# disabled=True  인 항목은 클릭 불가 (준비 중 상태).
# active_nav 에 매칭되는 key 를 가진 항목이 속한 카테고리는 자동으로 열린 상태.
# ============================================================
NAV_ITEMS = [
    # ── 1) 단독 링크 ──────────────────────────────────────
    {
        "type":  "link",
        "key":   "home",
        "label": "통합 대시보드",
        "url":   "/",
    },

    # ── 2) UI Client ──────────────────────────────────────
    {
        "type":  "category",
        "key":   "cat_ui_client",
        "label": "UI Client",
        "icon":  "👤",
        "children": [
            {"key": "login_history", "label": "사용자 접속 이력", "url": "/login-history"},
        ],
    },

    # ── 3) 파일 시스템 ────────────────────────────────────
    {
        "type":  "category",
        "key":   "cat_filesystem",
        "label": "파일 시스템",
        "icon":  "🗂",
        "children": [
            {"key": "log_search", "label": "Log Search",   "url": "/log-search"},
            {"key": "files",      "label": "File Download", "url": "/files"},
        ],
    },

    # ── 4) Maria DB ───────────────────────────────────────
    #   AMAT 설비관리는 DRAM DB 안의 amat_* 테이블들을 사용하지만,
    #   "쿼리 조회만" 인 VNAND/DRAM 과 달리 페이지에서 다양한 작업
    #   (STATUS 인라인 편집/SAVE 등)을 수행할 수 있는 전용 페이지로 분리.
    {
        "type":  "category",
        "key":   "cat_mariadb",
        "label": "Maria DB",
        "icon":  "🗄",
        "children": [
            {"key": "vnand", "label": "VNAND",        "url": "/vnand"},
            {"key": "dram",  "label": "DRAM",         "url": "/dram"},
            {"key": "amat",  "label": "AMAT 설비관리", "url": "/amat"},
        ],
    },

    # ── 5) Elastic Search ────────────────────────────────
    {
        "type":  "category",
        "key":   "cat_elasticsearch",
        "label": "Elastic Search",
        "icon":  "🔍",
        "children": [
            {"key": "es_document",      "label": "Document 조회",  "url": "/es/document"},
            {"key": "es_eqp_status",    "label": "설비별 처리현황", "url": "/es/eqp-status"},
            {"key": "es_pending_delay", "label": "작업 대기 및 지연", "url": "/es/pending-delay"},
            {"key": "es_history",       "label": "종합 처리 이력",  "url": "/es/history"},
            {"key": "es_targets",       "label": "대상 설비",      "url": "/es/targets",  "disabled": True},
            {"key": "es_overview",      "label": "대상 로그 개요",  "url": "/es/overview", "disabled": True},
            {"key": "es_delay",         "label": "처리 지연 상태",  "url": "/es/delay",    "disabled": True},
            {"key": "es_anomaly",       "label": "이상 발생 현황",  "url": "/es/anomaly",  "disabled": True},
        ],
    },

    # ── 6) Infra ──────────────────────────────────────────
    {
        "type":  "category",
        "key":   "cat_infra",
        "label": "Infra",
        "icon":  "🖥",
        "children": [
            {"key": "parser_flow", "label": "파서 처리 절차",   "url": "/infra/parser-flow"},
            {"key": "disk_usage",  "label": "Disk 용량 확인",  "url": "/disk-usage"},
            {"key": "eqp_if",      "label": "EQP I/F Manager", "url": "/eqp-if"},
        ],
    },
]

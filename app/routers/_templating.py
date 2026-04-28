"""Jinja2 템플릿 인스턴스 - 모든 라우터에서 공유."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# 사이드바 등에서 공유할 메뉴 정보
NAV_ITEMS = [
    {"key": "home",  "label": "통합 대시보드",     "url": "/"},
    {"key": "files", "label": "Log File Download", "url": "/files"},
    {"key": "vnand", "label": "VNAND DB",         "url": "/vnand"},
    {"key": "dram",  "label": "DRAM DB",          "url": "/dram"},
    {"key": "es",    "label": "Elasticsearch",    "url": "/es"},
]

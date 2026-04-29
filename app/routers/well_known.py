"""`.well-known/` 경로 핸들러.

브라우저(특히 Chrome) 가 페이지 로드 시 자동으로 보내는 well-known
메타데이터 요청을 조용히 처리해 콘솔/서버 로그에 404 noise 가 쌓이는
것을 막는다.

대상 요청 (대표):
    GET /.well-known/appspecific/com.chrome.devtools.json
        - Chrome DevTools 의 "Automatic Workspace Folders" 기능이
          dev-server 의 워크스페이스 매핑을 자동 발견하려고 보낸다.
          매핑이 필요 없는 사내 운영 대시보드에서는 응답할 내용이
          없으므로 204 No Content 로 조용히 응답한다.
        - 참고: https://stackoverflow.com/questions/79629915

설계 원칙:
  - 인증 미들웨어가 가로채지 않도록 PUBLIC_PATH_PREFIXES 에 "/.well-known/"
    가 포함돼 있어야 한다 (app/routers/auth.py).
  - 그 외의 임의 /.well-known/* 경로는 정의되어 있지 않으므로 평소처럼
    FastAPI 가 404 를 돌려준다 (브라우저 자동 요청만 잡아 noise 제거).
"""
from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(prefix="/.well-known", include_in_schema=False)


@router.get("/appspecific/com.chrome.devtools.json")
def chrome_devtools_json() -> Response:
    # 빈 JSON 대신 204 No Content — DevTools 는 본문 없이도 정상 처리하며
    # 워크스페이스 매핑이 필요 없음을 명시적으로 알린다.
    return Response(status_code=204)

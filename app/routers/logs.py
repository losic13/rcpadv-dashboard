"""UI 로그 패널용 API. 인메모리 버퍼의 최근 N개 로그 반환."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.logger import memory_handler

router = APIRouter(prefix="/api/logs")


@router.get("")
def list_logs(since_index: int = 0):
    """since_index 이후의 로그만 반환 (간단한 폴링용).

    인메모리 deque 는 maxlen 으로 잘리므로, 클라이언트의 since_index 와
    실제 버퍼 크기를 비교해서 새 항목만 잘라 보낸다.
    """
    snapshot = memory_handler.snapshot()
    total = len(snapshot)

    if since_index < 0:
        since_index = 0
    if since_index > total:
        since_index = total

    new_logs = snapshot[since_index:]
    return JSONResponse({
        "total": total,
        "next_index": total,
        "logs": new_logs,
    })

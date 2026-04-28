"""로깅 설정.

- 파일 로그: RotatingFileHandler (10MB x 5)
- 인메모리 버퍼: UI 로그 패널용 (최근 N개 deque)
- 콘솔 로그: 개발용

치명적인 오류와 실행 내역만 기록. 트레이스는 저장하지 않음.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.config import settings


class InMemoryBufferHandler(logging.Handler):
    """UI 로그 패널에 보여줄 최근 로그 N개를 메모리에 보관."""

    def __init__(self, maxlen: int) -> None:
        super().__init__()
        self.buffer: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            })
        except Exception:
            # 로깅 핸들러 자체 에러는 무시 (앱 흐름 영향 X)
            pass

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self.buffer)


# ---- 전역 핸들러 인스턴스 (라우터에서 참조) ----
memory_handler = InMemoryBufferHandler(maxlen=settings.LOG_BUFFER_SIZE)


def setup_logging() -> None:
    """앱 부트스트랩 시 1회 호출."""
    log_path = Path(settings.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    memory_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # 중복 핸들러 방지 (uvicorn reload 등)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.addHandler(memory_handler)

    # 외부 라이브러리 잡음 줄이기
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("elastic_transport").setLevel(logging.WARNING)
    logging.getLogger("elasticsearch").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

#!/bin/bash
# ============================================================
# 사내 대시보드 실행 스크립트 (nohup)
# 사용법: ./run.sh start | stop | status | restart
# ============================================================

cd "$(dirname "$0")"

PID_FILE="app.pid"
LOG_OUT="logs/uvicorn.out"
APP="app.main:app"
HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-8000}"

mkdir -p logs

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
        echo "[!] 이미 실행 중입니다 (PID: $(cat $PID_FILE))"
        exit 1
    fi

    if [ ! -d ".venv" ]; then
        echo "[!] .venv 가 없습니다. 먼저 'uv sync' 를 실행하세요."
        exit 1
    fi

    source .venv/bin/activate
    nohup uvicorn "$APP" --host "$HOST" --port "$PORT" \
        > "$LOG_OUT" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1
    echo "[+] 시작됨 (PID: $(cat $PID_FILE), http://${HOST}:${PORT})"
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "[!] PID 파일 없음. 실행 중이 아닙니다."
        return
    fi
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "[+] 중지됨 (PID: $PID)"
    else
        echo "[!] 프로세스 없음 (PID: $PID)"
    fi
    rm -f "$PID_FILE"
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
        echo "[+] 실행 중 (PID: $(cat $PID_FILE))"
    else
        echo "[ ] 중지 상태"
    fi
}

case "$1" in
    start)   start ;;
    stop)    stop ;;
    status)  status ;;
    restart) stop; sleep 1; start ;;
    *)       echo "사용법: $0 {start|stop|status|restart}"; exit 1 ;;
esac

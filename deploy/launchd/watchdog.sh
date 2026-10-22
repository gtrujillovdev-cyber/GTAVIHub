#!/usr/bin/env bash
# ==============================================================================
# GTA VI Hub Spain - Headless Watchdog & Autonomous Daemon Manager
# ==============================================================================
set -e

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"
PYTHON="$DIR/.venv/bin/python3"
LOG_DIR="$DIR/logs"
HEARTBEAT="$DIR/data/heartbeat.txt"

mkdir -p "$LOG_DIR"

# 1. Comprobación de Heartbeat (detectar si el proceso está congelado/pillado)
NOW=$(date +%s)
if [ -f "$HEARTBEAT" ] && pgrep -f "main.py --telegram" >/dev/null 2>&1; then
    LAST_BEAT=$(cat "$HEARTBEAT" 2>/dev/null || echo 0)
    DIFF=$((NOW - LAST_BEAT))
    # Si han pasado más de 10 minutos (600 s) sin latido, matar proceso colgado
    if [ "$DIFF" -gt 600 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Watchdog] Heartbeat caducado (${DIFF}s > 600s). Bot pillado. Matando y reiniciando..." >> "$LOG_DIR/watchdog.log"
        pkill -9 -f "main.py --telegram" 2>/dev/null || true
        pkill -9 -f "ffmpeg.*SHORT_" 2>/dev/null || true
        pkill -9 -f "yt_dlp" 2>/dev/null || true
        sleep 1
    fi
fi

# 2. Asegurar que el bot de Telegram esté siempre corriendo (Auto-healing 24/7)
if ! pgrep -f "main.py --telegram" >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Watchdog] Bot de Telegram no detectado o tras reinicio. Arrancando..." >> "$LOG_DIR/watchdog.log"
    nohup "$PYTHON" -u "$DIR/main.py" --telegram >> "$LOG_DIR/telegram_bot_stdout.log" 2>> "$LOG_DIR/telegram_bot_stderr.log" &
fi

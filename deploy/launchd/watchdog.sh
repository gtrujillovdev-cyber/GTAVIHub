#!/usr/bin/env bash
# ==============================================================================
# GTA VI Hub Spain - Headless Watchdog & Autonomous Daemon Manager
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"
PYTHON="$DIR/.venv/bin/python3"
LOG_DIR="$DIR/logs"

mkdir -p "$LOG_DIR"

# 1. Asegurar que el bot de Telegram esté siempre corriendo
if ! pgrep -f "main.py --telegram" >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Watchdog] Bot de Telegram caído o tras reinicio. Arrancando..." >> "$LOG_DIR/watchdog.log"
    nohup "$PYTHON" -u "$DIR/main.py" --telegram >> "$LOG_DIR/telegram_bot_stdout.log" 2>> "$LOG_DIR/telegram_bot_stderr.log" &
fi

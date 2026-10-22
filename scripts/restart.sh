#!/usr/bin/env bash
# ==============================================================================
# GTA VI Hub Spain - Manual Service Restart Script
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "[*] Deteniendo procesos de renderizado o descargas colgadas..."
pkill -9 -f "ffmpeg.*SHORT_" 2>/dev/null || true
pkill -9 -f "yt_dlp" 2>/dev/null || true

echo "[*] Reiniciando servicio de Telegram Bot..."
pkill -f "main.py --telegram" 2>/dev/null || true
sleep 1

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
mkdir -p "$DIR/logs"
nohup .venv/bin/python3 -u main.py --telegram > logs/telegram_bot_stdout.log 2> logs/telegram_bot_stderr.log &
sleep 2

echo "[✓] Estado del proceso tras reinicio:"
pgrep -fl "main.py --telegram" || echo "[!] Error: el proceso no arrancó."
echo "[✓] Reinicio completado con éxito."

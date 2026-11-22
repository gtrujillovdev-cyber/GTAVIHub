#!/usr/bin/env python3
"""
scripts/x_daily_scout.py — Rastreador nocturno diario de Likes de X (@00:02 CET).

Inspecciona los 'Me gusta' de la cuenta de X (@GaBtc1888), detecta nuevos creadores
y vídeos de guías, localizaciones y secretos de GTA 6, y los incorpora automáticamente:
1. Al registro de fuentes en 'config/channels.json' (como fuentes activas).
2. A la cola de clips de alta calidad 'data/curated_queue.json'.
3. Envía un reporte conciso por Telegram al administrador.
"""

import sys
from pathlib import Path
from datetime import datetime

# Añadir raíz al PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.x_scout import scan_x_timeline, ingest_x_likes_as_sources
from src.telegram_bot import send_telegram_alert

def run_daily_x_scout():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] 🚀 Iniciando X Daily Scout nocturno de Likes...")

    try:
        # Escanear Likes con prioridad alta
        candidates = scan_x_timeline(
            max_candidates=25,
            max_scrolls=8,
            include_likes=True
        )

        liked_candidates = [c for c in candidates if c.get("is_liked")]
        stats = ingest_x_likes_as_sources(liked_candidates)

        new_sources = stats.get("registered_sources", 0)
        new_clips = stats.get("queued_clips", 0)

        msg = (
            f"🐦 *X SCOUT NOCTURNO (00:02 CET)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❤️ *Likes analizados:* `{len(liked_candidates)}`\n"
            f"➕ *Nuevos canales registrados:* `{new_sources}`\n"
            f"🎯 *Clips en cola curada:* `{new_clips}`\n"
        )

        if new_sources > 0:
            msg += "\n_Los nuevos creadores de guías ya se han añadido a config/channels.json._"
        else:
            msg += "\n_No se detectaron creadores nuevos en los Likes de hoy._"

        print(f"[X Scout] Resultado: {new_sources} nuevos canales, {new_clips} nuevos clips.")
        send_telegram_alert(msg)

    except Exception as e:
        err_msg = f"⚠️ [X Scout Nocturno] Error en la ejecución: {e}"
        print(err_msg)
        try:
            send_telegram_alert(err_msg)
        except Exception:
            pass

if __name__ == "__main__":
    run_daily_x_scout()

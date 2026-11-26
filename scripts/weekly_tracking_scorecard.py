#!/usr/bin/env python3
"""
scripts/weekly_tracking_scorecard.py
====================================
Sincroniza métricas reales de YouTube/TikTok (snapshots 6h/24h/48h),
actualiza los pesos A/B en `data/viral_playbook.json` y envía un scorecard
semanal (solo texto, sin multimedia) a Telegram.

Uso:
  python3 scripts/weekly_tracking_scorecard.py --days 7 --send-telegram
  python3 scripts/weekly_tracking_scorecard.py --days 7 --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from src.performance_tracker import (
    detect_and_apply_winning_angles,
    format_weekly_scorecard_telegram,
    generate_weekly_scorecard,
    sync_live_channel_metrics,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scorecard semanal de tracking A/B (YouTube + TikTok).")
    parser.add_argument("--days", type=int, default=7, help="Ventana de días a analizar (default: 7).")
    parser.add_argument("--send-telegram", action="store_true", help="Enviar el resumen en texto a Telegram.")
    parser.add_argument("--dry-run", action="store_true", help="Imprimir el scorecard sin enviarlo ni modificar playbook.")
    args = parser.parse_args()

    try:
        synced = sync_live_channel_metrics(limit=30)
        print(f"[Tracking] YouTube live sync: {len(synced)} vídeos actualizados.")
    except Exception as exc:
        print(f"[Tracking] Aviso en YouTube live sync: {exc}")

    try:
        from src.learning_engine import sync_tiktok_insights_to_playbook
        sync_tiktok_insights_to_playbook()
    except Exception as exc:
        print(f"[Tracking] Aviso en TikTok sync: {exc}")

    if not args.dry_run:
        try:
            detect_and_apply_winning_angles(limit=20)
        except Exception as exc:
            print(f"[Tracking] Aviso en winning angles: {exc}")

    scorecard = generate_weekly_scorecard(days=args.days, update_playbook=not args.dry_run)
    text = format_weekly_scorecard_telegram(scorecard)
    print("\n" + text + "\n")

    if args.send_telegram and not args.dry_run:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if token and chat_id:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=15,
            )
            print(f"[Tracking] Telegram scorecard status={resp.status_code} ok={resp.ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

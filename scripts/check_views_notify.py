"""
Monitor de primeras vistas para GTA VI Hub Spain.

Corre cada 30 min via cron. Comprueba si los vídeos subidos hoy
han recibido sus primeras visualizaciones y notifica por Telegram.

Cron (añadir con: crontab -e):
    */30 * * * * /Users/GabrielTrujilloVallejo/GTAVIHub/.venv/bin/python3
                 /Users/GabrielTrujilloVallejo/GTAVIHub/scripts/check_views_notify.py
                 >> /Users/GabrielTrujilloVallejo/GTAVIHub/logs/views_monitor.log 2>&1
"""

import json
import os
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

PROCESSED_FILE = BASE_DIR / "data" / "processed.json"
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOOKBACK_HOURS = 48  # Solo vigilar vídeos subidos en las últimas 48h


def send_telegram(text: str) -> None:
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"[Telegram] Error: {e}")


def get_youtube_views(video_ids: list) -> dict:
    """Consulta YouTube API para obtener vistas de una lista de IDs."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file = BASE_DIR / "token.json"
        if not token_file.exists():
            return {}

        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        yt = build("youtube", "v3", credentials=creds)
        resp = yt.videos().list(
            id=",".join(video_ids),
            part="statistics,snippet"
        ).execute()

        result = {}
        for v in resp.get("items", []):
            vid_id = v["id"]
            views = int(v["statistics"].get("viewCount", 0))
            title = v["snippet"].get("title", "")[:50]
            result[vid_id] = {"views": views, "title": title}
        return result
    except Exception as e:
        print(f"[YouTube API] Error: {e}")
        return {}


def main():
    if not PROCESSED_FILE.exists():
        print("[Monitor] No existe processed.json — saliendo.")
        return

    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    cutoff = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
    updated = False

    # Filtrar vídeos recientes con URL de YouTube
    candidates = []
    for rec in records:
        yt_url = rec.get("youtube_uploaded_url") or rec.get("uploaded_youtube_url", "")
        if not yt_url:
            continue
        # Extraer video ID
        vid_id = yt_url.split("youtu.be/")[-1].split("?")[0] if "youtu.be/" in yt_url else ""
        if not vid_id or len(vid_id) < 8:
            continue
        # Solo vídeos recientes
        date_str = rec.get("date", "")
        try:
            upload_dt = datetime.fromisoformat(date_str)
            if upload_dt < cutoff:
                continue
        except Exception:
            continue
        # Solo los que no han sido notificados aún
        if rec.get("first_view_notified"):
            continue

        candidates.append((rec, vid_id))

    if not candidates:
        print("[Monitor] Sin candidatos nuevos para vigilar.")
        return

    print(f"[Monitor] Vigilando {len(candidates)} vídeos subidos en las últimas {LOOKBACK_HOURS}h...")

    video_ids = [vid_id for _, vid_id in candidates]
    views_data = get_youtube_views(video_ids)

    for rec, vid_id in candidates:
        info = views_data.get(vid_id)
        if not info:
            continue
        views = info["views"]
        title = info["title"]
        print(f"  {vid_id}: {views} vistas — {title[:40]}")

        if views > 0:
            # Primera vista detectada — notificar
            msg = (
                f"👁️ *¡TU VÍDEO YA TIENE VISITAS!*\n\n"
                f"📹 _{title}_\n"
                f"🔗 https://youtu.be/{vid_id}\n\n"
                f"👀 *Vistas actuales:* `{views:,}`\n"
                f"🎉 ¡Ya está indexado y la gente lo está viendo!"
            )
            send_telegram(msg)
            print(f"  [OK] Notificación enviada para {vid_id} ({views} vistas)")
            rec["first_view_notified"] = True
            rec["first_view_count"] = views
            rec["first_view_at"] = datetime.now().isoformat()
            updated = True

    if updated:
        with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print("[Monitor] processed.json actualizado con marcas de notificación.")


if __name__ == "__main__":
    main()

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

        token_extra = BASE_DIR / "token_extra.json"
        token_file = token_extra if token_extra.exists() else (BASE_DIR / "token.json")
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
    try:
        from src.channel_sentinel import update_realtime_metrics
        updated_sentinel = update_realtime_metrics(max_items=6)
        if updated_sentinel > 0:
            print(f"[ChannelSentinel] {updated_sentinel} checkpoints de analíticas actualizados.")
    except Exception as e:
        print(f"[ChannelSentinel] Error actualizando checkpoints: {e}")
    try:
        from src.performance_tracker import fetch_recent_metrics
        fetch_recent_metrics(max_items=6)
    except Exception as e:
        print(f"[PerformanceTracker] Aviso actualizando métricas: {e}")
    try:
        from src.community_manager import run_autonomous_community_cycle
        comm = run_autonomous_community_cycle(yt_max=6, ig_max=4)
        if comm.get("total_replied", 0) > 0:
            print(f"[Community] Respuestas enviadas: {comm['total_replied']} (YT={comm['youtube']['replied']}, IG={comm['instagram']['replied']})")
    except Exception as e:
        print(f"[Community] Error en ciclo autónomo: {e}")

    try:
        from src.x_scout import X_PROFILE_DIR, scan_x_timeline
        x_sync_stamp = BASE_DIR / "data" / ".x_scout_last_sync"
        run_x = True
        if x_sync_stamp.exists():
            try:
                age_sec = datetime.now().timestamp() - x_sync_stamp.stat().st_mtime
                if age_sec < 4 * 3600:
                    run_x = False
            except Exception:
                pass
        if run_x and X_PROFILE_DIR.exists():
            scan_x_timeline(max_candidates=12, max_scrolls=4, include_likes=True)
            x_sync_stamp.write_text(str(datetime.now().timestamp()), encoding="utf-8")
    except Exception as e:
        print(f"[X Scout] Error en ingesta automática de Likes: {e}")

    if os.getenv("ENABLE_INSTAGRAM", "false").lower() in ("true", "1", "yes"):
        try:
            from src.story_scheduler import can_publish_story, publish_scheduled_story
            can_story, story_reason = can_publish_story(force=False)
            if can_story:
                print("[Stories] Ventana óptima detectada. Publicando historia autónoma...")
                res_url, story_name, story_kind = publish_scheduled_story(force=False, dry_run=False)
                if res_url:
                    print(f"[Stories] [✓] Historia autónoma publicada con éxito: {story_name} ({story_kind}) -> {res_url}")
                    send_telegram(f"📸 *¡Nueva Historia en Instagram!*\n\n🌴 *Contenido:* `{story_name}`\n🏷️ *Tipo:* `{story_kind.upper()}`\n🔗 {res_url}")
            else:
                print(f"[Stories] Cooldown activo: {story_reason}")
        except Exception as e:
            print(f"[Stories] Error en ciclo de historias: {e}")

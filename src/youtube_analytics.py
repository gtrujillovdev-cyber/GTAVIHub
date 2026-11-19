import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .uploader import get_authenticated_youtube_service

def fetch_channel_overview() -> Optional[Dict[str, Any]]:
    """Obtiene los datos estadísticos generales del canal conectado en token.json."""
    youtube = get_authenticated_youtube_service()
    if not youtube:
        return None

    try:
        res = youtube.channels().list(mine=True, part="snippet,statistics,contentDetails").execute()
        items = res.get("items", [])
        if not items:
            return None
        
        ch = items[0]
        snippet = ch.get("snippet", {})
        statistics = ch.get("statistics", {})
        
        return {
            "id": ch.get("id"),
            "title": snippet.get("title", "GTA VI Hub Spain"),
            "custom_url": snippet.get("customUrl", "@gtavihubspain"),
            "published_at": snippet.get("publishedAt", ""),
            "subscribers": int(statistics.get("subscriberCount", 0)),
            "views": int(statistics.get("viewCount", 0)),
            "videos": int(statistics.get("videoCount", 0)),
            "hidden_subscribers": statistics.get("hiddenSubscriberCount", False)
        }
    except Exception as e:
        print(f"[YouTube Analytics] Error consultando overview: {e}")
        return None

def fetch_recent_videos(limit: int = 4) -> List[Dict[str, Any]]:
    """Obtiene los últimos vídeos subidos con sus métricas individuales de rendimiento."""
    youtube = get_authenticated_youtube_service()
    if not youtube:
        return []

    try:
        # 1. Obtener ID del canal
        ch_res = youtube.channels().list(mine=True, part="contentDetails").execute()
        items = ch_res.get("items", [])
        if not items:
            return []
        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2. Obtener los últimos elementos de la lista de subidas
        pl_res = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet,contentDetails",
            maxResults=limit
        ).execute()

        video_items = pl_res.get("items", [])
        if not video_items:
            return []

        video_ids = [v["contentDetails"]["videoId"] for v in video_items]

        # 3. Obtener estadísticas detalladas de cada vídeo
        v_res = youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,statistics"
        ).execute()

        results = []
        for v in v_res.get("items", []):
            v_snip = v.get("snippet", {})
            v_stats = v.get("statistics", {})
            v_id = v.get("id")
            results.append({
                "id": v_id,
                "title": v_snip.get("title", ""),
                "published_at": v_snip.get("publishedAt", ""),
                "views": int(v_stats.get("viewCount", 0)),
                "likes": int(v_stats.get("likeCount", 0)),
                "comments": int(v_stats.get("commentCount", 0)),
                "url": f"https://youtu.be/{v_id}"
            })
        return results
    except Exception as e:
        print(f"[YouTube Analytics] Error consultando vídeos recientes: {e}")
        return []

def get_youtube_analytics_report() -> str:
    """Genera un reporte conciso y profesional de analíticas de YouTube para Telegram con fallback a yt-dlp."""
    overview = fetch_channel_overview()
    recent = fetch_recent_videos(limit=5) if overview else []

    # Fallback si YouTube Data API OAuth token ha caducado
    if not overview or not recent:
        from .config import DATA_DIR
        processed_file = DATA_DIR / "processed.json"
        recent_candidates = []
        if processed_file.exists():
            try:
                with open(processed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in reversed(data):
                            yt_url = item.get("youtube_uploaded_url")
                            if yt_url and "youtu" in yt_url and "mock" not in yt_url:
                                recent_candidates.append({
                                    "url": yt_url,
                                    "title": item.get("youtube_title") or item.get("title", "GTA 6 Short")
                                })
                                if len(recent_candidates) >= 5:
                                    break
            except Exception:
                pass

        if recent_candidates:
            total_views = 0
            total_likes = 0
            total_comments = 0
            scraped_items = []

            for c in recent_candidates:
                try:
                    res = subprocess.run([
                        sys.executable, "-m", "yt_dlp",
                        "--dump-json", "--no-download", c["url"]
                    ], capture_output=True, text=True, timeout=12)
                    if res.returncode == 0 and res.stdout.strip():
                        v_info = json.loads(res.stdout)
                        v_cnt = int(v_info.get("view_count") or 0)
                        l_cnt = int(v_info.get("like_count") or 0)
                        c_cnt = int(v_info.get("comment_count") or 0)
                        total_views += v_cnt
                        total_likes += l_cnt
                        total_comments += c_cnt
                        scraped_items.append({
                            "title": v_info.get("title") or c["title"],
                            "url": c["url"],
                            "views": v_cnt,
                            "likes": l_cnt,
                            "comments": c_cnt,
                        })
                except Exception:
                    pass

            if scraped_items:
                report = (
                    "📈 *MÉTRICAS ACUMULADAS Y RENDIMIENTO (@GTAVIHubExtra)*\n"
                    + ("═" * 38) + "\n\n"
                    + f"🔥 *TOTAL ACUMULADO (Últimos {len(scraped_items)} Shorts):*\n"
                    + f"• 👁️ *Vistas Totales:* `{total_views:,}`\n"
                    + f"• ❤️ *Likes Totales:* `{total_likes:,}`\n"
                    + f"• 💬 *Comentarios Totales:* `{total_comments:,}`\n\n"
                    + "📊 *DETALLE INDIVIDUAL POR CLIP:*\n"
                )
                for idx, item in enumerate(scraped_items, 1):
                    clean_t = item["title"][:42] + ("..." if len(item["title"]) > 42 else "")
                    report += (
                        f"\n*{idx}.* [{clean_t}]({item['url']})\n"
                        f"   • Vistas: `{item['views']:,}` | Likes: `{item['likes']:,}` | Comentarios: `{item['comments']}`\n"
                    )
                report += (
                    "\n" + ("═" * 38) + "\n"
                    "💡 _Métricas obtenidas en directo vía scraper público con fallback resiliente._"
                )
                return report

        return (
            "📈 *MÉTRICAS DE YOUTUBE — GTA VI HUB*\n"
            + ("═" * 36) + "\n\n"
            + "⚠️ *YouTube API No Disponible*\n"
            + "No se pudo conectar con YouTube Data API ni consultar vídeos recientes.\n"
            + "Asegúrate de que `token.json` esté autorizado con:\n"
            + "`python3 auth_youtube.py`"
        )

    subs = f"{overview['subscribers']:,}"
    views = f"{overview['views']:,}"
    vids = overview["videos"]
    handle = overview["custom_url"]
    title = overview["title"]

    report = (
        "📈 *MÉTRICAS EN VIVO DE YOUTUBE*\n"
        + ("═" * 36) + "\n\n"
        + f"📺 *Canal:* `{title}` ({handle})\n"
        + f"👥 *Suscriptores:* `{subs}`\n"
        + f"👁️ *Visualizaciones Totales del Canal:* `{views}`\n"
        + f"🎬 *Vídeos Públicos:* `{vids}`\n\n"
        + "🔥 *Rendimiento de Subidas Recientes:*\n"
    )

    if recent:
        sub_views = sum(v["views"] for v in recent)
        sub_likes = sum(v["likes"] for v in recent)
        sub_comm = sum(v["comments"] for v in recent)
        report += (
            f"• 📊 *Acumulado Reciente:* `{sub_views:,}` vistas | `{sub_likes:,}` likes | `{sub_comm:,}` comms\n\n"
        )
        for idx, vid in enumerate(recent, 1):
            short_title = vid["title"][:42] + ("..." if len(vid["title"]) > 42 else "")
            report += (
                f"\n*{idx}.* [{short_title}]({vid['url']})\n"
                f"   • Vistas: `{vid['views']:,}` | Likes: `{vid['likes']:,}` | Comentarios: `{vid['comments']}`\n"
            )
    else:
        report += "\n_No hay subidas recientes registradas en el canal o canal nuevo._\n"

    report += (
        "\n" + ("═" * 36) + "\n"
        "💡 _Datos sincronizados en tiempo real con YouTube Data API v3._"
    )
    return report

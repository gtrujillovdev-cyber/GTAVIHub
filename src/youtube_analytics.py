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
    """Genera un reporte conciso y profesional de analíticas de YouTube para Telegram."""
    overview = fetch_channel_overview()
    if not overview:
        return (
            "📈 *MÉTRICAS DE YOUTUBE — GTA VI HUB*\n"
            + ("═" * 36) + "\n\n"
            + "⚠️ *YouTube API No Disponible*\n"
            + "No se pudo conectar con YouTube Data API.\n"
            + "Asegúrate de que `token.json` esté presente y autorizado con:\n"
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
        + f"👁️ *Visualizaciones Totales:* `{views}`\n"
        + f"🎬 *Vídeos Públicos:* `{vids}`\n\n"
        + "🔥 *Rendimiento de Subidas Recientes:*\n"
    )

    recent = fetch_recent_videos(limit=3)
    if recent:
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

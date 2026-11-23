import os
import sys
import json
import ssl
import urllib.request
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .config import DATA_DIR, BASE_DIR
from .uploader import get_authenticated_youtube_service

BROWSER_PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles"

def fetch_channel_overview() -> Optional[Dict[str, Any]]:
    """Obtiene los datos estadísticos generales del canal conectado (prioriza token_extra.json)."""
    target = "extra" if (BASE_DIR / "token_extra.json").exists() else "main"
    youtube = get_authenticated_youtube_service(target_channel=target)
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

def fetch_tiktok_overview(username: str = "gtavihubextra") -> Optional[Dict[str, Any]]:
    """Obtiene métricas públicas del perfil de TikTok (vistas de clips, likes y seguidores) mediante yt-dlp y scraper."""
    followers = 0
    total_likes = 0
    total_videos = 0
    total_views = 0
    recent_videos = []

    # 1. Intentar extracción completa de vistas y likes por vídeo mediante yt-dlp
    try:
        from .config import BASE_DIR
        ytdlp_candidates = [
            "/opt/homebrew/bin/yt-dlp",
            "/usr/local/bin/yt-dlp",
            "yt-dlp",
            str(BASE_DIR / ".venv" / "bin" / "yt-dlp"),
        ]
        chosen_bin = None
        for b in ytdlp_candidates:
            if b.startswith("/") and os.path.exists(b) and os.access(b, os.X_OK):
                chosen_bin = b
                break

        cmd = [
            chosen_bin or "yt-dlp",
            "--no-check-certificates",
            "--flat-playlist", "--dump-json",
            f"https://www.tiktok.com/@{username}"
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().split("\n"):
                if line.strip():
                    try:
                        v = json.loads(line)
                        v_views = int(v.get("view_count") or 0)
                        v_likes = int(v.get("like_count") or 0)
                        total_views += v_views
                        total_likes += v_likes
                        recent_videos.append({
                            "id": v.get("id"),
                            "title": v.get("title") or "TikTok Clip",
                            "views": v_views,
                            "likes": v_likes
                        })
                    except Exception:
                        pass
            total_videos = len(recent_videos)
    except Exception as e:
        print(f"[Analytics] Info yt-dlp TikTok (@{username}): {e}")

    # 2. Complementar o rescatar seguidores/likes base mediante el rehydration scraper
    try:
        url = f"https://www.tiktok.com/@{username}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            if "__UNIVERSAL_DATA_FOR_REHYDRATION__" in html:
                part = html.split("__UNIVERSAL_DATA_FOR_REHYDRATION__")[1].split(">", 1)[1].split("</script>", 1)[0]
                jdata = json.loads(part)
                stats = jdata.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {}).get("stats", {})
                followers = int(stats.get("followerCount", 0) or 0)
                if total_likes == 0:
                    total_likes = int(stats.get("heartCount", 0) or 0)
                if total_videos == 0:
                    total_videos = int(stats.get("videoCount", 0) or 0)
    except Exception as e:
        print(f"[Analytics] Error consultando TikTok web rehydration (@{username}): {e}")

    if total_videos > 0 or total_views > 0 or total_likes > 0:
        return {
            "username": username,
            "followers": followers,
            "likes": total_likes,
            "videos": total_videos,
            "views": total_views,
            "recent_videos": recent_videos
        }
    return None


def fetch_instagram_overview(username: str = "gtavihubextra") -> Optional[Dict[str, Any]]:
    """Obtiene métricas de Instagram Reels del perfil conectado mediante instagrapi."""
    try:
        from instagrapi import Client
        cl = Client()
        sfile = BROWSER_PROFILE_DIR / f"instagrapi_session_{username}.json"
        if not sfile.exists():
            sfile = BROWSER_PROFILE_DIR / "instagrapi_session.json"
        if not sfile.exists():
            return None

        cl.load_settings(str(sfile))
        u_info = cl.user_info(cl.user_id)
        medias = cl.user_medias(cl.user_id, amount=6)
        total_views = 0
        total_likes = 0
        media_list = []
        for m in medias:
            likes = int(getattr(m, "like_count", 0) or 0)
            views = int(getattr(m, "view_count", None) or getattr(m, "play_count", 0) or 0)
            total_likes += likes
            total_views += views
            media_list.append({"id": str(m.pk), "likes": likes, "views": views})

        return {
            "username": username,
            "followers": int(getattr(u_info, "follower_count", 0) or 0),
            "posts": int(getattr(u_info, "media_count", 0) or 0),
            "views_recent": total_views,
            "likes_recent": total_likes,
            "medias": media_list,
        }
    except Exception as e:
        print(f"[Analytics] Error consultando Instagram (@{username}): {e}")
    return None


def get_multiplatform_analytics_report() -> str:
    """Genera el reporte integral de todas las plataformas (YouTube, TikTok, Instagram Reels) para Telegram con contador global agregado."""
    yt_report = get_youtube_analytics_report()
    recent_yt = fetch_recent_videos(limit=10) or []
    yt_views = sum(int(v.get("views", 0) or 0) for v in recent_yt)
    yt_likes = sum(int(v.get("likes", 0) or 0) for v in recent_yt)

    # Consultar TikTok
    tt_data = fetch_tiktok_overview("gtavihubextra")
    tt_views = int(tt_data.get("views", 0) or 0) if tt_data else 0
    tt_likes = int(tt_data.get("likes", 0) or 0) if tt_data else 0

    # Consultar Instagram
    ig_data = fetch_instagram_overview("gtavihubextra")
    ig_views = int(ig_data.get("views_recent", 0) or 0) if ig_data else 0
    ig_likes = int(ig_data.get("likes_recent", 0) or 0) if ig_data else 0

    # Contador Global Agregado
    total_network_views = yt_views + tt_views + ig_views
    total_network_likes = yt_likes + tt_likes + ig_likes

    tt_block = "🎵 *TIKTOK* (@gtavihubextra)\n"
    if tt_data:
        tt_block += (
            f"• 👥 *Seguidores:* `{tt_data['followers']:,}`\n"
            f"• 👁️ *Vistas Totales (Clips):* `{tt_data['views']:,}`\n"
            f"• ❤️ *Me Gusta Totales:* `{tt_data['likes']:,}`\n"
            f"• 🎬 *Vídeos Públicos:* `{tt_data['videos']}`\n"
        )
        if tt_data.get("recent_videos"):
            tt_block += "\n*Clips destacados en TikTok:*\n"
            for idx, tv in enumerate(tt_data["recent_videos"][:3], 1):
                clean_t = str(tv.get("title", ""))[:38] + "..."
                tt_block += f"  *{idx}.* {clean_t} — `{tv.get('views', 0):,}` vistas | `{tv.get('likes', 0)}` likes\n"
    else:
        tt_block += "• ⚠️ _Perfil público temporalmente no disponible vía web scraper._\n"

    ig_block = "📸 *INSTAGRAM REELS* (@gtavihubextra)\n"
    if ig_data:
        ig_block += (
            f"• 👥 *Seguidores:* `{ig_data['followers']:,}`\n"
            f"• 🎬 *Publicaciones:* `{ig_data['posts']}`\n"
            f"• 👁️ *Vistas Recientes (Reels):* `{ig_data['views_recent']:,}`\n"
            f"• ❤️ *Likes Recientes (Reels):* `{ig_data['likes_recent']:,}`\n"
        )
    else:
        ig_block += "• ⚠️ _Sesión de Instagram no conectada o en espera de actualización._\n"

    # Banner del Contador Global Agregado
    banner = (
        "🌐 *CONTADOR GLOBAL DE AUDIENCIA MULTIPLATAFORMA*\n"
        + ("═" * 40) + "\n\n"
        f"🚀 *TOTAL ACUMULADO EN TODAS LAS REDES:*\n"
        f"• 👁️ *Vistas Totales de Clips:* `{total_network_views:,}`\n"
        f"• ❤️ *Interacciones / Likes Totales:* `{total_network_likes:,}`\n\n"
        f"📊 *Reparto de Vistas por Red:*\n"
        f"  └ 🔴 YouTube Shorts: `{yt_views:,}` vistas ({((yt_views/total_network_views)*100 if total_network_views else 0):.1f}%)\n"
        f"  └ 🎵 TikTok: `{tt_views:,}` vistas ({((tt_views/total_network_views)*100 if total_network_views else 0):.1f}%)\n"
        f"  └ 📸 Instagram Reels: `{ig_views:,}` vistas ({((ig_views/total_network_views)*100 if total_network_views else 0):.1f}%)\n\n"
        + ("═" * 40) + "\n\n"
    )

    combined = (
        f"{banner}"
        f"{yt_report}\n\n"
        + ("═" * 40) + "\n\n"
        f"{tt_block}\n"
        + ("─" * 40) + "\n\n"
        f"{ig_block}\n"
        + ("═" * 40) + "\n"
        "💡 _Monitor centralizado de audiencia unificada (YouTube, TikTok & Reels)._"
    )
    return combined


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

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import BASE_DIR, DATA_DIR, CHANNELS_FILE
from .channels import get_processed_ids, list_monitored_channels, add_monitored_channel

DISCOVERED_CHANNELS_FILE = DATA_DIR / "discovered_channels.json"

DEFAULT_VIRAL_QUERIES = [
    "ytsearch6:GTA 6 Shorts viral",
    "ytsearch6:GTA 6 trailer 2",
    "ytsearch6:GTA 6 filtracion mapa",
    "ytsearch6:GTA 6 gameplay leak",
    "ytsearch6:GTA 6 reaccion streamer",
    "ytsearch6:Grand Theft Auto VI secrets"
]

VIRAL_KEYWORDS = [
    "trailer", "trailer 2", "filtracion", "filtración", "leak", "leaks",
    "mapa", "secretos", "vice city", "lucia", "jason", "gameplay",
    "reaccion", "reacción", "oficial", "official", "fecha", "online",
    "rockstar", "confirmado", "noticia", "exclusiva"
]

def calculate_virality_score(title: str, duration: float, views: int) -> Dict[str, Any]:
    """
    Calcula una puntuación de virabilidad y potencial de engagement (0 a 100):
    1. Volumen de Visualizaciones (0 - 40 pts)
    2. Retención y Formato (0 - 30 pts): Primando Shorts (10s a 60s)
    3. Relevancia Semántica de Palabras Clave (0 - 20 pts)
    4. Factor Extra de Viralidad (0 - 10 pts)
    """
    # 1. Puntos por visualizaciones (0 a 40)
    if views >= 500_000:
        views_score = 40
    elif views >= 200_000:
        views_score = 35
    elif views >= 100_000:
        views_score = 30
    elif views >= 50_000:
        views_score = 25
    elif views >= 20_000:
        views_score = 20
    elif views >= 5_000:
        views_score = 15
    elif views >= 1_000:
        views_score = 10
    else:
        views_score = 5

    # 2. Puntos por formato y retención óptima (0 a 30)
    # Formato Shorts (10s a 65s): retención máxima en feeds verticales
    if 10 <= duration <= 65:
        format_score = 30
    elif 65 < duration <= 180:
        format_score = 18
    elif 180 < duration <= 600:
        format_score = 10
    else:
        format_score = 5

    # 3. Puntos por palabras clave virales en título (0 a 20)
    title_lower = title.lower()
    matches = [kw for kw in VIRAL_KEYWORDS if kw in title_lower]
    keyword_score = min(20, len(matches) * 5)

    # 4. Factor de impulso extra
    bonus = 0
    if "shorts" in title_lower or "#shorts" in title_lower:
        bonus += 5
    if any(k in title_lower for k in ["trailer 2", "filtracion", "leak", "exclusiva"]):
        bonus += 5

    total_score = min(100, views_score + format_score + keyword_score + bonus)

    return {
        "score": total_score,
        "views_score": views_score,
        "format_score": format_score,
        "keyword_score": keyword_score,
        "bonus": bonus,
        "matches": matches,
        "is_short": (0 < duration <= 65)
    }

def scan_viral_radar(
    queries: Optional[List[str]] = None,
    max_candidates: int = 10,
    min_score: int = 40
) -> List[Dict[str, Any]]:
    """
    Escanea dinámicamente YouTube con múltiples queries de alta tendencia,
    descubre nuevos creadores y clasifica los vídeos por puntuación de engagement.
    """
    if queries is None:
        queries = DEFAULT_VIRAL_QUERIES

    processed_ids = get_processed_ids()
    existing_channels = list_monitored_channels()
    existing_urls = {ch.get("url", "").rstrip("/").lower() for ch in existing_channels}
    existing_names = {ch.get("name", "").lower() for ch in existing_channels}

    candidates_by_id: Dict[str, Dict[str, Any]] = {}

    for query in queries:
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(playlist_uploader)s\t%(channel_url)s\t%(webpage_url)s",
                query
            ], capture_output=True, text=True, timeout=25)

            lines = res.stdout.strip().split("\n")
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip()
                    if not vid_id or vid_id in processed_ids or vid_id == "NA":
                        continue

                    # Parsing de duración
                    try:
                        duration = float(parts[2]) if len(parts) > 2 and parts[2] != "NA" else 0.0
                    except ValueError:
                        duration = 0.0

                    # Parsing de vistas
                    try:
                        views = int(parts[3]) if len(parts) > 3 and parts[3] != "NA" else 0
                    except ValueError:
                        views = 0

                    uploader = parts[4].strip() if len(parts) > 4 and parts[4] != "NA" else ""
                    channel_url = parts[5].strip() if len(parts) > 5 and parts[5] != "NA" else ""
                    webpage_url = parts[6].strip() if len(parts) > 6 and parts[6] != "NA" else f"https://www.youtube.com/watch?v={vid_id}"

                    # Si el uploader o el canal no vinieron, estimar o preservar
                    if not uploader:
                        uploader = "Creador YouTube"
                    if not channel_url and uploader:
                        clean_handle = uploader.replace(" ", "")
                        channel_url = f"https://www.youtube.com/@{clean_handle}/videos"

                    score_data = calculate_virality_score(title, duration, views)
                    if score_data["score"] < min_score:
                        continue

                    # Determinar si es un canal nuevo nunca antes monitorizado
                    clean_ch_url = channel_url.rstrip("/").lower()
                    is_new_channel = (
                        clean_ch_url not in existing_urls
                        and uploader.lower() not in existing_names
                    )

                    candidate = {
                        "id": vid_id,
                        "title": title,
                        "url": webpage_url,
                        "duration": duration,
                        "views": views,
                        "uploader": uploader,
                        "channel_url": channel_url,
                        "score": score_data["score"],
                        "is_short": score_data["is_short"],
                        "keywords": score_data["matches"],
                        "is_new_channel": is_new_channel,
                        "query_source": query
                    }

                    if vid_id not in candidates_by_id or score_data["score"] > candidates_by_id[vid_id]["score"]:
                        candidates_by_id[vid_id] = candidate

        except Exception as e:
            print(f"[Viral Discovery] Error escaneando query '{query}': {e}")

    ranked = sorted(candidates_by_id.values(), key=lambda x: x["score"], reverse=True)
    top_candidates = ranked[:max_candidates]

    # Guardar / actualizar registro de canales virales descubiertos
    track_discovered_channels(top_candidates)

    return top_candidates

def track_discovered_channels(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Registra y actualiza el historial de canales virales descubiertos dinámicamente."""
    discovered: Dict[str, Dict[str, Any]] = {}
    if DISCOVERED_CHANNELS_FILE.exists():
        try:
            with open(DISCOVERED_CHANNELS_FILE, "r", encoding="utf-8") as f:
                discovered = json.load(f)
        except Exception:
            discovered = {}

    for c in candidates:
        ch_url = c.get("channel_url")
        if not ch_url:
            continue

        if ch_url not in discovered:
            discovered[ch_url] = {
                "name": c.get("uploader", "Canal Descubierto"),
                "url": ch_url,
                "first_discovered": datetime.now().isoformat(),
                "best_clip_title": c.get("title"),
                "best_clip_views": c.get("views", 0),
                "best_score": c.get("score", 0),
                "occurrences": 1,
                "is_monitored": not c.get("is_new_channel", True)
            }
        else:
            item = discovered[ch_url]
            item["occurrences"] = item.get("occurrences", 1) + 1
            if c.get("score", 0) > item.get("best_score", 0):
                item["best_score"] = c.get("score", 0)
                item["best_clip_title"] = c.get("title")
                item["best_clip_views"] = c.get("views", 0)

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(DISCOVERED_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(discovered, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Viral Discovery] Error guardando discovered_channels: {e}")

    return list(discovered.values())

def auto_register_top_channels(min_score: int = 80, min_occurrences: int = 1) -> List[Dict[str, Any]]:
    """
    Añade automáticamente a channels.json los canales descubiertos que superan
    un listón alto de viralidad y engagement.
    """
    if not DISCOVERED_CHANNELS_FILE.exists():
        return []

    try:
        with open(DISCOVERED_CHANNELS_FILE, "r", encoding="utf-8") as f:
            discovered = json.load(f)
    except Exception:
        return []

    added = []
    for url, data in discovered.items():
        if data.get("is_monitored"):
            continue

        score = data.get("best_score", 0)
        occurrences = data.get("occurrences", 1)
        name = data.get("name", "Canal Viral")

        if score >= min_score and occurrences >= min_occurrences:
            res = add_monitored_channel(url, name=name, lang="en")
            if res.get("success"):
                data["is_monitored"] = True
                added.append(data)

    if added:
        try:
            with open(DISCOVERED_CHANNELS_FILE, "w", encoding="utf-8") as f:
                json.dump(discovered, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return added

def get_viral_radar_summary(top_candidates: Optional[List[Dict[str, Any]]] = None) -> str:
    """Genera un reporte conciso del Radar Viral para Telegram o Consola."""
    if top_candidates is None:
        top_candidates = scan_viral_radar(max_candidates=5)

    if not top_candidates:
        return (
            "🔥 *RADAR VIRAL DE GTA 6*\n"
            + ("═" * 36) + "\n\n"
            + "ℹ️ No se detectaron clips virales por encima del umbral en este momento."
        )

    summary = (
        "🔥 *RADAR VIRAL GTA 6 — MÁXIMO ENGAGEMENT*\n"
        + ("═" * 36) + "\n\n"
    )

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(top_candidates[:5]):
        medal = medals[idx] if idx < len(medals) else "•"
        short_title = item["title"][:48] + ("..." if len(item["title"]) > 48 else "")
        dur_sec = int(item.get("duration", 0))
        dur_str = f"{dur_sec}s (Short 9:16)" if item.get("is_short") else f"{dur_sec // 60}:{dur_sec % 60:02d}m"
        views_str = f"{item.get('views', 0):,}"
        new_tag = " ⭐ *[NUEVO CREADOR]*" if item.get("is_new_channel") else ""

        summary += (
            f"{medal} *[{short_title}]({item['url']})*\n"
            f"   👤 *Canal:* `{item['uploader']}`{new_tag}\n"
            f"   📊 *Score:* `{item['score']}/100` | 👁️ `{views_str}` vistas | ⏱️ `{dur_str}`\n\n"
        )

    summary += (
        ("═" * 36) + "\n"
        "💡 _Pulsa un botón para ingestar el clip o añadir los nuevos creadores._"
    )
    return summary

def print_viral_leaderboard(candidates: List[Dict[str, Any]]):
    """Muestra la tabla de clasificación viral en formato consola CLI."""
    print("\n" + "=" * 70)
    print(" 🔥 RADAR VIRAL GTA 6 — TOP CONTENIDOS DE MÁXIMO ENGAGEMENT")
    print("=" * 70)
    for idx, c in enumerate(candidates, 1):
        tag = "[NUEVO CANAL]" if c.get("is_new_channel") else "[MONITORIZADO]"
        dur = f"{int(c.get('duration', 0))}s" if c.get("is_short") else f"{int(c.get('duration', 0))//60}m"
        print(f" {idx:2d}. [{c['score']:3d}/100] {tag:14s} {c['title'][:42]}")
        print(f"     -> Creador: {c['uploader']} | Vistas: {c.get('views', 0):,} | Duración: {dur}")
        print(f"     -> URL: {c['url']}")
    print("=" * 70 + "\n")

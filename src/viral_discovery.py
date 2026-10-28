import os
import re
import sys
import json
import subprocess
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import BASE_DIR, DATA_DIR, CHANNELS_FILE
from .channels import get_processed_ids, list_monitored_channels, add_monitored_channel

DISCOVERED_CHANNELS_FILE = DATA_DIR / "discovered_channels.json"

DEFAULT_VIRAL_QUERIES = [
    # Gameplay y primeras impresiones post-lanzamiento (mayor volumen de búsqueda actual)
    "ytsearch15:GTA 6 gameplay secrets easter eggs #shorts",
    "ytsearch15:GTA 6 lucia jason funny moments #shorts",
    "ytsearch15:GTA 6 vice city physics fails #shorts",
    "ytsearch15:GTA 6 hidden details leonida #shorts",
    # Análisis técnicos y comparativas — alta retención
    "ytsearch15:GTA 6 graphics comparison real life #shorts",
    "ytsearch15:GTA 6 rage engine water physics #shorts",
    # Noticias, leaks y novedades — alto CTR
    "ytsearch15:GTA 6 new update leak rockstar #shorts",
    "ytsearch15:GTA 6 things you missed #shorts",
    # Español / LatAm — audiencia principal del canal
    "ytsearch15:GTA 6 secretos gameplay vice city #shorts",
    "ytsearch15:GTA 6 detalles ocultos lucia jason #shorts",
]

# Consultas específicas de Gameplay Puro activas a partir del 19 de Noviembre
GAMEPLAY_VIRAL_QUERIES = [
    "ytsearch15:GTA 6 gameplay real mission #shorts",
    "ytsearch15:GTA 6 gameplay espanol momentos #shorts",
    "ytsearch15:GTA 6 gameplay conduccion disparos #shorts",
    "ytsearch15:GTA 6 gameplay mundo abierto detalles #shorts",
    "ytsearch15:GTA 6 gameplay tiroteo policia #shorts",
]

VIRAL_KEYWORDS = [
    # Protagonistas & Personajes Canónicos
    "lucia", "jason", "stefanie", "mud girl", "florida joker", "brian", "hank",
    # Geografía & Lugares de Leonida
    "vice city", "leonida", "port gellhorn", "ocean drive", "keys", "cayos", "vice beach",
    "grassrivers", "everglades", "little haiti", "venetian islands", "starfish island", "escobar",
    # Jugabilidad, Físicas & Motor RAGE 9
    "gameplay", "leak", "leaks", "filtracion", "filtración", "fisicas", "físicas", "physics",
    "graphics", "graficos", "gráficos", "rage 9", "water physics", "interiores", "ia npc",
    "atraco", "armas", "weapon wheel", "saqueo", "animaciones", "rehenes", "gasolinera",
    "deformacion", "deformación", "choque", "accidente", "tiroteo", "gunplay", "cobertura",
    "policia", "policía", "swat", "persecucion", "persecución", "5 estrellas", "helicoptero",
    "helicóptero", "striptease", "discoteca", "maletero",
    # Fauna & Ecosistema Salvaje
    "caiman", "caimán", "cocodrilo", "alligator", "tiburon", "tiburón", "shark", "flamenco",
    # Tráilers, Secretos & Novedades
    "trailer", "trailer 1", "tráiler", "mapa", "secretos", "secreto",
    "easter egg", "detalles", "details", "comparativa", "vida real", "oficial", "official",
    "vercetti", "mansion", "mansión", "barco fantasma", "ovni",
    "fecha", "rockstar", "confirmado", "noticia", "exclusiva", "bombazo"
]

# Palabras clave de creadores y momentos reales (reciben bonus de puntuación)
CREATOR_KEYWORDS = [
    "stream", "directo", "reaccion", "reacción", "clip", "clips", "streamer",
    "jugando", "gameplay", "momento", "fails", "risas", "truco", "mision",
    "misión", "ibai", "xokas", "elxokas", "auron", "rubius", "thegrefg",
    "illojuan", "danirep", "tgg", "mors mutual", "darkviperau", "speedrun",
    "secreto", "easter egg", "misterio", "locura"
]

# Palabras excluidas para garantizar 100% Fair Use, evitar infracciones de Content ID musical
# y filtrar conceptos abstractos/CGI/Unreal Engine hechos por fans que no son clips reales de creadores
EXCLUDED_KEYWORDS = [
    "soundtrack", "ost", "full album", "vevo", "remix song", "cover song",
    "trap beat", "rap beat", "no commentary walkthrough", "full movie",
    "cancion oficial", "canción oficial", "tema musical",
    # Conceptos abstractos / CGI / Fan-made / Unreal Engine / IA / Mods / Fakes / Bucles
    "concept", "concept trailer", "gameplay concept", "fan made", "fan trailer",
    "fan-made", "unreal engine", "ue5", "unreal engine 5", "ai trailer",
    "artificial intelligence", "blender render", "remake concept", "graphics showcase",
    "mod", "mods", "modded", "cinematic edit", "tiktok edit", "fake", "simulated", "ai generated",
    "trailer 2", "tráiler 2", "trailer2", "loop", "bucle"
]

def calculate_virality_score(
    title: str, duration: float, views: int, days_old: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calcula una puntuación de virabilidad y potencial de engagement (0 a 100),
    asegurando cumplimiento estricto de directrices (Fair Use & Anti-Content-ID):
    1. Filtro de Exclusión de Copyright Musical / Contenido Abstracto Fan-Made
    2. Volumen de Visualizaciones (0 - 50 pts) — incluye tiers mega-viral
    3. Retención y Formato Vertical (0 - 35 pts): Primando Shorts (10s a 65s)
    4. Relevancia Semántica de Palabras Clave (0 - 20 pts)
    5. Prioridad a Creadores y Streamers Reales (Bonus 0 - 15 pts)
    6. Velocidad de Crecimiento / Velocity (Bonus 0 - 10 pts)
    """
    title_lower = title.lower()

    # Filtro de seguridad: excluir música comercial, gameplays crudos y conceptos abstractos CGI
    for exc in EXCLUDED_KEYWORDS:
        if exc in title_lower:
            return {
                "score": 0,
                "views_score": 0,
                "format_score": 0,
                "keyword_score": 0,
                "bonus": 0,
                "velocity_bonus": 0,
                "matches": [],
                "is_short": (0 < duration <= 65),
                "excluded_reason": f"Filtro de exclusión activo: '{exc}' (evita música o conceptos abstractos no oficiales)"
            }

    # 1. Puntos por visualizaciones (0 a 50) — tiers mega-viral diferenciados
    if views >= 10_000_000:
        views_score = 50
    elif views >= 5_000_000:
        views_score = 48
    elif views >= 2_000_000:
        views_score = 45
    elif views >= 500_000:
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

    # 2. Puntos por formato Shorts y retención óptima (0 a 35)
    # Formato Shorts nativo (10s a 60s): máxima prioridad editorial en feeds verticales
    if 10 <= duration <= 60:
        format_score = 35
    elif 60 < duration <= 80:
        format_score = 15
    elif 80 < duration <= 180:
        format_score = 5
    else:
        format_score = 0

    # 3. Puntos por palabras clave virales en título (0 a 20)
    matches = [kw for kw in VIRAL_KEYWORDS if kw in title_lower]
    keyword_score = min(20, len(matches) * 5)

    # 4. Factor de impulso extra: Shorts nativos + Contenido jugoso (Trailer, Gameplay, Leaks, Comparativas)
    bonus = 0
    if "shorts" in title_lower or "#shorts" in title_lower:
        bonus += 5

    high_value_gta6 = [
        "trailer", "trailer 1", "tráiler", "gameplay", "leak", "leaks", "filtracion", "filtración",
        "graphics", "graficos", "gráficos", "fisicas", "físicas", "physics", "secreto", "secret", "secretos",
        "easter egg", "lucia", "jason", "stefanie", "mud girl", "florida joker",
        "vice city", "leonida", "port gellhorn", "comparativa", "mapa", "detalles", "details",
        "rage 9", "atraco", "caimán", "cocodrilo", "vida real", "interiores", "ia npc"
    ]
    if any(k in title_lower for k in high_value_gta6):
        bonus += 10

    creator_matches = [ck for ck in CREATOR_KEYWORDS if ck in title_lower]
    if creator_matches:
        bonus = min(15, bonus + 5)

    from .config import is_gameplay_enabled
    if is_gameplay_enabled() and "gameplay" in title_lower:
        bonus = min(20, bonus + 5)

    # 5. Algoritmo de Anticipación y Velocidad (Breakout Detection):
    # Premia desproporcionadamente vídeos recién subidos (<24-48h) con tracción explosiva
    velocity_bonus = 0
    if days_old is not None and views > 0:
        if days_old <= 1:
            # Subido hoy (Día 0/1): Indicativo de viralidad y tendencia inmediata
            if views >= 10_000:
                velocity_bonus = 15  # Breakout inmediato
            elif views >= 2_000:
                velocity_bonus = 10
            elif views >= 500:
                velocity_bonus = 5
        elif days_old > 0:
            vpd = views / days_old
            if vpd >= 100_000:
                velocity_bonus = 12
            elif vpd >= 50_000:
                velocity_bonus = 9
            elif vpd >= 10_000:
                velocity_bonus = 6
            elif vpd >= 1_000:
                velocity_bonus = 4
            elif vpd >= 100:
                velocity_bonus = 2

    total_score = min(100, views_score + format_score + keyword_score + bonus + velocity_bonus)

    return {
        "score": total_score,
        "views_score": views_score,
        "format_score": format_score,
        "keyword_score": keyword_score,
        "bonus": bonus,
        "velocity_bonus": velocity_bonus,
        "matches": list(set(matches + creator_matches)),
        "is_short": (0 < duration <= 65),
        "excluded_reason": None
    }

def scan_viral_radar(
    queries: Optional[List[str]] = None,
    max_candidates: int = 10,
    min_score: int = 55,
    only_shorts: bool = True
) -> List[Dict[str, Any]]:
    """
    Escanea dinámicamente YouTube con múltiples queries de alta tendencia en paralelo,
    descubre nuevos creadores y clasifica los vídeos por puntuación de engagement.
    Incluye velocity score (vistas/día) para priorizar contenido emergente.
    Por defecto prioriza y filtra exclusivamente vídeos en formato Shorts (<= 65s).
    """
    from .channels import is_strictly_gta6

    if queries is None:
        from .config import is_gameplay_enabled
        queries = list(DEFAULT_VIRAL_QUERIES)
        if is_gameplay_enabled():
            queries.extend(GAMEPLAY_VIRAL_QUERIES)

    processed_ids = get_processed_ids()
    existing_channels = list_monitored_channels()
    existing_urls = {ch.get("url", "").rstrip("/").lower() for ch in existing_channels}
    existing_names = {ch.get("name", "").lower() for ch in existing_channels}

    def _fetch_single_query(query: str) -> List[Dict[str, Any]]:
        """Ejecuta una query yt-dlp y devuelve candidatos ya filtrados y puntuados."""
        results = []
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(uploader)s\t%(channel_url)s\t%(webpage_url)s\t%(upload_date)s",
                query
            ], capture_output=True, text=True, timeout=30)

            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                vid_id = parts[0].strip()
                title = parts[1].strip()
                if not vid_id or vid_id in processed_ids or vid_id == "NA":
                    continue

                # FILTRO INNEGOCIABLE DE EXCLUSIVIDAD GTA 6
                if not is_strictly_gta6(title):
                    continue

                try:
                    duration = float(parts[2]) if len(parts) > 2 and parts[2] not in ("NA", "") else 0.0
                except ValueError:
                    duration = 0.0

                if only_shorts and (duration > 65 or duration <= 0):
                    continue

                try:
                    views = int(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0
                except ValueError:
                    views = 0

                uploader = parts[4].strip() if len(parts) > 4 and parts[4] not in ("NA", "") else ""
                channel_url = parts[5].strip() if len(parts) > 5 and parts[5] not in ("NA", "") else ""
                webpage_url = parts[6].strip() if len(parts) > 6 and parts[6] not in ("NA", "") else f"https://www.youtube.com/watch?v={vid_id}"

                # Calcular antigüedad del vídeo para velocity score
                days_old = None
                raw_date = parts[7].strip() if len(parts) > 7 and parts[7] not in ("NA", "") else ""
                if raw_date and len(raw_date) == 8:
                    try:
                        upload_dt = datetime.strptime(raw_date, "%Y%m%d")
                        days_old = max(1, (datetime.now() - upload_dt).days)
                    except ValueError:
                        pass

                if not uploader:
                    uploader = "Creador YouTube"
                if not channel_url and uploader:
                    clean_handle = re.sub(r'[^\w.-]', '', uploader.replace(' ', ''))
                    channel_url = f"https://www.youtube.com/@{clean_handle}"

                score_data = calculate_virality_score(title, duration, views, days_old=days_old)
                if score_data["score"] < min_score:
                    continue

                clean_ch_url = channel_url.rstrip("/").lower()
                is_new_channel = (
                    clean_ch_url not in existing_urls
                    and uploader.lower() not in existing_names
                )

                velocity = round(views / days_old, 1) if days_old and days_old > 0 else None

                results.append({
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
                    "query_source": query,
                    "days_old": days_old,
                    "velocity": velocity,
                })
        except Exception as e:
            print(f"[Viral Discovery] Error escaneando query '{query}': {e}")
        return results

    candidates_by_id: Dict[str, Dict[str, Any]] = {}

    # Ejecutar todas las queries en paralelo (máx 3 workers para respetar CPU/GaTDSEQ)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_single_query, q): q for q in queries}
        for future in concurrent.futures.as_completed(futures):
            for candidate in future.result():
                vid_id = candidate["id"]
                if vid_id not in candidates_by_id or candidate["score"] > candidates_by_id[vid_id]["score"]:
                    candidates_by_id[vid_id] = candidate

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

def auto_register_top_channels(min_score: int = 80, min_occurrences: int = 2) -> List[Dict[str, Any]]:
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

        ch_url = item.get("channel_url") or item.get("url")
        velocity = item.get("velocity")
        vpd_str = f" | ⚡ `{velocity:,.0f} v/día`" if velocity and velocity >= 100 else ""
        summary += (
            f"{medal} *[{short_title}]({item['url']})*\n"
            f"   👤 *Canal:* [{item['uploader']}]({ch_url}){new_tag}\n"
            f"   📊 *Score:* `{item['score']}/100` | 👁️ `{views_str}` vistas | ⏱️ `{dur_str}`{vpd_str}\n\n"
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
        vpd = f" | {c['velocity']:,.0f} v/día" if c.get("velocity") else ""
        print(f"     -> Creador: {c['uploader']} | Vistas: {c.get('views', 0):,} | Duración: {dur}{vpd}")
        print(f"     -> URL: {c['url']}")
    print("=" * 70 + "\n")

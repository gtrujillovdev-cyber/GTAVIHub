import sys
import re
import json
import subprocess
import concurrent.futures
from typing import List, Dict, Any, Optional
from .config import CHANNELS_FILE, PROCESSED_FILE

GTA6_POSITIVE_KEYWORDS = [
    "gta 6", "gta6", "gta vi", "gtavi",
    "grand theft auto 6", "grand theft auto vi",
    "vice city", "leonida", "lucia", "jason",
    "port gellhorn", "mud girl", "rage 9"
]

def is_strictly_gta6(title: str, description: str = "") -> bool:
    """
    Verifica de forma estricta e innegociable que el contenido trata EXCLUSIVAMENTE
    sobre Grand Theft Auto VI (GTA 6).
    Rechaza tajantemente GTA 5, GTA Online, GTA 4 o cualquier contenido que no sea de GTA 6.
    """
    combined = f" {title} {description} ".lower()

    # 1. Requiere mención explícita a GTA 6 / GTA VI o sus elementos canónicos exclusivos
    has_gta6 = any(
        re.search(r"(?:\b|_)" + re.escape(term) + r"(?:\b|_)", combined)
        for term in GTA6_POSITIVE_KEYWORDS
    )
    if not has_gta6:
        return False

    title_lower = title.lower()

    # 2. Descalificadores absolutos: si menciona GTA 5, GTA V, GTA Online, GTA 4, etc.,
    # se descarta tajantemente para evitar gameplays antiguos o clickbait de GTA 5.
    # Usamos \b para que 'gta v' NO coincida por error con 'gta vi'.
    old_game_regexes = [
        r"\bgta\s*5\b",
        r"\bgta\s*v\b",
        r"\bgta\s*online\b",
        r"\bgta\s*4\b",
        r"\bgta\s*iv\b",
        r"\bgta\s*3\b",
        r"\bgta\s*iii\b",
        r"\bsan andreas\b",
        r"\bweekly update\b",
        r"\bcareer progress\b",
        r"\bcara a cara\b",
        r"\bparkour\b",
        r"\bmega ramp\b",
        r"\bcayo perico\b",
        r"\bshark card\b"
    ]
    for pattern in old_game_regexes:
        if re.search(pattern, title_lower):
            return False

    # 3. Filtro Anti-Fake, Anti-IA y Anti-Conceptos (CERO CONTENIDO FALSO O FAN-MADE):
    # GTA 6 está lanzado; existe gameplay real. Se descarta solo contenido CGI/fan-made/IA generativa,
    # no términos técnicos legítimos como "AI NPC", "IA del juego" o "render distance".
    fake_ai_regexes = [
        r"\bconcept\b",
        r"\bconcept\s*trailer\b",
        r"\bfan\s*made\b",
        r"\bfanmade\b",
        r"\bfan\s*trailer\b",
        r"\bunreal\b",
        r"\bue5\b",
        r"\bunreal\s*engine\b",
        r"\bai\s+generated\b",
        r"\bai\s+trailer\b",
        r"\bai\s+concept\b",
        r"\bia\s+generada\b",
        r"\btrailer\s+de\s+ia\b",
        r"\bmod\b",
        r"\bmods\b",
        r"\bmodded\b",
        r"\bmodding\b",
        r"\bcinematic\s*edit\b",
        r"\btiktok\s*edit\b",
        r"\bcgi\b",
        r"\bblender\b",
        r"\b(?:3d|blender|cgi)\s*render\b",
        r"\bfake\b",
        r"\bsimulated\b",
        r"\btrailer\s*2\b",
        r"\btráiler\s*2\b",
        r"\bloop\b",
        r"\bbucle\b"
    ]
    for pattern in fake_ai_regexes:
        if re.search(pattern, title_lower):
            return False

    return True

# Alias para retrocompatibilidad
is_strictly_gta = is_strictly_gta6

def get_processed_ids() -> set:
    if not PROCESSED_FILE.exists():
        return set()
    try:
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {entry.get("id") for entry in data if "id" in entry}
    except Exception as e:
        print(f"[Warning] Error reading {PROCESSED_FILE}: {e}")
        return set()

def mark_video_processed(entry: Dict[str, Any]):
    processed = []
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                processed = json.load(f)
        except Exception:
            processed = []
    processed.append(entry)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

def fetch_channel_candidates(max_per_channel: int = 2) -> List[Dict[str, Any]]:
    from .viral_discovery import calculate_virality_score

    if not CHANNELS_FILE.exists():
        return []

    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    processed_ids = get_processed_ids()
    candidates_by_id: Dict[str, Dict[str, Any]] = {}

    def _scan_channel(ch: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not ch.get("enabled", True):
            return []
        url = ch.get("url")
        results = []
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(url)s",
                "-I", f"1:{max_per_channel}",
                url
            ], capture_output=True, text=True, check=True, timeout=25)

            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip()
                    duration = parts[2] if len(parts) > 2 else "0"
                    try:
                        views = int(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0
                    except ValueError:
                        views = 0
                    vid_url = parts[4] if len(parts) > 4 else f"https://www.youtube.com/watch?v={vid_id}"

                    if vid_id and vid_id not in processed_ids and vid_id != "NA":
                        # FILTRO INNEGOCIABLE DE CONTENIDO EXCLUSIVO GTA 6:
                        is_official = ("rockstargames" in url.lower() or ch.get("type") == "official")
                        if not is_official and not is_strictly_gta6(title):
                            continue

                        try:
                            dur_secs = float(duration) if duration and duration != "NA" else 0.0
                        except ValueError:
                            dur_secs = 0.0

                        # FILTRO ESTRICTO DE SHORTS REALES (CERO VÍDEOS LARGOS RECORTADOS):
                        # Salvo tráilers oficiales, solo se admiten clips concebidos como Shorts nativos (<= 65s)
                        if not is_official and (dur_secs > 65 or dur_secs <= 0):
                            continue

                        score_data = calculate_virality_score(title, dur_secs, views)

                        results.append({
                            "id": vid_id,
                            "title": title,
                            "url": vid_url,
                            "duration": dur_secs,
                            "views": views,
                            "score": score_data["score"],
                            "source_name": ch.get("name"),
                            "source_type": ch.get("type", "general"),
                            "lang": ch.get("lang", "en"),
                            "is_short": (0 < dur_secs <= 60)
                        })
        except Exception as e:
            print(f"[!] Error escaneando canal {ch.get('name', url)}: {e}")
        return results

    def _scan_query(q: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not q.get("enabled", False):
            return []
        query = q.get("query")
        results = []
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(url)s",
                query
            ], capture_output=True, text=True, check=True, timeout=25)

            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip()
                    duration = parts[2] if len(parts) > 2 else "0"
                    try:
                        views = int(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0
                    except ValueError:
                        views = 0
                    vid_url = parts[4] if len(parts) > 4 else f"https://www.youtube.com/watch?v={vid_id}"

                    if vid_id and vid_id not in processed_ids and vid_id != "NA":
                        if not is_strictly_gta6(title):
                            continue
                        try:
                            dur_secs = float(duration) if duration and duration != "NA" else 0.0
                        except ValueError:
                            dur_secs = 0.0

                        # Si la query exige solo formato Shorts, filtrar vídeos largos (>65s)
                        if q.get("only_shorts", True) and (dur_secs > 65 or dur_secs <= 0):
                            continue

                        score_data = calculate_virality_score(title, dur_secs, views)

                        results.append({
                            "id": vid_id,
                            "title": title,
                            "url": vid_url,
                            "duration": dur_secs,
                            "views": views,
                            "score": score_data["score"],
                            "source_name": f"Search: {query.split(':')[1] if ':' in query else query}",
                            "source_type": "viral_search",
                            "lang": q.get("lang", "es"),
                            "is_short": (0 < dur_secs <= 60)
                        })
        except Exception as e:
            print(f"[!] Error en query {query}: {e}")
        return results

    # 1. Target Channels en paralelo (máx 3 workers para no saturar GaTDSEQ)
    target_channels = [ch for ch in config.get("channels", []) if ch.get("enabled", True)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_scan_channel, ch): ch for ch in target_channels}
        for future in concurrent.futures.as_completed(futures):
            for cand in future.result():
                vid_id = cand["id"]
                if vid_id not in candidates_by_id or cand["score"] > candidates_by_id[vid_id]["score"]:
                    candidates_by_id[vid_id] = cand

    # 2. Search queries en paralelo (máx 3 workers)
    from .config import is_gameplay_enabled
    from datetime import datetime

    def _is_query_active(q: Dict[str, Any]) -> bool:
        active_after = q.get("active_after")
        if active_after:
            if is_gameplay_enabled():
                return True
            try:
                if datetime.now() >= datetime.fromisoformat(active_after):
                    return True
            except Exception:
                pass
            return False
        return q.get("enabled", False)

    active_queries = [q for q in config.get("search_queries", []) if _is_query_active(q)]
    if active_queries:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_scan_query, q): q for q in active_queries}
            for future in concurrent.futures.as_completed(futures):
                for cand in future.result():
                    vid_id = cand["id"]
                    if vid_id not in candidates_by_id or cand["score"] > candidates_by_id[vid_id]["score"]:
                        candidates_by_id[vid_id] = cand

    candidates = list(candidates_by_id.values())
    # Ordenar por score descendente; Shorts tienen prioridad en caso de empate
    candidates.sort(key=lambda x: (-x.get("score", 0), not x.get("is_short", False)))

    return candidates

def list_monitored_channels() -> List[Dict[str, Any]]:
    """Devuelve la lista actual de canales en channels.json."""
    if not CHANNELS_FILE.exists():
        return []
    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("channels", [])
    except Exception:
        return []

def save_channels_config(config: Dict[str, Any]) -> bool:
    """Guarda la configuración actualizada en channels.json."""
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Channels] Error guardando {CHANNELS_FILE}: {e}")
        return False

def add_monitored_channel(url: str, name: str = "", lang: str = "en") -> Dict[str, Any]:
    """Añade un nuevo canal a channels.json."""
    config = {"channels": [], "search_queries": []}
    if CHANNELS_FILE.exists():
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    clean_url = url.strip()
    if not clean_url.endswith("/videos") and ("youtube.com/@" in clean_url or "youtube.com/channel/" in clean_url):
        clean_url = clean_url.rstrip("/") + "/videos"

    for ch in config.get("channels", []):
        if ch.get("url") == clean_url:
            return {"success": False, "message": f"El canal ya estaba registrado como '{ch.get('name')}'."}

    channel_name = name.strip() if name else ""
    if not channel_name:
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--print", "%(uploader)s",
                clean_url
            ], capture_output=True, text=True, timeout=12)
            first_line = res.stdout.strip().split("\n")[0]
            if first_line:
                channel_name = first_line
        except Exception:
            pass
    if not channel_name:
        channel_name = clean_url.split("/")[-2] if "/videos" in clean_url else clean_url.split("/")[-1]

    new_channel = {
        "name": channel_name,
        "url": clean_url,
        "type": "custom",
        "lang": lang,
        "filter_keywords": False,
        "enabled": True,
        "description": "Añadido desde Telegram Bot"
    }
    config.setdefault("channels", []).append(new_channel)
    save_channels_config(config)
    return {"success": True, "channel": new_channel}

def remove_monitored_channel(identifier: str) -> bool:
    """Elimina un canal por índice numérico (1-based) o nombre/URL."""
    if not CHANNELS_FILE.exists():
        return False
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    channels = config.get("channels", [])
    initial_len = len(channels)

    if identifier.strip().isdigit():
        idx = int(identifier.strip()) - 1
        if 0 <= idx < len(channels):
            channels.pop(idx)
    else:
        ident_lower = identifier.lower().strip()
        channels = [
            ch for ch in channels
            if ident_lower not in ch.get("name", "").lower() and ident_lower not in ch.get("url", "").lower()
        ]

    if len(channels) < initial_len:
        config["channels"] = channels
        save_channels_config(config)
        return True
    return False

def toggle_channel_enabled(index: int) -> Optional[bool]:
    """Invierte el estado de activación (enabled: True/False) de un canal."""
    if not CHANNELS_FILE.exists():
        return None
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    channels = config.get("channels", [])
    if 0 <= index < len(channels):
        channels[index]["enabled"] = not channels[index].get("enabled", True)
        config["channels"] = channels
        save_channels_config(config)
        return channels[index]["enabled"]
    return None

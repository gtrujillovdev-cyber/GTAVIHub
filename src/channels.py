import sys
import re
import json
import subprocess
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Any, Optional
from .config import CHANNELS_FILE, PROCESSED_FILE

GTA6_POSITIVE_KEYWORDS = [
    "gta 6", "gta6", "gta vi", "gtavi",
    "grand theft auto 6", "grand theft auto vi",
    "leonida", "port gellhorn", "vice beach", "rage 9", "mud girl", "florida joker"
]

def is_strictly_gta6(title: str, description: str = "") -> bool:
    """
    Verifica de forma estricta, matemática e innegociable que el contenido trata EXCLUSIVAMENTE
    sobre Grand Theft Auto VI (GTA 6).
    Rechaza tajantemente GTA 5, GTA Online, GTA 4, Red Dead Redemption, Fortnite,
    Call of Duty o cualquier otro juego o noticia que no sea estrictamente de GTA 6.
    """
    combined = f" {title} {description} ".lower()
    title_lower = title.lower()

    # 1. Requiere mención explícita a GTA 6 / GTA VI o sus elementos canónicos exclusivos
    has_gta6 = any(
        re.search(r"(?:\b|_)" + re.escape(term) + r"(?:\b|_)", combined)
        for term in GTA6_POSITIVE_KEYWORDS
    )

    # Soporte para protagonistas duales canónicos (Lucía & Jason juntos)
    if not has_gta6:
        if re.search(r"\b(?:lucia\s+(?:y|and|&)\s+jason|jason\s+(?:y|and|&)\s+lucia)\b", combined):
            has_gta6 = True

    # Soporte para protagonista individual (Lucía o Jason) ÚNICAMENTE con contexto explícito de GTA/Rockstar/Vice City
    if not has_gta6:
        has_protagonist = bool(re.search(r"\b(?:lucia|jason)\b", combined))
        has_gta_context = bool(re.search(r"\b(?:gta|rockstar|vice\s*city|trailer|leak|filtraci[oó]n)\b", combined))
        is_non_gta_person = bool(re.search(r"\b(?:jason\s*schreier|jason\s*blum|jason\s*voorhees|lucia\s*de\s*la\s*puerta|lucia\s*bellido)\b", combined))
        if has_protagonist and has_gta_context and not is_non_gta_person:
            has_gta6 = True

    if not has_gta6:
        return False

    # 2. Descalificadores absolutos de otras franquicias ajenas a GTA 6
    unrelated_franchises = [
        r"\bred\s*dead\b", r"\brdr\b", r"\brdr2\b", r"\brdr1\b", r"\bbully\b", r"\bmax\s*payne\b",
        r"\bmidnight\s*club\b", r"\bcircoloco\b", r"\bla\s*noire\b", r"\bmanhunt\b",
        r"\bfortnite\b", r"\bcall\s*of\s*duty\b", r"\bwarzone\b", r"\bminecraft\b",
        r"\bcyberpunk\b", r"\belden\s*ring\b", r"\broblox\b", r"\beafc\b", r"\bfifa\b",
        r"\bvalorant\b", r"\bleague\s*of\s*legends\b", r"\bassassin'?s\s*creed\b",
        r"\bspider-?man\b", r"\bwolverine\b", r"\bstar\s*field\b", r"\bhalo\b",
        r"\bresident\s*evil\b", r"\bsilent\s*hill\b", r"\bblack\s*myth\b", r"\bwukong\b",
        r"\bmonster\s*hunter\b", r"\bzelda\b", r"\bmario\b", r"\bpokemon\b", r"\bpokémon\b"
    ]
    for pattern in unrelated_franchises:
        if re.search(pattern, title_lower):
            # Solo permitir si es una comparación técnica explícita con GTA 6
            if not re.search(r"\b(?:vs|versus|comparativa|comparison|diferencias)\b", title_lower):
                return False

    # 3. Descalificadores absolutos de entregas anteriores de GTA (GTA 5, GTA Online, GTA 4, San Andreas, etc.)
    old_game_regexes = [
        r"\bgta\s*5\b",
        r"\bgta\s*v\b",
        r"\bgta\s*online\b",
        r"\bgta\s*4\b",
        r"\bgta\s*iv\b",
        r"\bgta\s*3\b",
        r"\bgta\s*iii\b",
        r"\bsan\s*andreas\b",
        r"\bdefinitive\s*edition\b",
        r"\bthe\s*definitive\s*edition\b",
        r"\btrilogy\b",
        r"\bremaster\b",
        r"\bremastered\b",
        r"\bvice\s*city\s*stories\b",
        r"\bliberty\s*city\s*stories\b",
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
            # Permitir únicamente comparaciones explícitas de evolución gráfica/físicas con GTA 6
            is_comparison = bool(
                re.search(r"\b(?:vs|versus|comparativa|comparison|diferencias|evolucion|evolution)\b", title_lower)
                and re.search(r"\b(?:gta\s*6|gta6|gta\s*vi|gtavi)\b", title_lower)
            )
            if not is_comparison:
                return False

    # Si menciona 'vice city' pero no menciona explícitamente '6' o 'vi', es del juego antiguo
    if re.search(r"\bvice\s*city\b", title_lower) and not re.search(r"\b(?:gta\s*6|gta6|gta\s*vi|gtavi)\b", title_lower):
        return False

    # 4. Filtro Anti-Fake, Anti-IA y Anti-Conceptos (CERO CONTENIDO FALSO O FAN-MADE):
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
        ch_name = ch.get("name", "Canal")
        results = []
        
        # Si la URL de /shorts falla, fallback a búsqueda de los vídeos del creador
        urls_to_try = [url]
        if "/shorts" in url or ch.get("type") in ("streamer", "spanish_streamer", "analyst"):
            urls_to_try.append(f"ytsearch5:{ch_name} GTA 6 #shorts")

        res_stdout = ""
        for u in urls_to_try:
            try:
                res = subprocess.run([
                    sys.executable, "-m", "yt_dlp",
                    "--impersonate", "chrome",
                    "--no-check-certificates",
                    "--flat-playlist",
                    "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s\t%(url)s\t%(upload_date)s",
                    "-I", f"1:{max_per_channel * 2}",
                    u
                ], capture_output=True, text=True, check=True, timeout=25)
                res_stdout = res.stdout
                if res_stdout.strip():
                    break
            except Exception:
                continue

        if not res_stdout.strip():
            return []

        for line in res_stdout.strip().split("\n"):
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
                try:
                    like_count = int(parts[4]) if len(parts) > 4 and parts[4] not in ("NA", "") else None
                except ValueError:
                    like_count = None
                vid_url = parts[5] if len(parts) > 5 else f"https://www.youtube.com/watch?v={vid_id}"
                up_date = parts[6].strip() if len(parts) > 6 else ""

                if vid_id and vid_id not in processed_ids and vid_id != "NA":
                    # FILTRO DE FRESCURA TEMPORAL: Descartar vídeos con más de 30 días de antigüedad
                    days_old = None
                    if up_date and up_date.isdigit() and len(up_date) == 8:
                        try:
                            age_days = (datetime.now() - datetime.strptime(up_date, "%Y%m%d")).days
                            if age_days > 30:
                                continue
                            days_old = max(1, age_days)
                        except Exception:
                            pass
                    # FILTRO INNEGOCIABLE DE CONTENIDO EXCLUSIVO GTA 6:
                    # Ni siquiera los canales oficiales pueden colar contenido ajeno (como RDR o GTA Online).
                    if not is_strictly_gta6(title):
                        continue
                    is_official = ("rockstargames" in url.lower() or ch.get("type") == "official")

                    try:
                        dur_secs = float(duration) if duration and duration != "NA" else 0.0
                    except ValueError:
                        dur_secs = 0.0

                    # FILTRO ESTRICTO DE SHORTS REALES (CERO VÍDEOS LARGOS RECORTADOS):
                    # Salvo tráilers oficiales, solo se admiten clips concebidos como Shorts nativos (12s a 65s)
                    if not is_official and (dur_secs > 65 or dur_secs < 12):
                        continue

                    score_data = calculate_virality_score(title, dur_secs, views, days_old=days_old, like_count=like_count)
                    velocity = score_data.get("velocity_vpd")

                    results.append({
                        "id": vid_id,
                        "title": title,
                        "url": vid_url,
                        "duration": dur_secs,
                        "views": views,
                        "like_count": like_count,
                        "days_old": days_old,
                        "velocity": velocity,
                        "score": score_data["score"],
                        "source_name": ch_name,
                        "source_type": ch.get("type", "general"),
                        "lang": ch.get("lang", "es"),
                        "is_short": (0 < dur_secs <= 60),
                        "source_count": 1,
                    })
        return results

    def _scan_query(q: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not q.get("enabled", False):
            return []
        query = q.get("query", "")
        results = []
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s\t%(url)s\t%(upload_date)s",
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
                    try:
                        like_count = int(parts[4]) if len(parts) > 4 and parts[4] not in ("NA", "") else None
                    except ValueError:
                        like_count = None
                    vid_url = parts[5] if len(parts) > 5 else f"https://www.youtube.com/watch?v={vid_id}"
                    up_date = parts[6].strip() if len(parts) > 6 else ""

                    if vid_id and vid_id not in processed_ids and vid_id != "NA":
                        # FILTRO DE FRESCURA TEMPORAL: Descartar vídeos con más de 30 días de antigüedad
                        days_old = None
                        if up_date and up_date.isdigit() and len(up_date) == 8:
                            try:
                                age_days = (datetime.now() - datetime.strptime(up_date, "%Y%m%d")).days
                                if age_days > 30:
                                    continue
                                days_old = max(1, age_days)
                            except Exception:
                                pass

                        if not is_strictly_gta6(title):
                            continue
                        try:
                            dur_secs = float(duration) if duration and duration != "NA" else 0.0
                        except ValueError:
                            dur_secs = 0.0

                        # Si la query exige solo formato Shorts, filtrar vídeos largos (>65s) o fragmentos diminutos (<12s)
                        if q.get("only_shorts", True) and (dur_secs > 65 or dur_secs < 12):
                            continue

                        score_data = calculate_virality_score(title, dur_secs, views, days_old=days_old, like_count=like_count)
                        velocity = score_data.get("velocity_vpd")

                        results.append({
                            "id": vid_id,
                            "title": title,
                            "url": vid_url,
                            "duration": dur_secs,
                            "views": views,
                            "like_count": like_count,
                            "days_old": days_old,
                            "velocity": velocity,
                            "score": score_data["score"],
                            "source_name": f"Search: {query.split(':')[1] if ':' in query else query}",
                            "source_type": "viral_search",
                            "lang": q.get("lang", "es"),
                            "is_short": (0 < dur_secs <= 60),
                            "source_count": 1,
                        })
        except Exception as e:
            print(f"[!] Error en query {query}: {e}")
        return results

    def _merge_candidate(cand: Dict[str, Any]):
        """Inserta o actualiza un candidato aplicando cross-source bonus si aparece en múltiples fuentes."""
        vid_id = cand["id"]
        if vid_id not in candidates_by_id:
            cand["source_count"] = 1
            candidates_by_id[vid_id] = cand
        else:
            existing = candidates_by_id[vid_id]
            existing["source_count"] = existing.get("source_count", 1) + 1
            existing["score"] = min(100, existing["score"] + 5)  # +5 pts por cada fuente extra
            if cand["score"] > existing["score"]:
                cand["source_count"] = existing["source_count"]
                candidates_by_id[vid_id] = cand

    # 1. Target Channels en paralelo (máx 3 workers para no saturar GaTDSEQ)
    target_channels = [ch for ch in config.get("channels", []) if ch.get("enabled", True)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_scan_channel, ch): ch for ch in target_channels}
        for future in concurrent.futures.as_completed(futures):
            for cand in future.result():
                _merge_candidate(cand)

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
                    _merge_candidate(cand)

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

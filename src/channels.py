import sys
import re
import json
import difflib
import subprocess
import concurrent.futures
from urllib.parse import quote_plus
from datetime import datetime
from typing import List, Dict, Any, Optional
from .config import CHANNELS_FILE, PROCESSED_FILE, DATA_DIR

GTA6_POSITIVE_KEYWORDS = [
    "gta 6", "gta6", "gta vi", "gtavi",
    "grand theft auto 6", "grand theft auto vi",
    "leonida", "port gellhorn", "vice beach", "rage 9", "mud girl", "florida joker"
]

# ── Filtro Anti-Oficial: el canal es para contenido EXTRA, no para copiar tráilers ──
_OFFICIAL_UPLOADERS = {
    "rockstar games", "rockstar games (oficial)", "rockstar games españa", "rockstar games japan",
    "rockstar games france", "rockstar games germany", "rockstar games brazil",
    "rockstar games uk", "rockstar games italia", "take-two interactive",
}

_OFFICIAL_REUPLOAD_PATTERNS = [
    r"^grand theft auto\s*(?:vi|6)\s*[:\-–|]?\s*(?:gameplay\s*)?trailer(?:\s*\d+)?[\s!🔥🤯]*$",
    r"^grand theft auto\s*(?:vi|6)\s*[:\-–|]?\s*official",
    r"^grand theft auto\s*(?:vi|6)\s*[:\-–|]?\s*(?:cover\s*art|key\s*art)",
    r"^gta\s*(?:6|vi)\s*[:\-–|]?\s*(?:gameplay\s*)?trailer(?:\s*\d+)?[\s!🔥🤯]*$",
    r"^gta\s*(?:6|vi)\s*[:\-–|]?\s*official",
    r"^gta\s*(?:6|vi)\s*[:\-–|]?\s*(?:cover\s*art|key\s*art)",
    r"^grand theft auto\s*(?:vi|6)\s*[:\-–|]?\s*(?:tráiler|trailer)\s*(?:de\s*lanzamiento|oficial)",
]

def is_official_or_reupload(title: str, uploader: str = "") -> bool:
    """Devuelve True si el contenido es oficial de Rockstar o un reupload puro de tráiler/arte.
    El canal GTA VI Hub Spain es para contenido EXTRA (análisis, secretos, físicas),
    no para copiar tráilers oficiales que ya tienen millones de vistas en el canal original."""
    if uploader.strip().lower() in _OFFICIAL_UPLOADERS:
        return True
    title_clean = title.strip().lower()
    for pattern in _OFFICIAL_REUPLOAD_PATTERNS:
        if re.match(pattern, title_clean):
            return True
    return False


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
                re.search(r"\b(?:vs|versus|comparativa|comparan|comparar|comparaci[oó]n|comparison|diferencias|evoluci[oó]n|evolution)\b", title_lower)
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
        r"\btrailer\s*1\b",
        r"\btráiler\s*1\b",
        r"\bprimer\s*trailer\b",
        r"\bprimer\s*tráiler\b",
        r"\bfirst\s*trailer\b",
        r"\bofficial\s*trailer\s*1\b",
        r"\btráiler\s*oficial\s*1\b",
        r"\bgameplay\s*filtrado\s*\(menu",
        r"\bloop\b",
        r"\bbucle\b"
    ]
    for pattern in fake_ai_regexes:
        if re.search(pattern, title_lower):
            return False

    # 5. Descalificador estricto de idiomas no soportados (Portugués, Holandés, Alemán, Ruso, etc.)
    # El canal opera exclusivamente para la comunidad hispanohablante (fuentes ES o EN)
    non_target_lang_markers = [
        r"\bvoc[eê]\b", r"\bn[aã]o\b", r"\bjogando\b", r"\bdublado\b",
        r"\bolha\b", r"\bgalera\b", r"\bjogos\b",
        r"\blan[cç]amento\b", r"\bcomente\b", r"\bcurte\b", r"\bdeixa\s*o\s*like\b",
        r"\bportugu[eê]s\b", r"\bbrasileiro\b", r"\bbrasil\b", r"\bmuito\b",
        r"\bnederland\b", r"\blaunchtrailer\b", r"\bdeutschland\b", r"\bdeutsch\b",
        r"\bfrançais\b", r"\bfrance\b", r"\bitaliano\b", r"\bitalia\b", r"[\u0400-\u04FF]"
    ]
    for pattern in non_target_lang_markers:
        if re.search(pattern, combined):
            return False

    # 6. Descalificador Absoluto de Parodias, Memes, Mors Mutual y Contenido de GTA 5
    parody_blacklist_regexes = [
        r"\bmors\s*mutual\b",
        r"\bsouth\s*park\b",
        r"\bsouthpark\b",
        r"\bparodia\b",
        r"\bparody\b",
        r"\bpar[oó]dia\b",
        r"\bsatira\b",
        r"\bs[aá]tira\b",
        r"\bsketch\b",
        r"\bmeme\b",
        r"\bmemes\b",
        r"\bbroma\b",
        r"\bchiste\b",
        r"\bfivem\b",
        r"\bgtao\b",
        r"\bgta\s*online\b"
    ]
    for pattern in parody_blacklist_regexes:
        if re.search(pattern, combined):
            return False

    # 7. Descalificador de Publicidad Corporativa, Mandos y Merchandising (CERO ANUNCIOS):
    merch_ad_regexes = [
        r"\bcontroller\b",
        r"\bcontrollers\b",
        r"\bdualsense\b",
        r"\bmando\b",
        r"\bmandos\b",
        r"\bcustom\s*controller\b",
        r"\bunboxing\b",
        r"\bmerch\b",
        r"\bmerchandise\b",
        r"\bmerchandising\b",
        r"\bcamiseta\b",
        r"\bt-shirt\b",
        r"\bhoodie\b",
        r"\bskin\b",
        r"\bskins\b",
        r"\bcase\b",
        r"\bfaceplate\b",
        r"\bconsole\s*cover\b",
        r"\bposter\b",
        r"\bfigura\b",
        r"\bfigure\b",
        r"\bstatue\b",
        r"\bcollectors\s*edition\b"
    ]
    for pattern in merch_ad_regexes:
        if re.search(pattern, combined):
            return False

    # 8. Descalificador Estricto de Talking-Heads, Tertulias, Podcasts y Cháchara sin Gameplay (Anti-Bocachanclas)
    talking_head_regexes = [
        r"\bpodcast\b",
        r"\bentrevista\b",
        r"\binterview\b",
        r"\bex[- ](?:rockstar|empleado|animador|developer|dev)\b",
        r"\bse pronuncia\b",
        r"\bdeclaraciones\b",
        r"\bcomunicado\b",
        r"\bhabla sobre\b",
        r"\bdespido[s]?\b",
        r"\bopinion\b",
        r"\bopinión\b",
        r"\bopinando\b",
        r"\bcharlas\b",
        r"\bcharla\b",
        r"\bvideo[- ]ensayo\b",
        r"\bvideo\s*essay\b",
        r"\btertulia\b",
        r"\bdebate\b",
        r"\bhablando\b",
        r"\bfacecam\b",
        r"\breactor\b"
    ]
    for pattern in talking_head_regexes:
        if re.search(pattern, combined):
            return False

    return True

# Alias para retrocompatibilidad
is_strictly_gta = is_strictly_gta6

def get_daily_published_count() -> int:
    """Cuenta cuántos vídeos han sido completados en las últimas 24 horas."""
    if not PROCESSED_FILE.exists():
        return 0
    try:
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=24)
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            count = 0
            for v in data:
                if v.get("status") == "completed" and v.get("date"):
                    try:
                        v_date = datetime.fromisoformat(v["date"])
                        if v_date >= cutoff:
                            count += 1
                    except Exception:
                        pass
            return count
    except Exception:
        return 0

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
    # Upsert: si el ID ya existe, actualizar en lugar de duplicar
    vid_id = entry.get("id")
    if vid_id:
        for i, existing in enumerate(processed):
            if existing.get("id") == vid_id:
                processed[i] = {**existing, **entry}
                break
        else:
            processed.append(entry)
    else:
        processed.append(entry)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

_STOPWORDS = {
    "gta", "vi", "gtavi", "gta6", "grand", "theft", "auto", "rockstar", "games",
    "shorts", "short", "video", "videos", "official", "new", "nuevo", "nueva",
    "nuevos", "nuevas", "con", "los", "las", "que", "como", "del", "para", "por",
    "una", "uno", "this", "that", "with", "from", "the", "and", "out", "finally"
}

def _tokenize_title_for_dedup(text: str) -> set:
    words = re.findall(r"[a-z0-9áéíóúñü]+", (text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}

def _strip_franchise_tokens_for_dedup(text: str) -> str:
    cleaned = re.sub(
        r"\b(grand\s+theft\s+auto\s+(?:vi|6)|gta\s*(?:vi|6)|rockstar\s+games?|official|shorts?)\b",
        " ",
        (text or "").lower(),
    )
    cleaned = re.sub(r"[^\wáéíóúñü]+", " ", cleaned)
    return " ".join(cleaned.split()).strip()

def filter_repetitive_candidates(
    candidates: List[Dict[str, Any]],
    processed_entries: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Escudo Anti-Repetición Semántica y Temática:
    Evita seleccionar una y otra vez los mismos clips o reuploads idénticos,
    sin bloquear reacciones, desgloses ni anuncios distintos de Rockstar por compartir el nombre del juego.
    """
    if not candidates:
        return []

    if processed_entries is None:
        processed_entries = []
        if PROCESSED_FILE.exists():
            try:
                with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                    processed_entries = json.load(f)
            except Exception:
                processed_entries = []

    processed_ids = {e.get("id") for e in processed_entries if e.get("id")}
    # Revisar los últimos 40 elementos y TODOS los rechazados/en espera recientes
    recent_pool = processed_entries[-40:]
    recent_creators = [
        (e.get("creator") or "").strip().lower()
        for e in processed_entries[-3:]
        if e.get("creator") and not str(e.get("creator")).startswith("Search:")
    ]

    history_signatures = []
    for e in recent_pool:
        for field in ("title", "original_title"):
            val = (e.get(field) or "").strip()
            if val:
                history_signatures.append((_strip_franchise_tokens_for_dedup(val), _tokenize_title_for_dedup(val)))

    filtered = []
    seen_cluster_tokens = []

    for cand in candidates:
        cid = cand.get("id")
        if cid and cid in processed_ids:
            continue

        title = (cand.get("title") or "").strip()
        title_clean = _strip_franchise_tokens_for_dedup(title)
        tokens = _tokenize_title_for_dedup(title)

        # 1. Comparar contra el historial reciente usando tema real (sin falsos positivos por 'Grand Theft Auto VI')
        is_duplicate_topic = False
        for hist_clean, hist_tokens in history_signatures:
            if not title_clean or not hist_clean:
                continue
            seq_ratio = difflib.SequenceMatcher(None, title_clean, hist_clean).ratio()
            if seq_ratio >= 0.72:
                is_duplicate_topic = True
                break
            if tokens and hist_tokens:
                overlap = len(tokens & hist_tokens)
                union = len(tokens | hist_tokens)
                if overlap >= 3 and (overlap / max(1, union)) >= 0.55:
                    is_duplicate_topic = True
                    break

        if is_duplicate_topic:
            print(f"[Anti-Repetición] Descartado por tema repetido/rechazado: '{title[:60]}'")
            continue

        # 2. Deduplicar candidatos entre sí dentro de la misma ronda (evita reuploads idénticos del mismo vídeo)
        is_intra_batch_dup = False
        for prev_clean, prev_tokens in seen_cluster_tokens:
            if difflib.SequenceMatcher(None, title_clean, prev_clean).ratio() >= 0.75:
                is_intra_batch_dup = True
                break
            if tokens and prev_tokens:
                overlap = len(tokens & prev_tokens)
                union = len(tokens | prev_tokens)
                if overlap >= 3 and (overlap / max(1, union)) >= 0.60:
                    is_intra_batch_dup = True
                    break
        if is_intra_batch_dup:
            continue

        seen_cluster_tokens.append((title_clean, tokens))

        # 3. Cooldown suave para creadores muy recientes (si otro creador compite, darle preferencia)
        cand_copy = dict(cand)
        src_l = (cand_copy.get("source_name") or cand_copy.get("uploader") or "").strip().lower()
        if src_l and src_l in recent_creators:
            cand_copy["score"] = max(0, cand_copy.get("score", 0) - 20)
            cand_copy["cooldown_applied"] = True

        filtered.append(cand_copy)

    return filtered


def fetch_channel_candidates(max_per_channel: int = 2) -> List[Dict[str, Any]]:
    from .viral_discovery import calculate_virality_score
    from .compliance_auditor import is_safe_rrss_candidate

    if not CHANNELS_FILE.exists():
        return []

    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    base_channels = [c for c in config.get("channels", []) if c.get("enabled", True)]
    base_urls = {(c.get("url") or "").strip().lower() for c in base_channels}

    # Integración acotada del Directorio Maestro: solo autoridades técnicas y GTA puras (cero streamers/prensa competidora)
    # Desactivar muestreo aleatorio de los 1,050 canales históricos para enfocar 100% en fuentes vivas y breaking
    combined_channels = base_channels

    processed_ids = get_processed_ids()
    candidates_by_id: Dict[str, Dict[str, Any]] = {}

    # Inyección de candidatos verificados prioritarios (Curated Safe Queue)
    if CURATED_QUEUE_FILE.exists():
        try:
            with open(CURATED_QUEUE_FILE, "r", encoding="utf-8") as f:
                curated_items = json.load(f)
            for item in curated_items:
                cid = item.get("id")
                if cid and cid not in processed_ids:
                    candidates_by_id[cid] = item
        except Exception as e:
            print(f"[Channels] Aviso leyendo curated_queue: {e}")

    def _scan_channel(ch: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not ch.get("enabled", True):
            return []
        url = (ch.get("url") or "").strip()
        if not url:
            return []
        ch_name = ch.get("name", "Canal")
        is_widescreen_src = ("/videos" in url or bool(ch.get("allow_long_clipping", False)))
        allow_official = bool(ch.get("allow_official_commentary", False))
        results = []

        # Si el canal en channel_directory no incluye /videos ni /shorts, usar /videos limpio (sin fallback ytsearch)
        target_url = url
        if not ("/shorts" in target_url or "/videos" in target_url):
            target_url = target_url.rstrip("/") + "/videos"
            is_widescreen_src = True

        res_stdout = ""
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s\t%(url)s\t%(upload_date)s\t%(uploader)s",
                "-I", f"1:{max(5, max_per_channel * 3)}",
                target_url
            ], capture_output=True, text=True, check=True, timeout=25)
            res_stdout = res.stdout
        except Exception:
            return []

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
                real_uploader = parts[7].strip() if len(parts) > 7 and parts[7].strip() not in ("NA", "") else ch_name

                if vid_id and vid_id not in processed_ids and vid_id != "NA":
                    days_old = None
                    if up_date and up_date.isdigit() and len(up_date) == 8:
                        try:
                            age_days = (datetime.now() - datetime.strptime(up_date, "%Y%m%d")).days
                            days_old = max(1, age_days)
                        except Exception:
                            pass

                    # Descartar vídeos muy antiguos si tienen fecha
                    if days_old is not None and days_old > 180:
                        continue

                    try:
                        dur_secs = float(duration) if duration and duration != "NA" else 0.0
                    except ValueError:
                        dur_secs = 0.0

                    # FILTRO ESTRICTO DE SEGURIDAD Y CUMPLIMIENTO RRSS:
                    # Fuentes 16:9 (/videos) habilitan auto-recorte de picos virales (hasta 900s)
                    # Lanzamientos oficiales nuevos (ej. Rockstar Pre-Load Now) permitidos si allow_official=True para transformación editorial
                    is_safe, reject_reason, comp_meta = is_safe_rrss_candidate(
                        title,
                        uploader=real_uploader,
                        duration_sec=dur_secs,
                        allow_long_clipping=is_widescreen_src,
                        allow_official_commentary=allow_official
                    )
                    if not is_safe:
                        continue

                    # FILTRO DE TRACCIÓN Y VIRALIDAD REAL:
                    is_authority_src = comp_meta.get("is_verified_authority", False)
                    is_fresh_breakout = (days_old == 1 and views >= 2_000)
                    if not is_authority_src and views > 0 and views < 12_000 and not is_fresh_breakout:
                        continue

                    score_data = calculate_virality_score(title, dur_secs, views, days_old=days_old, like_count=like_count)
                    velocity = score_data.get("velocity_vpd")
                    final_score = score_data["score"]
                    if allow_official and views >= 100_000:
                        final_score = min(100, max(final_score, 85) + 12)
                    elif is_widescreen_src and is_authority_src:
                        final_score = min(100, final_score + 12)
                    elif is_widescreen_src:
                        final_score = min(100, final_score + 6)

                    # El formato final exportado siempre es Short 9:16 (auto-recortado por downloader si >60s)
                    results.append({
                        "id": vid_id,
                        "title": title,
                        "url": vid_url,
                        "duration": dur_secs,
                        "views": views,
                        "like_count": like_count,
                        "days_old": days_old,
                        "velocity": velocity,
                        "score": final_score,
                        "source_name": real_uploader,
                        "uploader": real_uploader,
                        "source_type": ch.get("type", "general"),
                        "lang": ch.get("lang", "es"),
                        "is_short": True if (is_widescreen_src or 0 <= dur_secs <= 60) else False,
                        "allow_long_clipping": is_widescreen_src,
                        "allow_official_commentary": allow_official,
                        "source_count": 1,
                        "block_instagram": ch.get("block_instagram", False),
                        "allowed_platforms": ch.get("allowed_platforms", ["youtube", "tiktok", "instagram"]),
                    })
        return results

    def _scan_query(q: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not q.get("enabled", False):
            return []
        query = q.get("query", "")
        sp_filter = q.get("sp", "EgQIAxAB")  # EgQIAhAB = Hoy (24h Videos), EgQIAxAB = Esta semana (7d Videos)
        is_today_breaking = (sp_filter == "EgQIAhAB")
        allow_long = not q.get("only_shorts", True)
        results = []

        search_target = query
        if query.startswith("ytsearch") and ":" in query:
            terms = query.split(":", 1)[1].strip()
            search_target = f"https://www.youtube.com/results?search_query={quote_plus(terms)}&sp={quote_plus(sp_filter)}"

        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "-I", "1:10",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s\t%(url)s\t%(upload_date)s\t%(uploader)s",
                search_target
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
                    real_uploader = parts[7].strip() if len(parts) > 7 and parts[7].strip() not in ("NA", "") else "Análisis GTA 6"

                    # Descartar URLs de canales sueltos devueltas por búsqueda de YouTube
                    if not vid_id or vid_id == "NA" or vid_id.startswith("UC") or "/channel/" in vid_url:
                        continue

                    if vid_id not in processed_ids:
                        days_old = None
                        if up_date and up_date.isdigit() and len(up_date) == 8:
                            try:
                                age_days = (datetime.now() - datetime.strptime(up_date, "%Y%m%d")).days
                                days_old = max(1, age_days)
                            except Exception:
                                pass

                        # En búsquedas de ÚLTIMA HORA (HOY), aceptar vídeos en ascenso desde 2,500 vistas
                        min_req_views = 2_500 if is_today_breaking else 10_000
                        is_fresh_breakout = (days_old == 1 and views >= 2_000)
                        if views < min_req_views and not is_fresh_breakout:
                            continue

                        try:
                            dur_secs = float(duration) if duration and duration != "NA" else 0.0
                        except ValueError:
                            dur_secs = 0.0

                        upl_l = real_uploader.strip().lower()
                        allow_official_q = (
                            ("rockstar" in upl_l or upl_l in ("playstation", "xbox"))
                            and not ("trailer 1" in title.lower())
                        )
                        is_safe, _, _ = is_safe_rrss_candidate(
                            title,
                            uploader=real_uploader,
                            duration_sec=dur_secs,
                            allow_long_clipping=allow_long,
                            allow_official_commentary=allow_official_q
                        )
                        if not is_safe:
                            continue

                        if q.get("only_shorts", True) and (dur_secs > 65 or (0 < dur_secs < 12)):
                            continue

                        score_data = calculate_virality_score(title, dur_secs, views, days_old=days_old, like_count=like_count)
                        velocity = score_data.get("velocity_vpd")
                        adjusted_score = min(100, score_data["score"] + 12) if is_today_breaking else max(0, score_data["score"] - 5)

                        results.append({
                            "id": vid_id,
                            "title": title,
                            "url": vid_url,
                            "duration": dur_secs,
                            "views": views,
                            "like_count": like_count,
                            "days_old": days_old,
                            "velocity": velocity,
                            "score": adjusted_score,
                            "source_name": real_uploader,
                            "uploader": real_uploader,
                            "search_query": query,
                            "source_type": "breaking_today" if is_today_breaking else "viral_search",
                            "lang": q.get("lang", "es"),
                            "is_short": True if (allow_long or 0 <= dur_secs <= 60) else False,
                            "allow_long_clipping": allow_long,
                            "allow_official_commentary": allow_official_q,
                            "source_count": 1,
                            "block_instagram": q.get("block_instagram", False),
                            "allowed_platforms": q.get("allowed_platforms", ["youtube", "tiktok", "instagram"]),
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
            if cand.get("source_type") != "viral_search" or existing.get("source_type") != "viral_search":
                existing["source_count"] = existing.get("source_count", 1) + 1
                existing["score"] = min(100, existing["score"] + 5)
            if cand["score"] > existing["score"]:
                cand["source_count"] = existing["source_count"]
                candidates_by_id[vid_id] = cand

    # 1. Target Channels en paralelo
    target_channels = combined_channels
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_scan_channel, ch): ch for ch in target_channels}
        for future in concurrent.futures.as_completed(futures):
            for cand in future.result():
                _merge_candidate(cand)

    # 2. Search queries en paralelo (máx 3 workers)
    from .config import is_gameplay_enabled

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
    # Enriquecer con YouTube Data API v3 en tiempo real (<0.5s batch) para obtener publishedAt, duration y views/h reales
    candidates = enrich_candidates_with_yt_api(candidates)

    # Re-validar seguridad/antigüedad con metadatos exactos de YouTube API
    fresh_candidates = []
    for c in candidates:
        title_c = c.get("title", "")
        uploader_c = c.get("uploader", "")
        dur_c = float(c.get("duration") or 0.0)
        hours_old = float(c.get("hours_old", 720.0))
        vph = float(c.get("views_per_hour", 0.0))
        source_type = c.get("source_type", "")

        upl_l = uploader_c.strip().lower()
        is_rockstar_official = (
            ("rockstar" in upl_l or upl_l in ("playstation", "xbox"))
            and "trailer 1" not in title_c.lower()
        )
        if is_rockstar_official:
            c["allow_official_commentary"] = True
            c["allow_long_clipping"] = True

        # Filtrar vídeos obsoletos según el tipo de fuente
        if source_type in ("breaking_today", "viral_search"):
            if hours_old > 168 and not is_rockstar_official:
                continue
        else:
            if hours_old > 720:
                continue

        # Si venía de búsqueda strict-short y la API revela duración > 65s (sin clipping permitido), descartar
        if c.get("only_shorts") and not c.get("allow_long_clipping") and dur_c > 65:
            continue
        if dur_c > 0 and dur_c < 10:
            continue

        is_safe, _, _ = is_safe_rrss_candidate(
            title_c,
            uploader=uploader_c,
            duration_sec=dur_c,
            allow_long_clipping=c.get("allow_long_clipping", False),
            allow_official_commentary=c.get("allow_official_commentary", False),
        )
        if not is_safe:
            continue

        # Recalcular score dominado por velocidad real (views/hora) y frescura (<24h)
        if vph >= 50000:
            vph_pts = 60
        elif vph >= 10000:
            vph_pts = 54
        elif vph >= 2500:
            vph_pts = 46
        elif vph >= 500:
            vph_pts = 36
        elif vph >= 100:
            vph_pts = 24
        elif vph >= 20:
            vph_pts = 14
        else:
            vph_pts = min(12.0, vph * 0.5)

        if hours_old <= 6:
            recency_pts = 30
        elif hours_old <= 24:
            recency_pts = 24
        elif hours_old <= 72:
            recency_pts = 14
        elif hours_old <= 168:
            recency_pts = 6
        else:
            recency_pts = 0

        views_c = int(c.get("views") or 0)
        likes_c = int(c.get("like_count") or 0)
        like_ratio = (likes_c / max(views_c, 1)) if views_c > 0 else 0.0
        eng_pts = min(10.0, like_ratio * 200.0) + (5.0 if c.get("source_count", 1) > 1 else 0.0)
        if source_type == "breaking_today" and hours_old <= 24:
            eng_pts += 4.0

        c["score"] = min(100, int(round(vph_pts + recency_pts + eng_pts)))
        fresh_candidates.append(c)

    # Escudo Anti-Repetición Temática y Cooldown de Creador
    candidates = filter_repetitive_candidates(fresh_candidates)

    # Ordenar estrictamente por score de tracción y velocidad views/hora
    candidates.sort(key=lambda x: (-x.get("score", 0), -x.get("views_per_hour", 0.0), x.get("hours_old", 9999.0)))

    return candidates


def _parse_iso8601_duration(iso_str: str) -> float:
    """Convierte una duración ISO 8601 de YouTube (ej. 'PT13M45S', 'PT30S') a segundos."""
    import re
    if not iso_str:
        return 0.0
    m = re.match(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", iso_str.strip())
    if not m:
        return 0.0
    days = float(m.group(1) or 0)
    hours = float(m.group(2) or 0)
    minutes = float(m.group(3) or 0)
    seconds = float(m.group(4) or 0)
    return days * 86400.0 + hours * 3600.0 + minutes * 60.0 + seconds


def enrich_candidates_with_yt_api(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Consulta YouTube Data API v3 en lotes de 50 vídeos (<0.5s) para obtener
    publishedAt, duration ISO, viewCount, likeCount y channelTitle reales,
    calculando hours_old y views_per_hour exactos.
    """
    if not candidates:
        return candidates

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)

    # Identificar IDs válidos de YouTube (11 caracteres típicos, evitando rutas no-YT)
    yt_ids = list(dict.fromkeys([
        str(c.get("id", "")).strip()
        for c in candidates
        if c.get("id") and len(str(c.get("id", "")).strip()) == 11
    ]))

    meta_by_id: Dict[str, Dict[str, Any]] = {}
    if yt_ids:
        try:
            from .uploader import get_authenticated_youtube_service
            yt = get_authenticated_youtube_service(account="extra")
            if yt is not None:
                for i in range(0, len(yt_ids), 50):
                    chunk = yt_ids[i:i + 50]
                    resp = yt.videos().list(
                        part="snippet,statistics,contentDetails",
                        id=",".join(chunk)
                    ).execute()
                    for item in resp.get("items", []):
                        if item.get("id"):
                            meta_by_id[item["id"]] = item
        except Exception as e:
            print(f"[Channels] Aviso enriqueciendo candidatos con YouTube API v3: {e}")

    for c in candidates:
        vid_id = str(c.get("id", "")).strip()
        item = meta_by_id.get(vid_id)
        if item:
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            if snippet.get("title"):
                c["title"] = snippet["title"]
            ch_title = snippet.get("channelTitle")
            if ch_title:
                c["uploader"] = ch_title
                if c.get("source_type") in ("viral_search", "breaking_today") or not c.get("source_name"):
                    c["source_name"] = ch_title

            parsed_dur = _parse_iso8601_duration(content.get("duration", ""))
            if parsed_dur > 0:
                c["duration"] = parsed_dur
                c["is_short"] = bool(c.get("allow_long_clipping") or 0 < parsed_dur <= 62)

            if "viewCount" in stats:
                try:
                    c["views"] = int(stats["viewCount"])
                except (TypeError, ValueError):
                    pass
            if "likeCount" in stats:
                try:
                    c["like_count"] = int(stats["likeCount"])
                except (TypeError, ValueError):
                    pass

            pub_at = snippet.get("publishedAt")
            if pub_at:
                try:
                    pub_dt = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
                    hours_old = max(0.08, (now_utc - pub_dt).total_seconds() / 3600.0)
                    c["published_at"] = pub_at
                    c["hours_old"] = round(hours_old, 2)
                    c["days_old"] = max(0, int(hours_old // 24))
                    views_val = int(c.get("views") or 0)
                    vph = round(views_val / hours_old, 1)
                    c["views_per_hour"] = vph
                    c["velocity"] = int(round(vph * 24.0))
                    continue
                except Exception:
                    pass

        # Fallback si la API no devolvió este ID o no hay red/token en tests
        if "hours_old" not in c:
            days_old = c.get("days_old", 7)
            try:
                days_num = float(days_old)
            except (TypeError, ValueError):
                days_num = 7.0
            est_hours = max(12.0, days_num * 24.0) if days_num < 900 else 720.0
            c["hours_old"] = round(est_hours, 2)
        if "views_per_hour" not in c:
            views_val = int(c.get("views") or 0)
            c["views_per_hour"] = round(views_val / max(0.5, float(c["hours_old"])), 1)
            c.setdefault("velocity", int(round(c["views_per_hour"] * 24.0)))

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

DISCOVERED_CHANNELS_FILE = DATA_DIR / "discovered_channels.json"
CURATED_QUEUE_FILE = DATA_DIR / "curated_queue.json"

def auto_register_source_from_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra automáticamente el canal/creador de un enlace compartido por el usuario
    en data/discovered_channels.json y en config/channels.json (si es canal de YouTube válido).
    Alimenta el motor de sugerencias y aprendizaje continuo.
    """
    uploader = (meta.get("uploader") or "").strip()
    platform = meta.get("platform") or "YouTube"
    if not uploader or uploader.lower() in ["comunidad gta 6", "desconocido", "unknown", "none", ""]:
        return {"success": False, "status": "ignored", "reason": "Creador genérico o desconocido"}

    # Determinar URL del canal / creador
    ch_url = (meta.get("channel_url") or meta.get("uploader_url") or "").strip()
    if not ch_url:
        if platform == "YouTube":
            clean_name = re.sub(r"[^\w\-]", "", uploader)
            ch_url = f"https://www.youtube.com/@{clean_name}/shorts"
        else:
            ch_url = meta.get("url", "")

    if "youtube.com" in ch_url:
        if not ch_url.endswith("/shorts") and not ch_url.endswith("/videos"):
            ch_url = ch_url.rstrip("/") + "/shorts"

    # Cargar discovered_channels.json
    discovered: Dict[str, Dict[str, Any]] = {}
    if DISCOVERED_CHANNELS_FILE.exists():
        try:
            with open(DISCOVERED_CHANNELS_FILE, "r", encoding="utf-8") as f:
                discovered = json.load(f)
        except Exception:
            discovered = {}

    # Buscar coincidencia existente por URL o nombre
    key = ch_url
    if key not in discovered:
        for k, v in discovered.items():
            if v.get("name", "").lower() == uploader.lower():
                key = k
                break

    strategy = meta.get("strategy") or {}
    archetype = strategy.get("archetype", "Noticias & Novedades")
    rec_mode = strategy.get("recommended_opt", "short")
    title = meta.get("title", "")
    now_iso = datetime.now().isoformat()

    is_new_discovery = key not in discovered

    if is_new_discovery:
        discovered[key] = {
            "name": uploader,
            "url": ch_url,
            "platform": platform,
            "first_discovered": now_iso,
            "last_seen": now_iso,
            "best_clip_title": title,
            "best_clip_views": 0,
            "best_score": 85,
            "archetype": archetype,
            "recommended_mode": rec_mode,
            "occurrences": 1,
            "sample_titles": [title] if title else [],
            "is_monitored": False,
            "source_origin": "user_shared_link"
        }
    else:
        item = discovered[key]
        item["occurrences"] = item.get("occurrences", 0) + 1
        item["last_seen"] = now_iso
        if archetype:
            item["archetype"] = archetype
        if rec_mode:
            item["recommended_mode"] = rec_mode
        samples = item.setdefault("sample_titles", [])
        if title and title not in samples:
            samples.insert(0, title)
            item["sample_titles"] = samples[:10]

    # Verificar si ya existe en config/channels.json
    config = {"channels": [], "search_queries": []}
    if CHANNELS_FILE.exists():
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    channels_list = config.get("channels", [])
    already_in_config = any(
        ch.get("name", "").lower() == uploader.lower() or
        (ch_url and ch.get("url", "").rstrip("/") == ch_url.rstrip("/"))
        for ch in channels_list
    )

    is_new_channel_added = False
    if not already_in_config and platform == "YouTube":
        lang = "es" if ("es" in rec_mode or "español" in archetype.lower() or "vandal" in uploader.lower() or "3djuegos" in uploader.lower()) else "en"
        new_channel = {
            "name": uploader if "shorts" in uploader.lower() else f"{uploader} (Shorts)",
            "url": ch_url,
            "type": "custom_discovered",
            "lang": lang,
            "filter_keywords": True,
            "enabled": True,
            "description": f"Auto-registrado desde enlace compartido ({archetype})"
        }
        channels_list.append(new_channel)
        config["channels"] = channels_list
        save_channels_config(config)
        is_new_channel_added = True
        discovered[key]["is_monitored"] = True
    elif already_in_config:
        discovered[key]["is_monitored"] = True

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(DISCOVERED_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(discovered, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Channels] Error guardando {DISCOVERED_CHANNELS_FILE}: {e}")

    total_occurrences = discovered[key].get("occurrences", 1)

    return {
        "success": True,
        "uploader": uploader,
        "platform": platform,
        "channel_url": ch_url,
        "is_new": is_new_channel_added,
        "is_already_monitored": already_in_config or is_new_channel_added,
        "occurrences": total_occurrences,
        "archetype": archetype,
        "recommended_mode": rec_mode
    }

def get_discovered_sources_report() -> str:
    """Genera un resumen para Telegram de las fuentes aprendidas y registradas."""
    if not DISCOVERED_CHANNELS_FILE.exists():
        return "ℹ️ Aún no hay fuentes auto-registradas. Pega enlaces de YouTube o TikTok para descubrirlas."

    try:
        with open(DISCOVERED_CHANNELS_FILE, "r", encoding="utf-8") as f:
            discovered = json.load(f)
    except Exception:
        return "⚠️ Error leyendo archivo de fuentes descubiertas."

    if not discovered:
        return "ℹ️ No hay fuentes registradas actualmente."

    total_sources = len(discovered)
    monitored_count = sum(1 for d in discovered.values() if d.get("is_monitored"))
    user_contributed = sum(1 for d in discovered.values() if d.get("source_origin") == "user_shared_link")

    sorted_sources = sorted(discovered.values(), key=lambda x: x.get("occurrences", 1), reverse=True)
    top_items = sorted_sources[:5]

    lines = [
        "🧠 *MOTOR DE APRENDIZAJE Y FUENTES REGISTRADAS*",
        "═" * 36,
        f"• *Total Fuentes Catalogadas:* `{total_sources}`",
        f"• *Monitoreadas Activas:* `{monitored_count}`",
        f"• *Aportadas por Enlaces:* `{user_contributed}`\n",
        "🏆 *TOP FUENTES FRECUENTES:*"
    ]

    for i, s in enumerate(top_items, 1):
        name = s.get("name", "Desconocido")
        arch = s.get("archetype", "General")
        occ = s.get("occurrences", 1)
        mon = "🟢 Monitoreado" if s.get("is_monitored") else "⚪ Candidato"
        lines.append(f"{i}. *{name}* ({occ} clips) — `{arch}` [{mon}]")

    lines.append("\n💡 _Cada enlace que compartes amplía automáticamente el radar del motor de sugerencias._")
    return "\n".join(lines)


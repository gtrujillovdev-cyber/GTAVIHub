import sys
import os
import re
import glob
import json
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from .config import (
    TEMP_DIR, get_ffmpeg_threads, SHORT_MIN_DURATION, GAMEPLAY_MIN_DURATION,
    SHORT_MAX_DURATION, SHORT_TARGET_DURATION, ENABLE_4K_SHORTS, FFMPEG_VIDEO_CODEC
)

def parse_srt_time(ts_str: str) -> float:
    """Convierte HH:MM:SS,mmm a segundos flotantes."""
    try:
        parts = ts_str.strip().replace(",", ".").split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
    except Exception:
        pass
    return 0.0

def format_srt_time(seconds: float) -> str:
    """Convierte segundos a formato estándar SRT HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def deroll_and_clean_srt_content(content: str) -> str:
    """
    Desduplica y sanea subtítulos SRT eliminando el 'rolling buffer' progresivo de YouTube ASR.
    Resuelve de raíz el tartamudeo donde una frase o cláusula se repite en cues consecutivos
    debido a la actualización progresiva de líneas o correcciones parciales de reconocimiento de voz.
    """
    blocks = [b.strip() for b in content.strip().split("\n\n") if b.strip()]
    if not blocks:
        return content

    raw_cues = []
    for b in blocks:
        lines = b.split("\n")
        if len(lines) < 2:
            continue
        time_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else "")
        if not time_line or "-->" not in time_line:
            continue
        t_start, t_end = [p.strip() for p in time_line.split("-->")]
        raw_text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        clean_text_lines = [l.strip() for l in raw_text_lines if l.strip()]
        if clean_text_lines:
            raw_cues.append((t_start, t_end, clean_text_lines))

    cleaned_cues = []
    recent_lines_history = []

    for t_start, t_end, text_lines in raw_cues:
        # 1. Descartar líneas idénticas a las vistas en los últimos cues (rolling caption buffer)
        unique_lines = []
        for l in text_lines:
            l_norm = " ".join(l.lower().strip('.,!?;:"\'').split())
            if not l_norm:
                continue
            if any(l_norm == prev for prev in recent_lines_history[-6:]):
                continue
            unique_lines.append(l)
            recent_lines_history.append(l_norm)

        cue_text = " ".join(unique_lines).strip()
        if not cue_text:
            continue

        cue_norm = " ".join(cue_text.lower().strip('.,!?;:"\'').split())

        if not cleaned_cues:
            cleaned_cues.append([t_start, t_end, cue_text])
            continue

        prev_start, prev_end, prev_text = cleaned_cues[-1]
        prev_norm = " ".join(prev_text.lower().strip('.,!?;:"\'').split())

        # 2. Comprobación de idéntico total
        if cue_norm == prev_norm:
            cleaned_cues[-1][1] = t_end
            continue

        # 3. Comprobación si la frase anterior era un prefijo/subcadena incompleto de la actual
        if prev_norm in cue_norm and len(cue_norm) > len(prev_norm):
            cleaned_cues[-1] = [prev_start, t_end, cue_text]
            continue

        # 4. Comprobación si la frase actual ya estaba completamente contenida en la anterior
        if cue_norm in prev_norm:
            cleaned_cues[-1][1] = t_end
            continue

        # 5. Comprobación de solapamiento de palabras y redundancia semántica
        prev_words = prev_text.split()
        curr_words = cue_text.split()
        prev_clean = [w.lower().strip('.,!?;:"\'') for w in prev_words if len(w) > 0]
        curr_clean = [w.lower().strip('.,!?;:"\'') for w in curr_words if len(w) > 0]

        # Comprobar porcentaje de redundancia con el bloque anterior (>= 70% palabras repetidas)
        if curr_clean and prev_clean:
            overlap_count = sum(1 for w in curr_clean if w in prev_clean)
            if overlap_count / len(curr_clean) >= 0.7:
                cleaned_cues[-1][1] = t_end
                continue

        # Solapamiento sufijo-prefijo (hasta 2 palabras guía iniciales)
        overlap_k = 0
        lead_skip = 0
        max_k = min(len(prev_clean), len(curr_clean))
        for k in range(max_k, 1, -1):
            if prev_clean[-k:] == curr_clean[:k]:
                overlap_k = k
                lead_skip = 0
                break

        if overlap_k == 0:
            for lead in (1, 2):
                if len(curr_clean) > lead:
                    max_k2 = min(len(prev_clean), len(curr_clean) - lead)
                    for k in range(max_k2, 2, -1):
                        if prev_clean[-k:] == curr_clean[lead : lead + k]:
                            overlap_k = k
                            lead_skip = lead
                            break
                    if overlap_k > 0:
                        break

        if overlap_k > 0:
            remaining = curr_words[lead_skip + overlap_k:]
            if not remaining:
                cleaned_cues[-1][1] = t_end
                continue
            cue_text = " ".join(remaining)

        cleaned_cues.append([t_start, t_end, cue_text])

    out_blocks = []
    for idx, (s, e, txt) in enumerate(cleaned_cues, 1):
        out_blocks.append(f"{idx}\n{s} --> {e}\n{txt}")

    return "\n\n".join(out_blocks) + "\n"

def clean_and_deroll_srt(srt_path: Path) -> bool:
    """Lee un archivo SRT en disco, purga su rolling buffer y guarda la versión limpia y desduplicada."""
    if not srt_path.exists():
        return False
    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        cleaned = deroll_and_clean_srt_content(content)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(cleaned)
        return True
    except Exception as e:
        print(f"[!] Error desduplicando SRT en {srt_path.name}: {e}")
        return False

def slice_srt_file(srt_path: Path, start_trim: float, end_trim: float, output_srt: Path) -> bool:
    """Recorta y reindexa un archivo SRT para coincidir con el intervalo recortado."""
    if not srt_path.exists():
        return False
    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        blocks = content.strip().split("\n\n")
        new_blocks = []
        new_idx = 1

        for b in blocks:
            lines = b.strip().split("\n")
            if len(lines) < 2:
                continue
            time_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else "")
            if not time_line or "-->" not in time_line:
                continue
            parts = time_line.split("-->")
            t_start = parse_srt_time(parts[0])
            t_end = parse_srt_time(parts[1])

            # Si el subtítulo se encuentra dentro de la ventana de recorte
            if t_end >= start_trim and t_start <= end_trim:
                shifted_start = max(0.0, t_start - start_trim)
                shifted_end = max(shifted_start + 0.3, min(end_trim - start_trim, t_end - start_trim))
                text_lines = "\n".join(lines[2:] if "-->" in lines[1] else lines[1:])
                new_blocks.append(f"{new_idx}\n{format_srt_time(shifted_start)} --> {format_srt_time(shifted_end)}\n{text_lines}")
                new_idx += 1

        if new_blocks:
            with open(output_srt, "w", encoding="utf-8") as f:
                f.write("\n\n".join(new_blocks) + "\n")
            clean_and_deroll_srt(output_srt)
            return True
    except Exception as e:
        print(f"[!] Error recortando SRT: {e}")
    return False

def snap_window_to_subtitles(
    srt_path: Path,
    v_start: float,
    v_end: float,
    min_duration: float = SHORT_MIN_DURATION,
    max_duration: float = SHORT_MAX_DURATION
) -> Tuple[float, float]:
    """
    Ajusta v_start al inicio de una frase hablada y v_end al final de una frase hablada
    para que la locución empiece y termine limpiamente sin cortar palabras a la mitad.
    """
    if not srt_path or not srt_path.exists():
        return v_start, v_end

    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        blocks = content.strip().split("\n\n")
        cues = []
        for b in blocks:
            lines = b.strip().split("\n")
            if len(lines) < 2:
                continue
            time_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else "")
            if not time_line or "-->" not in time_line:
                continue
            parts = time_line.split("-->")
            t_s = parse_srt_time(parts[0])
            t_e = parse_srt_time(parts[1])
            text = " ".join(lines[2:] if "-->" in lines[1] else lines[1:]).strip()
            if t_e > t_s:
                cues.append({"start": t_s, "end": t_e, "text": text})

        if not cues:
            return v_start, v_end

        # 1. Ajustar v_start al inicio de un cue cercano (evitar empezar a media palabra)
        best_start = v_start
        min_start_diff = float("inf")
        for c in cues:
            diff = abs(c["start"] - v_start)
            if diff < min_start_diff and diff <= 3.5:
                min_start_diff = diff
                best_start = c["start"]

        target_dur = v_end - v_start
        ideal_end = best_start + target_dur

        # 2. Ajustar v_end al final de un cue que termine limpiamente una frase
        candidate_ends = []
        for i, c in enumerate(cues):
            c_dur = c["end"] - best_start
            if min_duration <= c_dur <= max_duration:
                is_sentence_end = bool(re.search(r"[\.!\?:…]\s*$", c["text"]))
                has_subsequent_pause = (i < len(cues) - 1 and (cues[i+1]["start"] - c["end"]) >= 0.35)
                
                score = abs(c["end"] - ideal_end)
                if is_sentence_end:
                    score -= 5.0  # Gran preferencia por terminar en punto o frase cerrada
                else:
                    score += 4.0  # Penalizar fuertemente cortar a mitad de pensamiento
                if has_subsequent_pause:
                    score -= 2.5

                candidate_ends.append((score, c["end"]))

        if candidate_ends:
            candidate_ends.sort(key=lambda x: x[0])
            best_end = candidate_ends[0][1]
            print(f"[✓ Subtitle Snapping] Segmento ajustado a frase: {best_start:.1f}s a {best_end:.1f}s (Duración natural: {best_end - best_start:.1f}s)")
            return (round(best_start, 2), round(best_end, 2))

    except Exception as e:
        print(f"[!] Error en snapping de subtítulos: {e}")

    return v_start, v_end


def find_best_transcript_hook_window(
    srt_path: Path,
    title: str = "",
    min_dur: int = 18,
    max_dur: int = 36,
    total_duration: float = 0.0,
    use_ai: bool = True,
) -> Optional[Tuple[float, float]]:
    """
    Analiza los subtítulos (.srt) de un vídeo largo sin heatmap para localizar
    la ventana de 18-36s con mayor densidad de gancho/revelación/reacción,
    descartando intros genéricas, llamadas a suscripción y segmentos patrocinados.
    """
    if not srt_path or not Path(srt_path).exists():
        return None

    try:
        raw_srt = Path(srt_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
    cues: List[Tuple[float, float, str]] = []
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        time_idx = next((idx for idx, l in enumerate(lines) if "-->" in l), -1)
        if time_idx < 0 or time_idx + 1 >= len(lines):
            continue
        t_parts = lines[time_idx].split("-->")
        if len(t_parts) != 2:
            continue
        s_sec = parse_srt_time(t_parts[0])
        e_sec = parse_srt_time(t_parts[1].split()[0])
        if e_sec <= s_sec:
            continue
        txt = " ".join(lines[time_idx + 1:])
        txt = re.sub(r"<[^>]+>", "", txt)
        txt = re.sub(r"\[[^\]]+\]", "", txt)
        txt = " ".join(txt.split()).strip()
        if txt:
            cues.append((s_sec, e_sec, txt))

    if len(cues) < 3:
        return None

    cues.sort(key=lambda c: c[0])
    eff_total = float(total_duration or cues[-1][1])
    if eff_total <= max_dur + 4:
        return (0.0, round(eff_total, 2))

    sponsor_re = re.compile(
        r"\b(sponsor(?:ed)?|nord\s?vpn|surfshark|express\s?vpn|incogni|ridge\s?wallet|"
        r"raid\s?shadow|raycon|factor|hello\s?fresh|patreon|discount\s?code|promo\s?code|"
        r"use\s?code|scroll\s+down|visit\s+the\s+website|website\s+right\s+now|c[oó]digo\s?de\s?descuento|patrocinad[oa]|enlace\s?en\s?la\s?descripci[oó]n|"
        r"link\s?in\s?(?:the\s)?description)\b",
        re.IGNORECASE,
    )
    cta_re = re.compile(
        r"\b(before\s+we\s+(?:begin|start|jump\s+in)|welcome\s+back\s+to\s+(?:the\s+)?channel|"
        r"don't\s+forget\s+to\s+(?:like|subscribe)|hit\s+that\s+like|subscribe\s+for\s+more|"
        r"thanks\s+for\s+watching|make\s+sure\s+to\s+subscribe|suscr[ií]bete|antes\s+de\s+empezar|"
        r"bienvenidos\s+al\s+canal|deja\s+tu\s+like)\b",
        re.IGNORECASE,
    )
    hook_kw_re = re.compile(
        r"\b(pre-?load|30\s?fps|60\s?fps|frame\s?rate|confirm(?:ed|ado)|official|oficial|"
        r"rockstar|november\s?19|lucia|luc[ií]a|jason|vice\s?city|leonida|secret|hidden|oculto|"
        r"detail|detalle|look\s+at|look\s+closely|pause|insane|crazy|brutal|wtf|no\s+way|"
        r"oh\s+my\s+god|omg|gameplay|trailer|leak|map|size|gb|download|ray\s?tracing|"
        r"physics|f[ií]sicas?|water|agua|hair|mira|incre[ií]ble|polic[ií]a|persecuci[oó]n|"
        r"choque|explosi[oó]n|atropell|disparo|tiroteo|hostia|madre\s+m[ií]a|qu[eé]\s+locura|"
        r"realismo|mec[aá]nica|agarre|coche|ragdoll|misi[oó]n|"
        r"location|ubicaci[oó]n|go\s+to|head\s+to|where\s+to|find|spawn|free|gratis|"
        r"money|dinero|cash|sell|vender|weapon|arma|supercar|chapter|cap[ií]tulo|"
        r"glitch|method|m[eé]todo|easter\s+egg|legendary|legendaria)\b",
        re.IGNORECASE,
    )
    menu_admin_re = re.compile(
        r"\b(tienda|skins?\s+de\s+pago|ultimate\s+edition|copyright|en\s+el\s+(?:bot|vod)|"
        r"apag[oa]\s+la\s+radio|quitar?\s+la\s+radio|m[uú]sica\s+con\s+licencia|ajustes|"
        r"configuraci[oó]n|interfaz\s+de\s+usuario|men[uú]\s+de\s+pausa|controles\s+del\s+mando|"
        r"suscriptores?|donaci[oó]n|patreon|twitch\s+prime)\b",
        re.IGNORECASE,
    )

    target_ideal = min(max_dur, max(min_dur, 26))
    windows = []

    for i in range(len(cues)):
        w_start = cues[i][0]
        w_end = cues[i][1]
        texts = [cues[i][2]]

        for j in range(i + 1, len(cues)):
            # Cortar si hay silencio > 3.5s para evitar tiempo muerto
            if cues[j][0] - w_end > 3.5:
                break
            next_dur = cues[j][1] - w_start
            if next_dur > max_dur:
                break
            w_end = cues[j][1]
            texts.append(cues[j][2])
            if (w_end - w_start) >= target_ideal:
                break

        dur = w_end - w_start
        if dur < min_dur or dur > max_dur + 2:
            continue

        joined = " ".join(texts)
        words = joined.split()
        if len(words) < 10:
            continue

        score = 0.0
        if sponsor_re.search(joined):
            score -= 120.0
        if menu_admin_re.search(joined):
            score -= 65.0
        if cta_re.search(joined):
            score -= 45.0
        if eff_total > 75 and w_start < 6.0:
            score -= 18.0
        if eff_total > 75 and w_end > eff_total - 8.0:
            score -= 25.0

        kw_hits = {m.group(0).lower() for m in hook_kw_re.finditer(joined)}
        score += min(36.0, len(kw_hits) * 6.0)

        num_hits = re.findall(r"\b\d+(?:\.\d+)?\b", joined)
        score += min(12.0, len(num_hits) * 4.0)

        punct_hits = joined.count("!") + joined.count("?")
        score += min(12.0, punct_hits * 3.0)

        wps = len(words) / max(dur, 1.0)
        if 1.8 <= wps <= 4.3:
            score += 8.0
        if 22.0 <= dur <= 32.0:
            score += 6.0

        windows.append({
            "start": round(w_start, 2),
            "end": round(w_end, 2),
            "score": round(score, 2),
            "text": joined,
        })

    if not windows:
        return None

    windows.sort(key=lambda w: (-w["score"], w["start"]))
    if windows[0]["score"] <= -20.0:
        return None

    # Deduplicar ventanas muy solapadas para ofrecer opciones distintas a Gemini si se consulta
    top_candidates = []
    for w in windows:
        overlaps = any(
            min(w["end"], existing["end"]) - max(w["start"], existing["start"]) > 0.55 * (w["end"] - w["start"])
            for existing in top_candidates
        )
        if not overlaps:
            top_candidates.append(w)
        if len(top_candidates) >= 5:
            break

    chosen = top_candidates[0]
    if use_ai and len(top_candidates) >= 2:
        try:
            from .config import GEMINI_API_KEY
            if GEMINI_API_KEY:
                from .translator import get_gemini_client, generate_content_with_retry
                client = get_gemini_client()
                options_txt = "\n".join(
                    f"[{idx}] ({cand['start']:.1f}s-{cand['end']:.1f}s): {cand['text'][:240]}"
                    for idx, cand in enumerate(top_candidates)
                )
                prompt = (
                    f"Vídeo: '{title or 'GTA 6'}'\n"
                    "Elige el ÚNICO fragmento con mayor retención visual y gameplay puro para un YouTube Short/TikTok "
                    "(un momento jugando con acción, físicas, policía, descubrimiento o reacción divertida in-game; "
                    "NUNCA intros, saludos, sponsors, menús de pausa/ajustes ni charlas sobre radio/copyright del directo).\n"
                    f"{options_txt}\n\n"
                    "Responde SOLO con el número de índice (ejemplo: 0)."
                )
                resp = generate_content_with_retry(client, prompt)
                m = re.search(r"\b([0-4])\b", (resp.text or "").strip())
                if m:
                    idx = int(m.group(1))
                    if 0 <= idx < len(top_candidates) and top_candidates[idx]["score"] > -20.0:
                        chosen = top_candidates[idx]
        except Exception:
            pass

    print(
        f"[✓ Transcript Hook] Ventana inteligente seleccionada: "
        f"{chosen['start']:.1f}s a {chosen['end']:.1f}s (score={chosen['score']})"
    )
    return (chosen["start"], chosen["end"])


def _inspect_remote_video_info(url: str) -> Dict[str, Any]:
    """Obtiene metadatos ligeros remotos (duración, heatmap, live_status) sin descargar vídeo."""
    attempts = [
        [
            sys.executable, "-m", "yt_dlp",
            "--impersonate", "chrome",
            "--no-check-certificates",
            "--no-playlist",
            "--skip-download",
            "--dump-single-json",
            url
        ],
        [
            sys.executable, "-m", "yt_dlp",
            "--force-ipv4",
            "--no-check-certificates",
            "--no-playlist",
            "--skip-download",
            "--dump-single-json",
            url
        ],
    ]
    for cmd in attempts:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0 and (res.stdout or "").strip():
                return json.loads(res.stdout)
        except Exception as e:
            print(f"[!] Info inspector remoto: {e}")
    return {}


def _select_heatmap_window(
    heatmap: Any,
    duration: float,
    target_duration: int = SHORT_TARGET_DURATION
) -> Optional[Tuple[float, float]]:
    """Calcula la ventana óptima por AVD sobre un heatmap de YouTube ya cargado."""
    if not heatmap or not isinstance(heatmap, list) or len(heatmap) <= 5 or duration <= 60:
        return None
    candidate_durations = [19, 24, 30, 36, 42, 50, 56, 58]
    best_avd_score = -1.0
    best_start = 15.0
    best_dur = target_duration
    best_avd_seconds = 0.0

    for c_dur in candidate_durations:
        if c_dur > duration:
            continue
        for pt in heatmap:
            start_t = float(pt.get("start_time", 0.0))
            end_t = start_t + c_dur
            if end_t > duration:
                break
            window_pts = [float(p.get("value", 0.0)) for p in heatmap if start_t <= float(p.get("start_time", 0.0)) <= end_t]
            if not window_pts:
                continue
            avg_retention = sum(window_pts) / len(window_pts)
            peak_retention = max(window_pts)
            min_retention = min(window_pts)

            estimated_avd_s = c_dur * avg_retention * (1.0 + peak_retention * 0.35)
            cliff_penalty = max(0.5, min(1.0, (min_retention / (avg_retention + 1e-4))))
            duration_penalty = 1.0 if c_dur <= 28 else (0.85 if c_dur <= 36 else 0.70)
            avd_score = estimated_avd_s * (0.7 + 0.3 * cliff_penalty) * duration_penalty

            if avd_score > best_avd_score:
                best_avd_score = avd_score
                best_start = start_t
                best_dur = c_dur
                best_avd_seconds = estimated_avd_s

    print("[⚡ AVD Engine] Segmento óptimo por Average View Duration:")
    print(f"    • Rango: {best_start:.1f}s a {best_start + best_dur:.1f}s ({best_dur}s)")
    print(f"    • AVD Estimado: {best_avd_seconds:.1f}s de retención neta (Score AVD: {best_avd_score:.2f})")
    return (best_start, best_start + best_dur)


def find_viral_heatmap_segment(
    url: str,
    min_duration: int = GAMEPLAY_MIN_DURATION,
    max_duration: int = SHORT_MAX_DURATION,
    target_duration: int = SHORT_TARGET_DURATION,
    video_id: str = "",
    prefetched_info: Optional[Dict[str, Any]] = None
) -> Optional[Tuple[float, float]]:
    """
    Analiza el mapa de calor de YouTube ('most replayed' heatmap) con yt-dlp
    para encontrar una ventana dinámica (26-52s) de máxima retención y engagement.
    Si el vídeo original ya es corto (<= 58s), preserva su duración original sin recortar.
    """
    try:
        info = prefetched_info if prefetched_info is not None else _inspect_remote_video_info(url)
        if not info:
            return None
        duration = float(info.get("duration") or 0)

        if duration <= 60:
            print(f"[*] Vídeo ya en formato Short orgánico ({duration:.1f}s <= 60s). Duración original preservada (cero cortes).")
            return None

        seg = _select_heatmap_window(info.get("heatmap"), duration, target_duration=target_duration)
        if seg:
            return seg
        print(f"[*] Vídeo largo ({duration}s) sin heatmap público en YouTube.")
        return None
    except Exception as e:
        print(f"[!] Info detector: {e}")
        return None

def suggest_video_strategy(
    title: str,
    duration_sec: int = 0,
    uploader: str = "",
    platform: str = "YouTube"
) -> Dict[str, Any]:
    """
    Analiza un vídeo y determina la estrategia óptima de transformación editorial
    para maximizar retención y cumplir estrictamente con Fair Use según su arquetipo.
    """
    title_lower = (title or "").lower()
    uploader_lower = (uploader or "").lower()

    # Detección de idioma español
    spanish_markers = [
        " de ", " el ", " la ", " los ", " las ", " en ", " y ", " que ", " por ", " para ",
        "detalles", "alucinantes", "físico", "físicas", "gráfico", "gráficos", "tráiler",
        "filtración", "noticia", "novedades", "secreto", "secretos", "jugabilidad", "español"
    ]
    is_spanish = any(m in f" {title_lower} " for m in spanish_markers) or any(
        u in uploader_lower for u in ["vandal", "elanalistadebits", "eurogamer spain", "3djuegos", "vidaextra", "alfabetajuega"]
    )

    # 1. Arquetipo: Comparativa Gráfica / FPS (en Loop si <= 20s, o Split/Audio Juego si > 20s)
    is_fps_or_vs = bool(re.search(r"\b(vs|versus|comparativa|comparison|30\s*fps|60\s*fps|frame\s*rate)\b", title_lower)) or "graphics vs" in title_lower or "gráfico vs" in title_lower
    is_comparison = is_fps_or_vs or ("trailer 2" in title_lower)
    if (0 < duration_sec <= 16) or (is_comparison and duration_sec <= 20):
        return {
            "recommended_opt": "gameplay",
            "archetype": "Comparativa Visual en Loop",
            "badge": "⚡ Loop Ultra-Corto",
            "reason": "Vídeo corto de alto impacto visual. Encuadre inmersivo con audio del juego maximiza el completion rate (>120%).",
            "hook_text": "GTA 6 VS GTA 5 🤯"
        }

    # 2. Arquetipo: Listicle / Curiosidades y Top Detalles
    is_listicle = bool(re.search(r"\b(\d+)\s*(detalles|cosas|secrets|things|details|easter eggs|curiosidades|secretos)\b", title_lower))
    if is_listicle:
        if is_spanish:
            return {
                "recommended_opt": "short",
                "archetype": "Listicle de Detalles & Curiosidades",
                "badge": "🔥 Retención Máxima (Listicle)",
                "reason": "Contenido en español con ritmo enumerado. Recomendado Subtítulos Pop limpios sin cajas para disparar el CTR.",
                "hook_text": "¡DETALLES ALUCINANTES! 🔥"
            }
        else:
            return {
                "recommended_opt": "dub",
                "archetype": "Listicle en Inglés (Top Detalles)",
                "badge": "🎙️ Doblaje Neural + Subtítulos",
                "reason": "Top detalles en inglés. El Doblaje Neural al español (+12% ritmo) elimina la barrera de idioma y captura la retención completa.",
                "hook_text": "¡SECRETOS REVELADOS! 🔍"
            }

    # 3. Comparativa Técnica / FPS larga (>20s, ej. 30 FPS vs 60 FPS en X/YouTube) -> Audio original del juego + Split Apilado
    if is_fps_or_vs:
        fps_hook = "30 FPS VS 60 FPS\nDIFERENCIA REAL EN GTA 6" if "fps" in title_lower else "COMPARATIVA DIRECTA\nMIRA LA DIFERENCIA"
        return {
            "recommended_opt": "gameplay",
            "archetype": "Comparativa Técnica / FPS",
            "badge": "🎮 Split / Audio del Juego",
            "reason": "Comparativa visual/técnica. Preserva el audio real del juego y apila o encuadra ambas vistas sin voz encima.",
            "hook_text": fps_hook
        }

    # 4. Arquetipo: Físicas RAGE 9, Gameplay Puro, Misiones o Demostración
    is_physics_gameplay = any(k in title_lower for k in [
        "rage 9", "physics", "físicas", "water physics", "crash", "car crash", "accident", "accidente",
        "tiroteo", "gunplay", "shooting", "driving", "conducción", "npc behavior", "ia peatones",
        "pure gameplay", "gameplay clip", "free roam", "first mission", "primera mision",
        "primera misión", "open world", "mundo abierto", "police chase", "walkthrough",
        "no commentary", "gameplay"
    ])
    if is_physics_gameplay:
        return {
            "recommended_opt": "gameplay",
            "archetype": "Gameplay Real & Físicas RAGE 9",
            "badge": "🎮 Pro-Cinema 83.3%",
            "reason": "Metraje de gameplay real. Se recomienda respetar el audio auténtico del juego y aplicar reencuadre centrado cinematográfico.",
            "hook_text": "¡GAMEPLAY REAL GTA 6! 🎮"
        }

    # 4. Si está en inglés (narrado por streamers o canales anglos)
    if not is_spanish:
        return {
            "recommended_opt": "dub",
            "archetype": "Contenido en Inglés",
            "badge": "🎙️ Doblaje Neural Recomendado",
            "reason": "Locución en inglés. Doblaje con voz neural en español y atenuación del audio original al 18% para monetización y audiencia hispana.",
            "hook_text": "¡ANÁLISIS AL DETALLE! 🌴"
        }

    # 5. Contenido en español estándar / Noticias / Explicación
    return {
        "recommended_opt": "short",
        "archetype": "Noticias & Novedades GTA 6",
        "badge": "⚡ Short Vertical Hormozi",
        "reason": "Clip en español. Reencuadre 9:16 con subtítulos dinámicos de alto contraste y gancho superior.",
        "hook_text": "¡NOVEDAD EXCLUSIVA! 🌴"
    }

def get_url_metadata(url: str) -> Dict[str, Any]:
    """
    Extrae metadatos esenciales de una URL (YouTube, Twitter/X, TikTok, etc.)
    de forma tolerante a fallos, detectando plataforma, título, duración y creador.
    """
    import time
    is_twitter_or_x = any(d in url.lower() for d in ["twitter.com", "x.com"])
    is_tiktok = "tiktok.com" in url.lower()
    is_youtube = any(d in url.lower() for d in ["youtube.com", "youtu.be"])

    platform_name = "Twitter/X" if is_twitter_or_x else ("TikTok" if is_tiktok else ("YouTube" if is_youtube else "Web"))

    # Intentos de extracción: para Twitter/TikTok se prefiere llamada limpia sin impersonate chrome
    cmd_attempts = []
    base_cmd = [
        sys.executable, "-m", "yt_dlp",
        "--force-ipv4",
        "--no-check-certificates",
        "--no-playlist",
        "--print", "%(id)s\t%(title)s\t%(duration)s\t%(uploader)s\t%(extractor_key)s\t%(channel_url)s\t%(uploader_url)s",
        url
    ]
    if not is_twitter_or_x:
        cmd_attempts.append([
            sys.executable, "-m", "yt_dlp",
            "--impersonate", "chrome",
            "--no-check-certificates",
            "--no-playlist",
            "--print", "%(id)s\t%(title)s\t%(duration)s\t%(uploader)s\t%(extractor_key)s\t%(channel_url)s\t%(uploader_url)s",
            url
        ])
    cmd_attempts.append(base_cmd)

    stdout = ""
    for cmd in cmd_attempts:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0 and res.stdout.strip():
                stdout = res.stdout.strip()
                break
        except Exception:
            continue

    channel_url = ""
    uploader_url = ""

    if stdout:
        parts = stdout.split("\t")
        raw_id = parts[0].strip() if len(parts) > 0 and parts[0].strip() else f"vid_{int(time.time())}"
        raw_title = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "GTA 6 Clip"
        dur_raw = parts[2].strip() if len(parts) > 2 else "0"
        uploader = parts[3].strip() if len(parts) > 3 and parts[3].strip() else "Comunidad GTA 6"
        extractor = parts[4].strip() if len(parts) > 4 else platform_name
        channel_url = parts[5].strip() if len(parts) > 5 else ""
        uploader_url = parts[6].strip() if len(parts) > 6 else ""
    else:
        raw_id = f"vid_{int(time.time())}"
        raw_title = "GTA 6 Gameplay Clip"
        dur_raw = "0"
        uploader = "Comunidad GTA 6"
        extractor = platform_name

    try:
        dur_sec = int(float(dur_raw))
        dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d} min"
    except Exception:
        dur_sec = 0
        dur_str = "Auto"

    clean_title = raw_title
    if "gta" not in clean_title.lower():
        clean_title = f"GTA 6: {clean_title}"

    strategy = suggest_video_strategy(
        title=clean_title,
        duration_sec=dur_sec,
        uploader=uploader,
        platform=platform_name
    )

    return {
        "id": raw_id,
        "title": clean_title,
        "duration_sec": dur_sec,
        "duration_str": dur_str,
        "uploader": uploader,
        "platform": platform_name,
        "extractor": extractor,
        "url": url,
        "channel_url": channel_url,
        "uploader_url": uploader_url,
        "strategy": strategy
    }

def _fetch_subtitles_yt(
    url: str,
    video_id: str,
    source_lang: str
) -> Tuple[Optional[Path], str]:
    """Descarga únicamente los subtítulos originales más fiables antes de descargar el vídeo."""
    sub_output_template = str(TEMP_DIR / f"{video_id}.%(ext)s")
    src_l = (source_lang or "es").strip().lower()
    if src_l.startswith("es"):
        sub_langs_to_try = [
            ("es", ["es-orig", "es"]),
            ("en", ["en-orig", "en"]),
        ]
    else:
        sub_langs_to_try = [
            ("en", ["en-orig", "en"]),
            ("es", ["es"]),
        ]

    for lang_code, lang_candidates in sub_langs_to_try:
        for target_lang in lang_candidates:
            cmd_subs = [
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--no-playlist",
                "--skip-download",
                "--write-auto-subs",
                "--write-subs",
                "--sub-langs", target_lang,
                "--convert-subs", "srt",
                "-o", sub_output_template,
                url
            ]
            try:
                subprocess.run(cmd_subs, capture_output=True, text=True, timeout=30)
                found_subs = list(TEMP_DIR.glob(f"{video_id}*.srt")) + list(TEMP_DIR.glob(f"{video_id}*.vtt"))
                if found_subs:
                    chosen = found_subs[0]
                    if chosen.suffix.lower() == ".vtt":
                        converted_srt = chosen.with_suffix(".srt")
                        subprocess.run(["ffmpeg", "-y", "-i", str(chosen), str(converted_srt)], capture_output=True)
                        if converted_srt.exists():
                            chosen = converted_srt
                    clean_and_deroll_srt(chosen)
                    print(f"[*] Subtítulos descargados con éxito ({target_lang} -> {lang_code})")
                    return chosen, lang_code
            except Exception:
                continue
    return None, source_lang


def _select_action_chapter_window(
    chapters: Any,
    duration: float,
    target_duration: int = 24
) -> Optional[Tuple[float, float]]:
    """Elige el mejor capítulo de acción/gameplay dentro de vídeos largos de YouTube."""
    if not chapters or not isinstance(chapters, list) or duration <= SHORT_MAX_DURATION:
        return None

    skip_kws = (
        "intro", "opening", "menu", "settings", "options", "config",
        "outro", "credits", "sponsor", "subscribe", "recap", "title"
    )
    action_kws = (
        "chase", "police", "wanted", "combat", "shootout", "gunfight",
        "robbery", "heist", "crash", "physics", "water", "free roam",
        "open world", "mission", "action", "escape", "explosion",
        "gameplay", "ps5 pro", "xbox", "fps", "vs", "comparison",
        "beach", "night", "driving", "boat", "helicopter"
    )

    best_score = -999
    best_win = None
    best_title = ""

    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        title = str(ch.get("title") or "").strip()
        tl = title.lower()
        s_t = float(ch.get("start_time") or 0.0)
        e_t = float(ch.get("end_time") or duration)
        span = e_t - s_t
        if span < 18.0 or s_t >= duration - 12.0:
            continue

        sc = 0
        if any(sk in tl for sk in skip_kws):
            sc -= 50
        for ak in action_kws:
            if ak in tl:
                sc += 15
        if 15.0 <= s_t <= duration * 0.75:
            sc += 5

        if sc > best_score:
            best_score = sc
            clip_dur = min(float(target_duration), max(18.0, span - 2.0))
            offset = 3.0 if span > (clip_dur + 6.0) else 0.0
            win_start = s_t + offset
            win_end = min(duration, win_start + clip_dur)
            if (win_end - win_start) >= 16.0:
                best_win = (win_start, win_end)
                best_title = title

    if best_win and best_score >= 10:
        print(f"[⚡ Chapter Engine] Capítulo de alta retención elegido ('{best_title}'): {best_win[0]:.1f}s - {best_win[1]:.1f}s")
        return best_win
    return None


def _pick_window_for_long_video(
    raw_d: float,
    heatmap: Any,
    srt_path: Optional[Path],
    trim_official_bumpers: bool,
    video_id: str,
    url: str,
    is_social_clip: bool,
    chapters: Any = None
) -> Optional[Tuple[float, float]]:
    """Determina la mejor ventana de 20-32s para clips o gameplays largos."""
    if trim_official_bumpers and 24.0 <= raw_d <= 45.0:
        win = (1.0, max(16.0, raw_d - 1.5))
        print(f"[*] Spot promocional oficial ({raw_d:.1f}s): conservando anuncio completo -> {win[0]:.1f}s a {win[1]:.1f}s")
        return win

    if raw_d <= SHORT_MAX_DURATION:
        return None

    viral_range = _select_heatmap_window(heatmap, raw_d, target_duration=min(SHORT_TARGET_DURATION, 24))
    if not viral_range and chapters and not trim_official_bumpers:
        viral_range = _select_action_chapter_window(chapters, raw_d, target_duration=min(SHORT_TARGET_DURATION, 24))
    if not viral_range and srt_path and srt_path.exists() and not trim_official_bumpers:
        viral_range = find_best_transcript_hook_window(
            srt_path,
            min_dur=max(GAMEPLAY_MIN_DURATION, 18),
            max_dur=min(SHORT_MAX_DURATION, 38),
            total_duration=raw_d,
        )
    if not viral_range:
        seed_val = sum(ord(c) for c in (video_id or url))
        sweet_min = max(GAMEPLAY_MIN_DURATION, 20)
        sweet_max = min(SHORT_MAX_DURATION, 26)
        dur_jitter = (seed_val % max(1, (sweet_max - sweet_min + 1)))
        dynamic_dur = sweet_min + dur_jitter
        if is_social_clip or raw_d <= 150.0:
            start_t = 0.0
        elif raw_d >= 300.0:
            # Saltar intros/cinemáticas iniciales en gameplays largos (entre 45s y 115s según semilla)
            start_t = min(raw_d * 0.14, 45.0 + float(seed_val % 70))
        else:
            start_t = min(25.0, raw_d * 0.12)
        if start_t + dynamic_dur > raw_d:
            start_t = max(0.0, raw_d - dynamic_dur)
        print(f"[*] Ventana orgánica de acción ({raw_d:.1f}s): {start_t:.1f}s a {start_t + dynamic_dur:.1f}s")
        viral_range = (start_t, start_t + dynamic_dur)

    if viral_range and srt_path and srt_path.exists() and not trim_official_bumpers:
        viral_range = snap_window_to_subtitles(
            srt_path=srt_path,
            v_start=viral_range[0],
            v_end=viral_range[1],
            min_duration=GAMEPLAY_MIN_DURATION,
            max_duration=min(SHORT_MAX_DURATION, 32)
        )
    return viral_range


def download_video_and_subtitles(
    url: str,
    video_id: str,
    source_lang: str = "es",
    trim_official_bumpers: bool = False
) -> Tuple[Optional[Path], Optional[Path], str]:
    """
    Descarga el video (4K VP9/1440p cuando ENABLE_4K_SHORTS está activo o 1080p),
    detecta picos virales ANTES de descargar vídeos largos (>90s) usando --download-sections
    para ahorrar ancho de banda/SSD, y sincroniza los subtítulos disponibles con el clip recortado.
    Retorna: (video_path, srt_path, detected_lang)
    """
    output_template = str(TEMP_DIR / f"{video_id}.%(ext)s")
    is_twitter_or_x = any(d in url.lower() for d in ["twitter.com", "x.com"])
    is_tiktok = "tiktok.com" in url.lower()
    is_social_clip = (is_twitter_or_x or is_tiktok)

    src_l = (source_lang or "es").strip().lower()
    audio_lang = "es" if src_l.startswith("es") else "en"
    max_h = 2160 if ENABLE_4K_SHORTS else 1080
    if is_social_clip:
        format_selector = f"best[ext=mp4]/bestvideo[height<={max_h}]+bestaudio/best"
    elif ENABLE_4K_SHORTS:
        # Priorizar 4K/1440p reales (VP9, excluyendo AV1 lento) antes de caer a 1080p avc1
        format_selector = (
            f"bestvideo[height>=1440][height<={max_h}][vcodec!^=av01]+bestaudio[language^={audio_lang}][ext=m4a]/"
            f"bestvideo[height>=1440][height<={max_h}][vcodec!^=av01]+bestaudio[ext=m4a]/"
            f"bestvideo[height>=1440][height<={max_h}][vcodec!^=av01]+bestaudio/"
            f"bestvideo[height<={max_h}][vcodec^=avc1]+bestaudio[language^={audio_lang}]/"
            f"bestvideo[height<={max_h}][vcodec!^=av01]+bestaudio[language^={audio_lang}]/"
            f"bestvideo[height<={max_h}][vcodec^=avc1]+bestaudio/"
            f"bestvideo[height<={max_h}][vcodec!^=av01]+bestaudio/"
            f"bestvideo[height<={max_h}]+bestaudio/"
            f"best[height<={max_h}]/best"
        )
    else:
        format_selector = (
            f"bestvideo[height<={max_h}][vcodec^=avc1]+bestaudio[language^={audio_lang}]/"
            f"bestvideo[height<={max_h}][vcodec!^=av01]+bestaudio[language^={audio_lang}]/"
            f"bestvideo[height<={max_h}]+bestaudio[language^={audio_lang}]/"
            f"bestvideo[height<={max_h}][vcodec^=avc1]+bestaudio/"
            f"bestvideo[height<={max_h}][vcodec!^=av01]+bestaudio/"
            f"bestvideo[height<={max_h}]+bestaudio/"
            f"best[height<={max_h}]/best"
        )

    detected_lang = source_lang
    srt_path: Optional[Path] = None
    remote_info: Dict[str, Any] = {}
    section_range: Optional[Tuple[float, float]] = None

    # Pre-inspección ligera en YouTube: abortar directos, bajar subtítulos antes y elegir sección en gameplays largos
    if not is_social_clip:
        remote_info = _inspect_remote_video_info(url)
        if remote_info.get("is_live") or remote_info.get("live_status") == "is_live":
            print(f"[!] Emisión en directo detectada para {video_id}. Abortando descarga infinita.")
            return None, None, "unknown"

        srt_path, detected_lang = _fetch_subtitles_yt(url, video_id, source_lang)
        remote_dur = float(remote_info.get("duration") or 0.0)
        if remote_dur > 90.0:
            section_range = _pick_window_for_long_video(
                raw_d=remote_dur,
                heatmap=remote_info.get("heatmap"),
                srt_path=srt_path,
                trim_official_bumpers=trim_official_bumpers,
                video_id=video_id,
                url=url,
                is_social_clip=False,
                chapters=remote_info.get("chapters")
            )

    def _cleanup_partial_downloads():
        for partial in TEMP_DIR.glob(f"{video_id}*"):
            if partial.suffix.lower() in (".part", ".ytdl", ".f315", ".f140") or ".part" in partial.name:
                partial.unlink(missing_ok=True)

    def _run_ytdlp_download(section_arg: Optional[Tuple[float, float]]) -> bool:
        extra_args = []
        if section_arg:
            s0 = max(0.0, round(section_arg[0], 2))
            s1 = max(s0 + 8.0, round(section_arg[1], 2))
            extra_args = ["--download-sections", f"*{s0:.2f}-{s1:.2f}"]
            print(f"[⚡ Fast Section] Descargando solo segmento {s0:.1f}s - {s1:.1f}s...")
        elif not is_social_clip and not remote_info:
            # Guardia SSD: si falló el inspector de duración remoto, limitar tamaño máx para no llenar el SSD con streams largos
            extra_args = ["--max-filesize", "800M"]

        cmd_attempts = []
        if not is_social_clip:
            cmd_attempts.append([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--no-playlist",
                "-f", format_selector,
                *extra_args,
                "--merge-output-format", "mp4",
                "-o", output_template,
                url
            ])
        cmd_attempts.append([
            sys.executable, "-m", "yt_dlp",
            "--force-ipv4",
            "--no-check-certificates",
            "--no-playlist",
            "-f", format_selector,
            *extra_args,
            "--merge-output-format", "mp4",
            "-o", output_template,
            url
        ])

        for attempt_idx, cmd in enumerate(cmd_attempts):
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90)
                return True
            except subprocess.TimeoutExpired:
                print(f"[!] Timeout de 90s descargando vídeo {url}.")
                _cleanup_partial_downloads()
            except subprocess.CalledProcessError as e:
                err_msg = e.stderr.strip() if e.stderr else str(e)
                print(f"[!] Intento {attempt_idx+1} falló al descargar vídeo {url}: {err_msg[:120]}")
                _cleanup_partial_downloads()
            except Exception as e:
                print(f"[!] Error inesperado descargando vídeo {url}: {e}")
                _cleanup_partial_downloads()
        return False

    print(f"[*] Descargando vídeo de {url}...")
    downloaded_by_section = False
    if section_range:
        downloaded_by_section = _run_ytdlp_download(section_range)
        if not downloaded_by_section:
            # Limpiar parciales antes de decidir fallback
            for partial in TEMP_DIR.glob(f"{video_id}*"):
                if partial.suffix.lower() in (".mp4", ".mkv", ".webm", ".part"):
                    partial.unlink(missing_ok=True)
            remote_dur = float(remote_info.get("duration") or 0.0)
            if remote_dur > 600.0:
                print(f"[!] Gameplay largo ({remote_dur:.0f}s) no soportó descarga parcial; abortando para proteger SSD/GaTDSEQ.")
                return None, None, "unknown"
            _run_ytdlp_download(None)
    else:
        _run_ytdlp_download(None)

    # Encontrar archivo de video
    video_path = TEMP_DIR / f"{video_id}.mp4"
    if not video_path.exists():
        matches = list(TEMP_DIR.glob(f"{video_id}.*"))
        for m in matches:
            if m.suffix.lower() in [".mp4", ".mkv", ".webm"]:
                video_path = m
                break

    if not video_path or not video_path.exists():
        print(f"[!] No se encontró ningún archivo de vídeo descargado para {video_id}.")
        return None, None, "unknown"

    # Si se descargó por sección parcial ya recortada (~15-58s), resincronizar SRT sin re-descargar ni re-encodear
    if downloaded_by_section and section_range:
        v_start, v_end = section_range
        if srt_path and srt_path.exists():
            trimmed_srt = TEMP_DIR / f"{video_id}_viral.srt"
            if slice_srt_file(srt_path, v_start, v_end, trimmed_srt):
                srt_path.unlink(missing_ok=True)
                srt_path = trimmed_srt
                print(f"[✓] Subtítulos resincronizados con sección viral -> {trimmed_srt.name}")
            else:
                srt_path.unlink(missing_ok=True)
                srt_path = None
        return video_path, srt_path, detected_lang

    # Paso 3 (videos completos locales <= 10 min o redes sociales): recorte por ffmpeg
    if video_path and video_path.exists():
        raw_d = 0.0
        try:
            p_dur = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
                capture_output=True, text=True, timeout=10
            )
            raw_d = float(p_dur.stdout.strip()) if p_dur.stdout.strip() else 0.0
        except Exception:
            raw_d = 0.0

        viral_range = _pick_window_for_long_video(
            raw_d=raw_d,
            heatmap=remote_info.get("heatmap"),
            srt_path=srt_path,
            trim_official_bumpers=trim_official_bumpers,
            video_id=video_id,
            url=url,
            is_social_clip=is_social_clip,
            chapters=remote_info.get("chapters")
        )
        if viral_range:
            v_start, v_end = viral_range

            trimmed_video = TEMP_DIR / f"{video_id}_viral.mp4"
            print(f"[*] Recortando clip dinámico ({v_start:.1f}s a {v_end:.1f}s, duración: {v_end - v_start:.1f}s)...")
            
            # Seek híbrido en dos pasos con timestamps estabilizados:
            # Evita decodificar 10+ minutos de vídeo por CPU desde 0.0s (coexistencia GaTDSEQ)
            fast_seek = max(0.0, round(v_start - 10.0, 3))
            inner_ss = max(0.0, round(v_start - fast_seek, 3))
            clip_dur = max(1.0, round(v_end - v_start, 3))
            n_threads = str(get_ffmpeg_threads())
            cmd_trim = [
                "ffmpeg", "-y",
                "-threads", n_threads,
                "-ss", str(fast_seek),
                "-accurate_seek",
                "-i", str(video_path),
                "-ss", str(inner_ss),
                "-avoid_negative_ts", "make_zero",
                "-t", str(clip_dur),
                "-threads", n_threads,
                "-c:v", FFMPEG_VIDEO_CODEC,
                "-b:v", "18M" if ENABLE_4K_SHORTS else "8M",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                str(trimmed_video)
            ]
            try:
                subprocess.run(cmd_trim, check=True, capture_output=True, timeout=120)
                # Verificar duración real del archivo recortado con ffprobe antes de descartar el original
                trimmed_dur = 0.0
                if trimmed_video.exists():
                    try:
                        probe_res = subprocess.run(
                            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(trimmed_video)],
                            capture_output=True, text=True, timeout=8
                        )
                        trimmed_dur = float(probe_res.stdout.strip()) if probe_res.stdout.strip() else 0.0
                    except Exception:
                        trimmed_dur = 0.0

                # Validar que el clip no haya quedado truncado anómalamente (debe ser al menos 80% del clip solicitado o min 8s)
                min_acceptable_dur = min(8.0, clip_dur * 0.75)
                if trimmed_video.exists() and trimmed_dur >= min_acceptable_dur:
                    video_path.unlink()  # Eliminar archivo largo pesado de forma segura
                    video_path = trimmed_video
                    print(f"[✓] Vídeo recortado al pico de máxima retención ({trimmed_dur:.1f}s) -> {trimmed_video.name}")

                    # Recortar y sincronizar SRT si existe
                    if srt_path and srt_path.exists():
                        trimmed_srt = TEMP_DIR / f"{video_id}_viral.srt"
                        if slice_srt_file(srt_path, v_start, v_end, trimmed_srt):
                            srt_path.unlink()
                            srt_path = trimmed_srt
                            print(f"[✓] Subtítulos resincronizados con el clip viral -> {trimmed_srt.name}")
                        else:
                            print("[!] El segmento recortado no contiene subtítulos válidos; descartando SRT completo para evitar desfase.")
                            srt_path.unlink(missing_ok=True)
                            srt_path = None
                else:
                    print(f"[!] Recorte inválido o duración anómala ({trimmed_dur:.2f}s).")
                    if trimmed_video.exists():
                        trimmed_video.unlink()
                    if raw_d > 65.0:
                        print(f"[!] Abortando entrega de vídeo largo ({raw_d:.1f}s) sin recortar para proteger el render.")
                        video_path.unlink(missing_ok=True)
                        return None, srt_path, detected_lang
            except Exception as e:
                print(f"[!] No se pudo recortar con VideoToolbox: {e}")
                if raw_d > 65.0:
                    video_path.unlink(missing_ok=True)
                    return None, srt_path, detected_lang

    return (video_path if video_path and video_path.exists() else None, srt_path, detected_lang)

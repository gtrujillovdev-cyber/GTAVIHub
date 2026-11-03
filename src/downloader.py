import sys
import os
import re
import glob
import json
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from .config import TEMP_DIR, get_ffmpeg_threads, SHORT_MIN_DURATION, SHORT_MAX_DURATION, SHORT_TARGET_DURATION

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

        if best_start < 4.0:
            best_start = 0.0

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
                    score -= 4.0
                if has_subsequent_pause:
                    score -= 2.0

                candidate_ends.append((score, c["end"]))

        if candidate_ends:
            candidate_ends.sort(key=lambda x: x[0])
            best_end = candidate_ends[0][1]
            print(f"[✓ Subtitle Snapping] Segmento ajustado a frase: {best_start:.1f}s a {best_end:.1f}s (Duración natural: {best_end - best_start:.1f}s)")
            return (round(best_start, 2), round(best_end, 2))

    except Exception as e:
        print(f"[!] Error en snapping de subtítulos: {e}")

    return v_start, v_end

def find_viral_heatmap_segment(
    url: str,
    min_duration: int = SHORT_MIN_DURATION,
    max_duration: int = SHORT_MAX_DURATION,
    target_duration: int = SHORT_TARGET_DURATION,
    video_id: str = ""
) -> Optional[Tuple[float, float]]:
    """
    Analiza el mapa de calor de YouTube ('most replayed' heatmap) con yt-dlp
    para encontrar una ventana dinámica (26-52s) de máxima retención y engagement.
    Si el vídeo original ya es corto (<= 58s), preserva su duración original sin recortar.
    """
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--impersonate", "chrome",
            "--skip-download",
            "--dump-single-json",
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if res.returncode != 0:
            return None
        info = json.loads(res.stdout)
        duration = info.get("duration", 0)

        # Si ya es un vídeo corto optimizado (<= 60 segundos), NUNCA recortar:
        # Se respeta íntegramente la duración orgánica del creador para no cortar frases a la mitad.
        if duration <= 60:
            print(f"[*] Vídeo ya en formato Short orgánico ({duration:.1f}s <= 60s). Duración original preservada (cero cortes).")
            return None

        heatmap = info.get("heatmap")
        if heatmap and isinstance(heatmap, list) and len(heatmap) > 5:
            # Duraciones candidatas adaptativas alineadas con el arco narrativo (16s a 42s)
            candidate_durations = [16, 20, 24, 28, 34, 42]
            best_score = -1.0
            best_start = 15.0
            best_dur = target_duration

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
                    avg_val = sum(window_pts) / len(window_pts)
                    peak_val = max(window_pts)
                    # Score ponderado adaptativo: premia picos y modula según retención orgánica
                    window_score = avg_val * (1 + peak_val * 0.4) * (24 / max(c_dur, 16))
                    if window_score > best_score:
                        best_score = window_score
                        best_start = start_t
                        best_dur = c_dur

            print(f"[⚡ Heatmap Detector] Pico viral detectado: {best_start:.1f}s a {best_start + best_dur:.1f}s (Duración: {best_dur}s, Score ponderado: {best_score:.3f})")
            return (best_start, best_start + best_dur)
        else:
            # Vídeo largo sin heatmap: saltar intro y aplicar duración orgánica determinista anti-robot
            seed_val = sum(ord(c) for c in (video_id or url))
            dur_jitter = (seed_val % (max_duration - min_duration + 1))
            dynamic_dur = min_duration + dur_jitter
            start_t = min(20.0, duration * 0.1)
            print(f"[*] Vídeo largo ({duration}s) sin heatmap. Segmento dinámico orgánico: {start_t:.1f}s a {start_t + dynamic_dur:.1f}s ({dynamic_dur}s)...")
            return (start_t, start_t + dynamic_dur)
    except Exception as e:
        print(f"[!] Info detector: {e}")
        return None

def download_video_and_subtitles(
    url: str,
    video_id: str,
    source_lang: str = "es"
) -> Tuple[Optional[Path], Optional[Path], str]:
    """
    Descarga el video (limitado a 1080p), detecta picos virales si es largo (>60s)
    y extrae los subtítulos disponibles sincronizados con el clip recortado.
    Retorna: (video_path, srt_path, detected_lang)
    """
    output_template = str(TEMP_DIR / f"{video_id}.%(ext)s")
    
    # Paso 1: Descargar vídeo limpio
    cmd_video = [
        sys.executable, "-m", "yt_dlp",
        "--impersonate", "chrome",
        "--no-check-certificates",
        "--no-playlist",
        "-f", "bestvideo[height<=1440]+bestaudio/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url
    ]

    print(f"[*] Descargando vídeo de {url}...")
    try:
        subprocess.run(cmd_video, check=True, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        print(f"[!] Timeout de 90s descargando vídeo {url}. Abortando para no bloquear el pipeline.")
        return None, None, "unknown"
    except subprocess.CalledProcessError as e:
        print(f"[!] Error al descargar vídeo {url}: {e.stderr.strip() if e.stderr else e}")
        return None, None, "unknown"
    except Exception as e:
        print(f"[!] Error inesperado descargando vídeo {url}: {e}")
        return None, None, "unknown"

    # Encontrar archivo de video
    video_path = TEMP_DIR / f"{video_id}.mp4"
    if not video_path.exists():
        matches = list(TEMP_DIR.glob(f"{video_id}.*"))
        for m in matches:
            if m.suffix.lower() in [".mp4", ".mkv", ".webm"]:
                video_path = m
                break

    # Paso 2: Intentar descargar subtítulos (español o inglés nativo/auto)
    sub_output_template = str(TEMP_DIR / f"{video_id}.%(ext)s")
    sub_langs_to_try = [
        ("es", ["es-orig", "es"]),
        ("en", ["en-orig", "en"])
    ]

    detected_lang = source_lang
    srt_path = None

    for lang_code, lang_candidates in sub_langs_to_try:
        if srt_path:
            break
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
                    srt_path = chosen
                    clean_and_deroll_srt(srt_path)
                    detected_lang = lang_code
                    print(f"[*] Subtítulos descargados con éxito ({target_lang} -> {detected_lang})")
                    break
            except Exception:
                continue

    # Paso 3: Análisis de picos virales si el vídeo es largo (> 58s)
    if video_path and video_path.exists():
        viral_range = find_viral_heatmap_segment(
            url,
            min_duration=SHORT_MIN_DURATION,
            max_duration=SHORT_MAX_DURATION,
            target_duration=SHORT_TARGET_DURATION,
            video_id=video_id
        )
        if viral_range:
            v_start, v_end = viral_range

            # Paso 3b: Ajuste inteligente por frases/subtítulos para evitar cortes a media palabra
            if srt_path and srt_path.exists():
                v_start, v_end = snap_window_to_subtitles(
                    srt_path=srt_path,
                    v_start=v_start,
                    v_end=v_end,
                    min_duration=SHORT_MIN_DURATION,
                    max_duration=SHORT_MAX_DURATION
                )

            trimmed_video = TEMP_DIR / f"{video_id}_viral.mp4"
            print(f"[*] Recortando clip dinámico ({v_start:.1f}s a {v_end:.1f}s, duración: {v_end - v_start:.1f}s)...")
            
            # Recorte preciso frame-accurate con aceleración VideoToolbox (input antes de seek para evitar desync de keyframe con SRT)
            cmd_trim = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-ss", str(v_start),
                "-to", str(v_end),
                "-threads", str(get_ffmpeg_threads()),
                "-c:v", "h264_videotoolbox",
                "-b:v", "8M",
                "-c:a", "aac",
                "-b:a", "192k",
                str(trimmed_video)
            ]
            try:
                subprocess.run(cmd_trim, check=True, capture_output=True)
                if trimmed_video.exists():
                    video_path.unlink()  # Eliminar archivo largo pesado
                    video_path = trimmed_video
                    print(f"[✓] Vídeo recortado al pico de máxima retención -> {trimmed_video.name}")

                    # Recortar y sincronizar SRT si existe
                    if srt_path and srt_path.exists():
                        trimmed_srt = TEMP_DIR / f"{video_id}_viral.srt"
                        if slice_srt_file(srt_path, v_start, v_end, trimmed_srt):
                            srt_path.unlink()
                            srt_path = trimmed_srt
                            print(f"[✓] Subtítulos resincronizados con el clip viral -> {trimmed_srt.name}")
            except Exception as e:
                print(f"[!] No se pudo recortar con VideoToolbox: {e}")

    return (video_path if video_path and video_path.exists() else None, srt_path, detected_lang)

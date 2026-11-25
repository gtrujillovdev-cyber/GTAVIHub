"""
src/guide_story_compiler.py — Compilador Multi-Beat de Guías desde Vídeos Largos 16:9
====================================================================================
Transforma guías largas horizontales (2–15 min) en Shorts estilo Caspahz de 4 actos:
  1. REWARD HOOK (4–6s): Muestra la recompensa/coche/arma en acción desde el segundo 0.
  2. MAP LOCATION (6–9s): Corte al mapa mostrando la ubicación exacta en Leonida.
  3. ACTION STEPS (10–16s): 1–2 cortes rápidos de llegada/entrada/acción clave.
  4. CLAIM & PAYOFF (8–12s): Recogida o conducción final + cierre limpio.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import TEMP_DIR
from .translator import (
    clean_srt_response,
    generate_content_with_retry,
    get_gemini_client,
    sanitize_banned_words,
)
from .video_editor import is_quant_busy


def _parse_vtt_to_segments(vtt_path: Path) -> List[Dict[str, Any]]:
    """Convierte un archivo .vtt de yt-dlp en segmentos [{start, end, text}]."""
    if not vtt_path.exists():
        return []
    raw = vtt_path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", raw)
    segments: List[Dict[str, Any]] = []
    time_re = re.compile(r"(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->\s*(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})")

    def _to_sec(h: Optional[str], m: str, s: str, ms: str) -> float:
        hh = int(h.rstrip(":")) if h else 0
        return hh * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    last_txt = ""
    for blk in blocks:
        lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
        if not lines:
            continue
        m = None
        txt_lines = []
        for ln in lines:
            if not m:
                tm = time_re.search(ln)
                if tm:
                    m = tm
                    continue
            else:
                clean_ln = re.sub(r"<[^>]+>", "", ln).strip()
                if clean_ln:
                    txt_lines.append(clean_ln)
        if not m or not txt_lines:
            continue
        start_s = _to_sec(m.group(1), m.group(2), m.group(3), m.group(4))
        end_s = _to_sec(m.group(5), m.group(6), m.group(7), m.group(8))
        txt = " ".join(txt_lines)
        txt = re.sub(r"\s+", " ", txt).strip()
        if not txt or txt == last_txt:
            continue
        last_txt = txt
        segments.append({"start": round(start_s, 2), "end": round(end_s, 2), "text": txt})
    return segments


def fetch_long_guide_context(url: str, video_id: str, work_dir: Path = TEMP_DIR) -> Dict[str, Any]:
    """Obtiene metadatos, capítulos y transcripción con timestamps vía yt-dlp."""
    work_dir.mkdir(parents=True, exist_ok=True)
    sub_prefix = work_dir / f"guide_ctx_{video_id}"
    cmd = [
        "python3", "-m", "yt_dlp",
        "--skip-download",
        "--write-auto-sub", "--write-sub",
        "--sub-lang", "en,es",
        "--sub-format", "vtt",
        "--dump-single-json",
        "-o", str(sub_prefix),
        url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    info = {}
    if res.returncode == 0 and res.stdout.strip():
        try:
            info = json.loads(res.stdout.strip().splitlines()[-1])
        except Exception:
            info = {}

    vtt_files = sorted(work_dir.glob(f"guide_ctx_{video_id}*.vtt"))
    segments: List[Dict[str, Any]] = []
    for vf in vtt_files:
        segments = _parse_vtt_to_segments(vf)
        try:
            vf.unlink(missing_ok=True)
        except Exception:
            pass
        if segments:
            break

    return {
        "title": info.get("title", ""),
        "duration": float(info.get("duration") or 0),
        "uploader": info.get("uploader") or info.get("channel") or "",
        "chapters": info.get("chapters") or [],
        "segments": segments,
    }


def plan_multi_beat_guide(
    title: str,
    duration: float,
    chapters: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Usa Gemini para diseñar un storyboard de 4 actos (32–44s totales) desde un vídeo largo 16:9
    + guion narrado en español estilo Caspahz (recompensa primero, sin preguntas retóricas).
    """
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return None

    # Compactar transcripción para el prompt (máx ~120 líneas)
    step = max(1, len(segments) // 120) if segments else 1
    sampled = segments[::step][:120]
    transcript_txt = "\n".join(f"[{s['start']:.1f}s-{s['end']:.1f}s] {s['text']}" for s in sampled)
    chapters_txt = "\n".join(
        f"[{c.get('start_time', 0):.1f}s-{c.get('end_time', 0):.1f}s] {c.get('title', '')}"
        for c in (chapters or [])[:20]
    )

    prompt = f"""Eres editor jefe de Shorts virales de GTA 6 estilo Caspahz.
Tienes un vídeo largo horizontal 16:9 titulado: "{title}" (duración total: {duration:.0f}s).

CAPÍTULOS:
{chapters_txt or "(Sin capítulos)"}

TRANSCRIPCIÓN CON TIMESTAMPS:
{transcript_txt or "(Sin transcripción; reparte los 4 actos coherentemente dentro de la duración)"}

TAREA:
Construye una MINI-GUÍA COMPLETA de 4 actos (4 cortes de distintos momentos del vídeo largo) que sumen entre 32 y 42 segundos totales:
1. Acto 1 "reward_hook" (4-6s): El momento donde ya se ve la RECOMPENSA final (el coche, arma o dinero). La narración anuncia DIRECTAMENTE qué consigues (PROHIBIDO hacer preguntas).
2. Acto 2 "map_location" (6-9s): El momento donde se muestra el MAPA o ubicación exacta en Leonida/Vice City.
3. Acto 3 "action_steps" (10-15s): El paso clave (entrada, guardia, truco, ubicación dentro de la zona).
4. Acto 4 "claim_payoff" (8-12s): Recogida de la recompensa o conducción final.

REGLAS ESTRICTAS:
- Cada beat debe tener 0 <= start_sec < end_sec <= {max(10.0, duration - 1.0):.1f}, con duración entre 4.0s y 15.0s.
- El texto `narration_es` de cada acto debe ser español natural de España, conciso (12-26 palabras por acto, ~2.6 palabras/seg), directo y sin palabras prohibidas (usa "recompensa" o "mercancía" en vez de drogas/cocaína).

Responde SOLO JSON válido:
{{
  "short_title_es": "TÍTULO VIRAL EN MAYÚSCULAS SIN HASHTAGS",
  "cover_line1": "1 PALABRA BLANCA (ej: BUGATTI, ARMA, DINERO)",
  "cover_line2": "1-2 PALABRAS ACENTO (ej: GRATIS, OCULTA, +$500K)",
  "beats": [
    {{"act": "reward_hook", "start_sec": 0.0, "end_sec": 5.0, "narration_es": "..."}},
    {{"act": "map_location", "start_sec": 0.0, "end_sec": 7.0, "narration_es": "..."}},
    {{"act": "action_steps", "start_sec": 0.0, "end_sec": 12.0, "narration_es": "..."}},
    {{"act": "claim_payoff", "start_sec": 0.0, "end_sec": 10.0, "narration_es": "..."}}
  ]
}}"""

    client = get_gemini_client()
    resp = generate_content_with_retry(
        client=client,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    data = json.loads(clean_srt_response(resp.text or "{}"))
    beats = data.get("beats") or []
    valid_beats: List[Dict[str, Any]] = []
    for b in beats:
        s = max(0.0, float(b.get("start_sec", 0)))
        e = min(max(duration - 0.5, s + 4.0), float(b.get("end_sec", s + 5.0)))
        if e - s < 3.5:
            e = min(duration, s + 4.5)
        if e - s > 15.0:
            e = s + 14.0
        nar = sanitize_banned_words(str(b.get("narration_es", "")).strip())
        if nar and e > s + 2.0:
            valid_beats.append({
                "act": b.get("act", "step"),
                "start_sec": round(s, 2),
                "end_sec": round(e, 2),
                "narration_es": nar,
            })
    if len(valid_beats) < 3:
        return None
    data["beats"] = valid_beats
    data["short_title_es"] = sanitize_banned_words(str(data.get("short_title_es") or title))
    return data


def compile_multi_beat_video(
    source_video: Path,
    beats: List[Dict[str, Any]],
    compiled_video_path: Path,
    srt_output_path: Path,
) -> Tuple[bool, Optional[Path]]:
    """
    Corta los N tramos de `source_video` y los concatena en `compiled_video_path`,
    generando también el archivo `.srt` sincronizado con la narración por acto.
    """
    if not source_video.exists() or not beats:
        return False, None

    threads = "1" if is_quant_busy() else "2"
    vcodec = "h264_videotoolbox" if os.uname().sysname == "Darwin" else "libx264"

    # Detectar si tiene audio
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(source_video)],
        capture_output=True, text=True, timeout=8,
    )
    has_audio = bool(probe.stdout.strip())

    inputs: List[str] = []
    v_filters: List[str] = []
    concat_inputs: List[str] = []
    srt_lines: List[str] = []
    cur_t = 0.0

    def _fmt_srt(sec: float) -> str:
        ms = int(round((sec % 1) * 1000))
        tot = int(sec)
        return f"{tot // 3600:02d}:{(tot % 3600) // 60:02d}:{tot % 60:02d},{ms:03d}"

    for idx, b in enumerate(beats):
        s = float(b["start_sec"])
        e = float(b["end_sec"])
        dur = e - s
        inputs.extend(["-ss", f"{s:.2f}", "-t", f"{dur:.2f}", "-i", str(source_video)])
        v_filters.append(f"[{idx}:v]setpts=PTS-STARTPTS,setsar=1[v{idx}]")
        if has_audio:
            v_filters.append(f"[{idx}:a]asetpts=PTS-STARTPTS[a{idx}]")
            concat_inputs.append(f"[v{idx}][a{idx}]")
        else:
            concat_inputs.append(f"[v{idx}]")

        srt_lines.append(f"{idx + 1}\n{_fmt_srt(cur_t)} --> {_fmt_srt(cur_t + dur)}\n{b['narration_es']}\n")
        cur_t += dur

    n = len(beats)
    if has_audio:
        fc = ";".join(v_filters) + f";{''.join(concat_inputs)}concat=n={n}:v=1:a=1[vout][aout]"
        maps = ["-map", "[vout]", "-map", "[aout]", "-c:v", vcodec, "-b:v", "10M", "-c:a", "aac", "-b:a", "192k"]
    else:
        fc = ";".join(v_filters) + f";{''.join(concat_inputs)}concat=n={n}:v=1:a=0[vout]"
        maps = ["-map", "[vout]", "-c:v", vcodec, "-b:v", "10M"]

    cmd = ["ffmpeg", "-y", "-threads", threads, *inputs, "-filter_complex", fc, *maps, "-movflags", "+faststart", str(compiled_video_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0 or not compiled_video_path.exists():
        print(f"[GuideCompiler] Error FFmpeg concat: {res.stderr[-300:]}")
        return False, None

    srt_output_path.write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"[✓ GuideCompiler] Compilado Multi-Beat ({n} actos, {cur_t:.1f}s) -> {compiled_video_path.name}")
    return True, srt_output_path

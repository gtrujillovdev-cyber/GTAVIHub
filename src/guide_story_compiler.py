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
import sys
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
        sys.executable, "-m", "yt_dlp",
        "--impersonate", "chrome",
        "--no-check-certificates",
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


def extract_visual_storyboard_frames(
    source_video: Path,
    duration: float,
    num_frames: int = 14,
    work_dir: Path = TEMP_DIR,
) -> List[Tuple[float, Path]]:
    """
    Extrae `num_frames` fotogramas ligeros (480x270) repartidos a lo largo de `source_video`
    con su timestamp exacto para que Gemini Vision VEA el vídeo real antes de planificar los cortes.
    """
    if not source_video or not Path(source_video).exists() or duration < 10.0:
        return []
    work_dir.mkdir(parents=True, exist_ok=True)
    frames: List[Tuple[float, Path]] = []
    start_t = max(1.0, duration * 0.03)
    end_t = max(start_t + 2.0, duration * 0.96)
    step = (end_t - start_t) / max(1, num_frames - 1)
    for i in range(num_frames):
        ts = round(start_t + i * step, 1)
        out_jpg = work_dir / f"_sb_{os.getpid()}_{i:02d}.jpg"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", f"{ts:.2f}", "-i", str(source_video),
                    "-frames:v", "1", "-vf", "scale=480:270:force_original_aspect_ratio=decrease",
                    "-q:v", "5", str(out_jpg),
                ],
                capture_output=True,
                timeout=8,
            )
            if out_jpg.exists() and out_jpg.stat().st_size > 1000:
                frames.append((ts, out_jpg))
        except Exception:
            continue
    return frames


def plan_multi_beat_guide(
    title: str,
    duration: float,
    chapters: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
    source_video: Optional[Path] = None,
    work_dir: Path = TEMP_DIR,
) -> Optional[Dict[str, Any]]:
    """
    Usa Gemini Vision (cuando `source_video` está disponible) para diseñar un storyboard
    de 4 actos estilo Caspahz 100% alineado visualmente (guion describe lo que REALMENTE sale en pantalla):
      1. reward_hook (2.8-4.0s): Recompensa visible en gameplay 3D.
      2. map_location (2.0-3.0s MÁX): Flash rápido y dinámico del mapa/ubicación (nunca estático 6-8s).
      3. action_steps (4.5-6.5s): Paso exacto en gameplay 3D.
      4. claim_payoff (4.5-6.5s): Recogida/uso final + CTA corto de guardado.
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

    storyboard_frames: List[Tuple[float, Path]] = []
    if source_video and Path(source_video).exists():
        storyboard_frames = extract_visual_storyboard_frames(source_video, duration, num_frames=14, work_dir=work_dir)

    prompt = f"""Eres editor jefe de Shorts virales de GTA 6 estilo Caspahz (ingeniería inversa exacta de edición).
Tienes un vídeo de guía titulado: "{title}" (duración total: {duration:.0f}s).

CAPÍTULOS:
{chapters_txt or "(Sin capítulos)"}

TRANSCRIPCIÓN CON TIMESTAMPS:
{transcript_txt or "(Sin transcripción; guíate directamente por los fotogramas reales adjuntos)"}

TAREA:
Construye una MINI-GUÍA COMPLETA de 4 actos (4 cortes reales del vídeo) que sumen entre 17 y 23 segundos totales.
CADA ACTO DEBE COINCIDIR 100% VISUALMENTE CON LOS FOTOGRAMAS REALES ADJUNTOS (el guion SOLO puede describir lo que realmente ocurre en ese timestamp):

1. Acto 1 "reward_hook" (3.0-4.0s): Elige el timestamp donde se ve CLARAMENTE la recompensa principal (el coche, arma o dinero) en gameplay 3D. Guion: 1 frase directa (8-12 palabras, PROHIBIDO hacer preguntas) describiendo esa recompensa visible.
2. Acto 2 "map_location" (2.0-3.0s MÁXIMO ESTRICTO): Elige el timestamp exacto donde aparece el MAPA con la ubicación. Si no hay mapa en ningún fotograma, usa la llegada a la zona. Guion ultra-corto (6-9 palabras máximo, ej: "Ve a este punto exacto del mapa.") para que el mapa NUNCA se quede estático más de 3 segundos.
3. Acto 3 "action_steps" (4.5-6.5s): Elige el timestamp donde el jugador entra o ejecuta la acción clave en gameplay 3D. Narra exactamente lo que se ve hacer al jugador (11-16 palabras).
4. Acto 4 "claim_payoff" (4.5-6.5s): Elige el timestamp donde recoge/sube/conduce la recompensa, cerrando con CTA corto de guardado (ej: "Guárdalo para cuando juegues.").

REGLAS ESTRICTAS:
- Cada beat debe tener 0 <= start_sec < end_sec <= {max(8.0, duration - 0.5):.1f}.
- Acto 2 ("map_location") DEBE durar entre 2.0s y 3.0s (NUNCA más de 3.2s).
- PROHIBIDO elegir tramos con menús de pausa, pantallas de estadísticas/tablas de vehículos, sliders horizontales o pantallas de carga en los actos 1, 3 y 4; esos 3 actos deben ser SIEMPRE gameplay 3D en movimiento.
- El texto `narration_es` debe ser español natural de España, fiel a lo que sale en pantalla, y sin palabras prohibidas (usa "recompensa" o "mercancía" en vez de drogas/cocaína).

Responde SOLO JSON válido:
{{
  "short_title_es": "TÍTULO VIRAL EN MAYÚSCULAS SIN HASHTAGS",
  "cover_line1": "1 PALABRA BLANCA (ej: EMERUS, ARMA, DINERO)",
  "cover_line2": "1-2 PALABRAS ACENTO (ej: GRATIS, OCULTA, +$17K)",
  "beats": [
    {{"act": "reward_hook", "start_sec": 0.0, "end_sec": 3.5, "narration_es": "..."}},
    {{"act": "map_location", "start_sec": 0.0, "end_sec": 2.6, "narration_es": "..."}},
    {{"act": "action_steps", "start_sec": 0.0, "end_sec": 5.5, "narration_es": "..."}},
    {{"act": "claim_payoff", "start_sec": 0.0, "end_sec": 5.5, "narration_es": "..."}}
  ]
}}"""

    client = get_gemini_client()
    try:
        if storyboard_frames:
            from google.genai import types
            contents: Any = [prompt]
            for ts, jpg_path in storyboard_frames:
                contents.append(f"[Fotograma en t={ts:.1f}s]")
                contents.append(types.Part.from_bytes(data=jpg_path.read_bytes(), mime_type="image/jpeg"))
            print(f"[GuideCompiler] Planificando 4 actos con Gemini Vision ({len(storyboard_frames)} fotogramas reales)...")
        else:
            contents = prompt

        resp = generate_content_with_retry(
            client=client,
            contents=contents,
            config={"response_mime_type": "application/json"},
        )
    finally:
        for _, jpg_path in storyboard_frames:
            jpg_path.unlink(missing_ok=True)

    data = json.loads(clean_srt_response(resp.text or "{}"))
    beats = data.get("beats") or []
    valid_beats: List[Dict[str, Any]] = []
    for b in beats:
        act_name = str(b.get("act", "step")).lower()
        is_map = "map" in act_name
        s = max(0.0, float(b.get("start_sec", 0)))
        default_len = 2.6 if is_map else 5.0
        e = min(max(duration - 0.3, s + default_len), float(b.get("end_sec", s + default_len)))
        if is_map:
            if e - s < 2.0:
                e = min(duration, s + 2.5)
            if e - s > 3.2:
                e = s + 3.0
        else:
            if e - s < 3.0:
                e = min(duration, s + 4.0)
            if e - s > 10.0:
                e = s + 8.0
        nar = sanitize_banned_words(str(b.get("narration_es", "")).strip())
        if nar and e > s + 1.8:
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
        act_name = str(b.get("act") or "").lower()
        inputs.extend(["-ss", f"{s:.2f}", "-t", f"{dur:.2f}", "-i", str(source_video)])
        if "map" in act_name:
            # Zoom suave 1.00 -> 1.08 para que el mapa sea dinámico (nunca imagen congelada)
            v_filters.append(
                f"[{idx}:v]setpts=PTS-STARTPTS,"
                f"scale=iw*1.08:ih*1.08,"
                f"crop=iw/1.08:ih/1.08:(iw-ow)/2*(1-min(1\\,t/{max(dur, 1.0):.2f})):(ih-oh)/2,"
                f"setsar=1[v{idx}]"
            )
        else:
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


def sync_beats_with_voiceover(
    beats: List[Dict[str, Any]],
    source_duration: float,
    output_audio_path: Path,
    work_dir: Path = TEMP_DIR,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Sintetiza la locución de cada acto por separado y ajusta la duración de cada corte
    de vídeo para que coincida exactamente con su voz (cero huecos mudos al final o en medio).
    """
    import asyncio
    from .dubber import DEFAULT_TTS_VOICE, VOICE_ENHANCER_CHAIN, _probe_audio_duration, _synthesize_async

    if not beats:
        return beats, False

    tts_rate = os.getenv("TTS_RATE", "+14%")
    tts_pitch = os.getenv("TTS_PITCH", "+2Hz")
    enable_enhancer = os.getenv("ENABLE_VOICE_ENHANCER", "true").lower() in ("true", "1", "yes")
    tmp_parts: List[Path] = []
    synced_beats: List[Dict[str, Any]] = []

    try:
        for idx, b in enumerate(beats):
            nar = str(b.get("narration_es") or "").strip()
            if not nar:
                continue
            raw_mp3 = work_dir / f"_beat_tts_{idx}_{output_audio_path.stem}.mp3"
            padded_mp3 = work_dir / f"_beat_pad_{idx}_{output_audio_path.stem}.mp3"
            asyncio.run(_synthesize_async(nar, raw_mp3, DEFAULT_TTS_VOICE, rate=tts_rate, pitch=tts_pitch))
            tts_dur = _probe_audio_duration(raw_mp3)
            if tts_dur <= 0.5:
                continue

            act_name = str(b.get("act") or "").lower()
            is_map_act = "map" in act_name
            if idx == len(beats) - 1:
                pad_tail = 0.08  # Corte en seco final para bucle instantáneo (>100% completion rate)
            elif is_map_act:
                pad_tail = 0.14
            else:
                pad_tail = 0.20 if idx == 0 else 0.24

            # Tope estricto para mapa: 2.0s - 3.2s (flash rápido estilo Caspahz, jamás 6-8s congelados)
            atempo_prefix = ""
            if is_map_act:
                if tts_dur > 3.05:
                    spd = min(1.35, round((tts_dur + 0.12) / 3.10, 2))
                    atempo_prefix = f"atempo={spd},"
                    tts_dur = tts_dur / spd
                target_dur = max(2.0, min(3.2, tts_dur + pad_tail))
            else:
                target_dur = max(3.2, tts_dur + pad_tail)
            s = float(b["start_sec"])
            max_avail = max(2.5, float(source_duration or 600.0) - s - 0.2)
            if target_dur > max_avail:
                target_dur = max_avail

            # Ajustar audio exacto a target_dur con silencio de cola si hace falta
            af = f"{atempo_prefix}apad=whole_dur={target_dur:.3f}"
            if enable_enhancer:
                af = f"{VOICE_ENHANCER_CHAIN},{af}"
            cmd_p = [
                "ffmpeg", "-y", "-i", str(raw_mp3),
                "-af", af, "-t", f"{target_dur:.3f}",
                "-c:a", "libmp3lame", "-b:a", "192k", str(padded_mp3),
            ]
            r = subprocess.run(cmd_p, capture_output=True, timeout=30)
            if r.returncode != 0 or not padded_mp3.exists():
                cmd_p2 = [
                    "ffmpeg", "-y", "-i", str(raw_mp3),
                    "-af", f"apad=whole_dur={target_dur:.3f}", "-t", f"{target_dur:.3f}",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(padded_mp3),
                ]
                subprocess.run(cmd_p2, capture_output=True, timeout=30)
            raw_mp3.unlink(missing_ok=True)
            if padded_mp3.exists():
                tmp_parts.append(padded_mp3)
                synced_beats.append({
                    **b,
                    "start_sec": round(s, 2),
                    "end_sec": round(s + target_dur, 2),
                })

        if not tmp_parts:
            return beats, False

        concat_inputs = []
        filter_parts = []
        for i, p in enumerate(tmp_parts):
            concat_inputs.extend(["-i", str(p)])
            filter_parts.append(f"[{i}:a]")
        fc = f"{''.join(filter_parts)}concat=n={len(tmp_parts)}:v=0:a=1[aout]"
        cmd_cat = [
            "ffmpeg", "-y", *concat_inputs, "-filter_complex", fc,
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", str(output_audio_path),
        ]
        res_cat = subprocess.run(cmd_cat, capture_output=True, timeout=45)
        ok = res_cat.returncode == 0 and output_audio_path.exists()
        if ok:
            total_d = sum(float(x["end_sec"]) - float(x["start_sec"]) for x in synced_beats)
            print(f"[✓ GuideCompiler] Voz sincronizada por acto ({len(synced_beats)} actos, {total_d:.1f}s continuos sin huecos mudos).")
        return synced_beats, ok
    finally:
        for p in tmp_parts:
            p.unlink(missing_ok=True)


def _measure_segment_motion_and_ui(
    source_video: Path,
    start_sec: float,
    dur_sec: float,
    work_dir: Path = TEMP_DIR,
) -> Tuple[float, float]:
    """
    Mide rápidamente (en ~40ms) el movimiento medio entre dos fotogramas del tramo
    y la proporción de píxeles planos/muy claros típicos de tablas o menús estáticos 16:9.
    Devuelve (motion_score 0..255, flat_ui_ratio 0..1).
    """
    from PIL import Image, ImageChops, ImageStat

    t1 = max(0.0, start_sec + min(0.5, dur_sec * 0.2))
    t2 = max(t1 + 0.4, start_sec + min(2.2, dur_sec * 0.65))
    f1 = work_dir / f"_ui_chk_{os.getpid()}_1.jpg"
    f2 = work_dir / f"_ui_chk_{os.getpid()}_2.jpg"
    try:
        for ts, out_p in ((t1, f1), (t2, f2)):
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", f"{ts:.2f}", "-i", str(source_video),
                    "-frames:v", "1", "-vf", "scale=160:90", str(out_p),
                ],
                capture_output=True,
                timeout=8,
            )
        if not (f1.exists() and f2.exists()):
            return 20.0, 0.0
        im1 = Image.open(f1).convert("L")
        im2 = Image.open(f2).convert("L")
        diff = ImageChops.difference(im1, im2)
        motion = float(ImageStat.Stat(diff).mean[0])

        # Detectar menús/tablas con barras horizontales muy claras o fondos planos uniformes
        hist = im1.histogram()
        total_px = max(1, sum(hist))
        bright_flat = sum(hist[210:]) / total_px
        return round(motion, 2), round(bright_flat, 3)
    except Exception:
        return 20.0, 0.0
    finally:
        f1.unlink(missing_ok=True)
        f2.unlink(missing_ok=True)


def sanitize_gameplay_beats_against_menus(
    source_video: Path,
    beats: List[Dict[str, Any]],
    source_duration: float,
    work_dir: Path = TEMP_DIR,
    min_motion: float = 6.5,
    max_bright_ui_ratio: float = 0.42,
) -> List[Dict[str, Any]]:
    """
    Verifica visualmente cada acto de gameplay (no 'map_location') para evitar que
    entren menús de pausa o tablas de estadísticas recortadas lateralmente.
    Si detecta un tramo estático/tabla, desplaza el inicio al offset cercano con gameplay en movimiento.
    """
    if not beats or not source_video or not Path(source_video).exists():
        return beats

    cleaned: List[Dict[str, Any]] = []
    max_dur = float(source_duration or 0.0)

    for b in beats:
        act = str(b.get("act") or "").lower()
        s = float(b.get("start_sec", 0.0))
        e = float(b.get("end_sec", s + 4.0))
        beat_dur = max(3.5, e - s)

        if "map" in act:
            cleaned.append(b)
            continue

        motion, bright_ui = _measure_segment_motion_and_ui(source_video, s, beat_dur, work_dir)
        is_menu_or_table = (motion < min_motion) or (bright_ui >= max_bright_ui_ratio and motion < 14.0)
        if not is_menu_or_table:
            cleaned.append(b)
            continue

        best_s = s
        best_motion = motion
        for delta in (5.0, 10.0, -5.0, 16.0, -10.0, 24.0):
            cand_s = s + delta
            if cand_s < 0.0 or (max_dur > 0 and cand_s + beat_dur > max_dur - 0.5):
                continue
            c_mot, c_ui = _measure_segment_motion_and_ui(source_video, cand_s, beat_dur, work_dir)
            if c_mot >= min_motion and not (c_ui >= max_bright_ui_ratio and c_mot < 14.0):
                best_s = cand_s
                best_motion = c_mot
                break
            if c_mot > best_motion:
                best_s = cand_s
                best_motion = c_mot

        if abs(best_s - s) >= 0.5:
            print(
                f"[✓ GuideCompiler] Acto '{act or 'gameplay'}' desplazado {s:.1f}s -> {best_s:.1f}s "
                f"(menú/tabla estática evitada: motion {motion:.1f} -> {best_motion:.1f})"
            )
            cleaned.append({**b, "start_sec": round(best_s, 2), "end_sec": round(best_s + beat_dur, 2)})
        else:
            cleaned.append(b)

    return cleaned


def build_multi_beat_guide_package(
    url: str,
    video_id: str,
    source_video: Path,
    work_dir: Path = TEMP_DIR,
) -> Optional[Tuple[Path, Path, Path, Dict[str, Any]]]:
    """
    Pipeline completo de compilación Multi-Beat 16:9 -> 9:16:
    1. Lee transcripción + capítulos del vídeo largo.
    2. Planifica 4 actos con Gemini (Recompensa -> Mapa -> Pasos -> Cobro).
    3. Sintetiza voz por acto y ajusta cada corte a la duración exacta de su voz (0 huecos mudos).
    4. Filtra visualmente menús/tablas estáticas en los actos de gameplay.
    5. Compila el vídeo maestro y devuelve (comp_mp4, srt_path, dub_mp3, plan).
    """
    try:
        ctx = fetch_long_guide_context(url, video_id, work_dir)
        dur = float(ctx.get("duration") or 0)
        if dur < 45.0:
            return None
        plan = plan_multi_beat_guide(
            ctx.get("title", ""),
            dur,
            ctx.get("chapters") or [],
            ctx.get("segments") or [],
            source_video=source_video,
            work_dir=work_dir,
        )
        if not plan or not plan.get("beats"):
            return None

        dub_mp3 = work_dir / f"{video_id}_mb_dub.mp3"
        synced_beats, ok_tts = sync_beats_with_voiceover(plan["beats"], dur, dub_mp3, work_dir)
        if not ok_tts or not synced_beats:
            return None

        synced_beats = sanitize_gameplay_beats_against_menus(source_video, synced_beats, dur, work_dir)

        comp_mp4 = work_dir / f"{video_id}_mb_compiled.mp4"
        srt_path = work_dir / f"{video_id}_mb_es.srt"
        ok_vid, _ = compile_multi_beat_video(source_video, synced_beats, comp_mp4, srt_path)
        if not ok_vid or not comp_mp4.exists():
            return None

        return comp_mp4, srt_path, dub_mp3, plan
    except Exception as e:
        print(f"[GuideCompiler] Aviso fallback a flujo estándar: {e}")
        return None


def build_multi_beat_guide_package_from_url(
    url: str,
    video_id: str,
    work_dir: Path = TEMP_DIR,
) -> Optional[Tuple[Path, Path, Path, Dict[str, Any]]]:
    """
    Descarga y compila un Short Multi-Beat directamente desde una URL de guía (>= 45s,
    ideal para guías enfocadas de 1-3 min en YouTube o X/Twitter).
    Descarga primero el vídeo para que Gemini Vision VEA fotogramas reales antes de planificar.
    """
    if "/shorts/" in (url or "").lower():
        return None
    src_mp4 = work_dir / f"{video_id}_mb_src.mp4"
    try:
        ctx = fetch_long_guide_context(url, video_id, work_dir)
        dur = float(ctx.get("duration") or 0)
        if dur < 45.0:
            return None

        dl_res = subprocess.run([
            sys.executable, "-m", "yt_dlp", "--impersonate", "chrome", "--no-check-certificates",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
            "--merge-output-format", "mp4", "-o", str(src_mp4), url
        ], capture_output=True, text=True, timeout=180)
        if dl_res.returncode != 0 or not src_mp4.exists():
            return None

        plan = plan_multi_beat_guide(
            ctx.get("title", ""),
            dur,
            ctx.get("chapters") or [],
            ctx.get("segments") or [],
            source_video=src_mp4,
            work_dir=work_dir,
        )
        if not plan or not plan.get("beats"):
            return None

        dub_mp3 = work_dir / f"{video_id}_mb_dub.mp3"
        synced_beats, ok_tts = sync_beats_with_voiceover(plan["beats"], dur, dub_mp3, work_dir)
        if not ok_tts or not synced_beats:
            return None

        synced_beats = sanitize_gameplay_beats_against_menus(src_mp4, synced_beats, dur, work_dir)

        comp_mp4 = work_dir / f"{video_id}_mb_compiled.mp4"
        srt_path = work_dir / f"{video_id}_mb_es.srt"
        ok_vid, _ = compile_multi_beat_video(src_mp4, synced_beats, comp_mp4, srt_path)
        if not ok_vid or not comp_mp4.exists():
            return None

        return comp_mp4, srt_path, dub_mp3, plan
    except Exception as e:
        print(f"[GuideCompiler] Aviso fallback desde URL: {e}")
        return None
    finally:
        src_mp4.unlink(missing_ok=True)

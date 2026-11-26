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
    profile: str = "short",
) -> Optional[Dict[str, Any]]:
    """
    Usa Gemini Vision (cuando `source_video` está disponible) para diseñar un storyboard
    100% alineado visualmente:
    - `profile="short"` (YouTube Shorts / TikTok): 4 actos, 17-23s totales, mapa máx 2.0-3.0s.
    - `profile="x_long"` (X / Twitter): 5-6 actos completos, 45-70s totales en 16:9 nativo.
    """
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return None

    is_x_long = (profile or "short").lower() == "x_long"
    # Compactar transcripción para el prompt (máx ~140 líneas)
    max_lines = 140 if is_x_long else 120
    step = max(1, len(segments) // max_lines) if segments else 1
    sampled = segments[::step][:max_lines]
    transcript_txt = "\n".join(f"[{s['start']:.1f}s-{s['end']:.1f}s] {s['text']}" for s in sampled)
    chapters_txt = "\n".join(
        f"[{c.get('start_time', 0):.1f}s-{c.get('end_time', 0):.1f}s] {c.get('title', '')}"
        for c in (chapters or [])[:20]
    )

    storyboard_frames: List[Tuple[float, Path]] = []
    if source_video and Path(source_video).exists():
        n_frames = 18 if is_x_long else 14
        storyboard_frames = extract_visual_storyboard_frames(source_video, duration, num_frames=n_frames, work_dir=work_dir)

    if is_x_long:
        prompt = f"""Eres editor jefe de mini-guías virales para X (Twitter) de GTA 6.
Tienes un vídeo de guía titulado: "{title}" (duración total: {duration:.0f}s).

CAPÍTULOS:
{chapters_txt or "(Sin capítulos)"}

TRANSCRIPCIÓN CON TIMESTAMPS:
{transcript_txt or "(Sin transcripción; guíate directamente por los fotogramas reales adjuntos)"}

TAREA (FORMATO X LONG GUIDE — 45 a 68 segundos totales):
Construye una GUÍA COMPLETA Y DETALLADA de 6 actos (6 cortes reales del vídeo) que sumen entre 48 y 66 segundos totales (NUNCA menos de 45s ni más de 70s).
CADA ACTO DEBE COINCIDIR 100% VISUALMENTE CON LOS FOTOGRAMAS REALES ADJUNTOS:

1. Acto 1 "reward_hook" (5.0-7.0s): Muestra la recompensa principal en acción (coche/arma/dinero) en gameplay 3D. Anuncia directamente qué consigues y por qué merece la pena (14-20 palabras, sin preguntas).
2. Acto 2 "map_location" (3.5-5.0s): Muestra el MAPA con la ubicación exacta y una referencia de la zona (10-14 palabras).
3. Acto 3 "approach_route" (8.0-12.0s): Llegada exacta a la calle, edificio o entrada de la zona (22-30 palabras).
4. Acto 4 "action_steps" (11.0-15.0s): Ejecución paso a paso de lo que ocurre en pantalla (guardias, acceso, truco, interacción) (28-38 palabras).
5. Acto 5 "claim_payoff" (10.0-14.0s): Recogida o conducción de la recompensa + cómo guardarla, registrarla o sacarle el máximo provecho (25-35 palabras).
6. Acto 6 "bonus_cta" (6.0-9.0s): Consejo práctico extra o aviso importante + CTA natural para guardar el post en marcadores ("Guarda este post en marcadores para cuando juegues.").

REGLAS ESTRICTAS:
- Cada beat debe tener 0 <= start_sec < end_sec <= {max(10.0, duration - 0.5):.1f}.
- Prioriza siempre tramos con acción dinámica (disparos, persecuciones, conducción rápida o interacción directa) siempre que coincidan con la guía real y lo que se narra.
- PROHIBIDO elegir menús de pausa o tablas de estadísticas en los actos de gameplay (actos 1, 3, 4, 5, 6).
- Español natural de España, directo, fiel a lo que sale en pantalla, sin palabras prohibidas (usa "recompensa" o "mercancía" en vez de drogas/cocaína).

Responde SOLO JSON válido:
{{
  "has_facecam": false,
  "has_burned_english_subs": false,
  "short_title_es": "TÍTULO DIRECTO PARA X SIN HASHTAGS",
  "cover_line1": "1 PALABRA BLANCA",
  "cover_line2": "1-2 PALABRAS ACENTO",
  "beats": [
    {{"act": "reward_hook", "start_sec": 0.0, "end_sec": 6.0, "narration_es": "..."}},
    {{"act": "map_location", "start_sec": 0.0, "end_sec": 4.2, "narration_es": "..."}},
    {{"act": "approach_route", "start_sec": 0.0, "end_sec": 10.0, "narration_es": "..."}},
    {{"act": "action_steps", "start_sec": 0.0, "end_sec": 13.0, "narration_es": "..."}},
    {{"act": "claim_payoff", "start_sec": 0.0, "end_sec": 12.0, "narration_es": "..."}},
    {{"act": "bonus_cta", "start_sec": 0.0, "end_sec": 7.5, "narration_es": "..."}}
  ]
}}"""
    else:
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
- Prioriza siempre tramos con acción dinámica (disparos, persecuciones, conducción rápida o interacción directa) siempre que coincidan con la guía real y lo que se narra.
- PROHIBIDO elegir tramos con menús de pausa, pantallas de estadísticas/tablas de vehículos, sliders horizontales o pantallas de carga en los actos 1, 3 y 4; esos 3 actos deben ser SIEMPRE gameplay 3D en movimiento.
- El texto `narration_es` debe ser español natural de España, fiel a lo que sale en pantalla, y sin palabras prohibidas (usa "recompensa" o "mercancía" en vez de drogas/cocaína).

- AUDITORÍA VISUAL OBLIGATORIA (sé estricto): marca `"has_facecam": true` si aparece CUALQUIER cámara/cara de un streamer o persona real superpuesta al gameplay (NO personajes 3D de GTA 6). Marca `"has_burned_english_subs": true` si el vídeo original ya trae textos/subtítulos grandes en inglés quemados encima del gameplay (NO el HUD normal del juego).

Responde SOLO JSON válido:
{{
  "has_facecam": false,
  "has_burned_english_subs": false,
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
    if data.get("has_facecam") is True or data.get("has_burned_english_subs") is True:
        print(
            f"[✗ Visual Compliance Shield] Vídeo rechazado en origen: "
            f"has_facecam={data.get('has_facecam')} | has_burned_english_subs={data.get('has_burned_english_subs')}"
        )
        return None
    beats = data.get("beats") or []
    valid_beats: List[Dict[str, Any]] = []
    for b in beats:
        act_name = str(b.get("act", "step")).lower()
        is_map = "map" in act_name
        s = max(0.0, float(b.get("start_sec", 0)))
        if is_x_long:
            default_len = 4.2 if is_map else 10.0
            e = min(max(duration - 0.3, s + default_len), float(b.get("end_sec", s + default_len)))
            if is_map:
                if e - s < 3.0:
                    e = min(duration, s + 3.8)
                if e - s > 5.5:
                    e = s + 5.0
            else:
                if e - s < 4.5:
                    e = min(duration, s + 6.0)
                if e - s > 18.0:
                    e = s + 16.0
        else:
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

    # Detectar dimensiones exactas y si tiene audio
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(source_video)],
        capture_output=True, text=True, timeout=8,
    )
    has_audio = bool(probe.stdout.strip())
    v_probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(source_video)],
        capture_output=True, text=True, timeout=8,
    )
    src_w, src_h = 0, 0
    if "x" in (v_probe.stdout or ""):
        try:
            src_w, src_h = [int(x) for x in v_probe.stdout.strip().splitlines()[0].split("x")[:2]]
        except Exception:
            src_w, src_h = 0, 0

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
        if "map" in act_name and src_w > 0 and src_h > 0:
            zw = int(round(src_w * 1.08))
            zh = int(round(src_h * 1.08))
            zw += zw % 2
            zh += zh % 2
            # Paneo/zoom suave con dimensiones finales EXACTAS (src_w x src_h) para concat sin error
            v_filters.append(
                f"[{idx}:v]setpts=PTS-STARTPTS,"
                f"scale={zw}:{zh},"
                f"crop={src_w}:{src_h}:({zw}-{src_w})/2*(1-min(1\\,t/{max(dur, 1.0):.2f})):({zh}-{src_h})/2,"
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
        maps = ["-map", "[vout]", "-map", "[aout]", "-c:v", vcodec, "-b:v", "22M", "-c:a", "aac", "-b:a", "192k"]
    else:
        fc = ";".join(v_filters) + f";{''.join(concat_inputs)}concat=n={n}:v=1:a=0[vout]"
        maps = ["-map", "[vout]", "-c:v", vcodec, "-b:v", "22M"]

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
    profile: str = "short",
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

            is_x_long = (profile or "short").lower() == "x_long"
            act_name = str(b.get("act") or "").lower()
            is_map_act = "map" in act_name
            if idx == len(beats) - 1:
                pad_tail = 0.25 if is_x_long else 0.08
            elif is_map_act:
                pad_tail = 0.22 if is_x_long else 0.14
            else:
                pad_tail = 0.28 if is_x_long else (0.20 if idx == 0 else 0.24)

            # Tope para mapa: 2.0-3.2s en Short, 3.0-5.2s en X Long Guide
            atempo_prefix = ""
            if is_map_act:
                map_cap = 5.2 if is_x_long else 3.2
                map_min = 3.0 if is_x_long else 2.0
                if tts_dur > (map_cap - 0.15):
                    spd = min(1.35, round((tts_dur + 0.12) / (map_cap - 0.10), 2))
                    atempo_prefix = f"atempo={spd},"
                    tts_dur = tts_dur / spd
                target_dur = max(map_min, min(map_cap, tts_dur + pad_tail))
            else:
                min_act = 4.5 if is_x_long else 3.2
                target_dur = max(min_act, tts_dur + pad_tail)
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


def narrate_compiled_beats_from_video(
    source_video: Path,
    beats: List[Dict[str, Any]],
    title: str,
    profile: str = "short",
    work_dir: Path = TEMP_DIR,
) -> List[Dict[str, Any]]:
    """
    Fase 2 (Alineación Visual 100%):
    1. Compila un proxy ligero (480p, 8fps, sin audio, ~1-2 MB) con los cortes YA definitivos
       (después del filtro anti-menús).
    2. Envía ese vídeo real a Gemini Vision (inline video/mp4) con los rangos exactos de cada acto.
    3. Reescribe `narration_es` de cada acto describiendo EXCLUSIVAMENTE lo que se ve en pantalla
       en esos segundos exactos (cero desincronización guion <-> imagen).
    """
    if not beats or not source_video or not Path(source_video).exists() or not os.getenv("GEMINI_API_KEY", "").strip():
        return beats

    proxy_mp4 = work_dir / f"_vision_proxy_{os.getpid()}.mp4"
    try:
        inputs: List[str] = []
        v_filters: List[str] = []
        concat_v: List[str] = []
        act_ranges: List[str] = []
        cur_t = 0.0
        for idx, b in enumerate(beats):
            s = float(b["start_sec"])
            e = float(b["end_sec"])
            d = max(1.8, e - s)
            inputs.extend(["-ss", f"{s:.2f}", "-t", f"{d:.2f}", "-i", str(source_video)])
            v_filters.append(
                f"[{idx}:v]fps=8,scale=480:270:force_original_aspect_ratio=decrease,"
                f"pad=480:270:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS,setsar=1[v{idx}]"
            )
            concat_v.append(f"[v{idx}]")
            act_ranges.append(
                f"- Acto {idx + 1} (`{b.get('act', 'step')}`): {cur_t:.1f}s a {cur_t + d:.1f}s "
                f"(duración {d:.1f}s, ~{max(6, int(d * 2.4))} palabras máx)"
            )
            cur_t += d

        fc = ";".join(v_filters) + f";{''.join(concat_v)}concat=n={len(beats)}:v=1:a=0[vout]"
        vcodec = "h264_videotoolbox" if os.uname().sysname == "Darwin" else "libx264"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-threads", "2",
            *inputs, "-filter_complex", fc,
            "-map", "[vout]", "-c:v", vcodec, "-b:v", "450k", "-an",
            "-movflags", "+faststart", str(proxy_mp4),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0 or not proxy_mp4.exists() or proxy_mp4.stat().st_size > 18 * 1024 * 1024:
            return beats

        from google.genai import types
        is_x_long = (profile or "short").lower() == "x_long"
        cta_rule = (
            'El último acto debe cerrar con "Guarda este post en marcadores para cuando juegues."'
            if is_x_long
            else 'El último acto debe cerrar con "Guárdalo para cuando juegues."'
        )
        prompt = (
            f'Eres el narrador oficial de GTA 6 para una guía titulada "{title}".\n'
            "Te adjunto el VÍDEO YA MONTADO Y RECORTADO. Estos son los cortes exactos que vas a ver:\n"
            + "\n".join(act_ranges) + "\n\n"
            "REGLA DE ORO (OBLIGATORIA):\n"
            "- Mira cada segundo del vídeo adjunto y escribe `narration_es` para cada acto describiendo "
            "ÚNICA Y EXCLUSIVAMENTE lo que REALMENTE aparece en pantalla en ese rango de segundos.\n"
            "- Si en un acto el personaje conduce un coche, di qué hace con ese coche; si sale el mapa, señala la ubicación en el mapa; "
            "si entra a pie a una casa/zona o recoge algo, describe EXACTAMENTE esa acción visible.\n"
            "- PROHIBIDO mencionar objetos, vehículos, lugares o pasos que NO aparezcan en el vídeo de ese acto.\n"
            "- Español natural de España, tono directo sin preguntas retóricas y sin palabras prohibidas (usa 'recompensa' o 'mercancía').\n"
            f"- Respeta estrictamente el límite aproximado de palabras de cada acto para que la voz encaje al segundo. {cta_rule}\n\n"
            f'Responde SOLO JSON válido con exactamente {len(beats)} elementos en orden:\n'
            '{"narrations": ["texto acto 1", "texto acto 2", ...]}'
        )
        client = get_gemini_client()
        resp = generate_content_with_retry(
            client=client,
            contents=[
                types.Part.from_bytes(data=proxy_mp4.read_bytes(), mime_type="video/mp4"),
                prompt,
            ],
            config={"response_mime_type": "application/json"},
        )
        data = json.loads(clean_srt_response(resp.text or "{}"))
        narrs = data.get("narrations") or []
        if len(narrs) == len(beats):
            updated = []
            for b, new_n in zip(beats, narrs):
                clean_n = sanitize_banned_words(str(new_n or "").strip())
                updated.append({**b, "narration_es": clean_n or b.get("narration_es", "")})
            print(f"[✓ GuideCompiler] Guion re-narrado viendo el vídeo montado ({len(updated)} actos 100% alineados).")
            return updated
    except Exception as exc:
        print(f"[GuideCompiler] Aviso en re-narración sobre vídeo montado: {exc}")
    finally:
        proxy_mp4.unlink(missing_ok=True)
    return beats


def build_multi_beat_guide_package(
    url: str,
    video_id: str,
    source_video: Path,
    work_dir: Path = TEMP_DIR,
    profile: str = "short",
) -> Optional[Tuple[Path, Path, Path, Dict[str, Any]]]:
    """
    Pipeline completo de compilación Multi-Beat (2 fases visualmente alineadas):
    - profile="short": 17-23s para YouTube Shorts y TikTok (9:16).
    - profile="x_long": 45-70s para X (Twitter) en 16:9 nativo.
    """
    try:
        ctx = fetch_long_guide_context(url, video_id, work_dir)
        dur = float(ctx.get("duration") or 0)
        min_src = 65.0 if profile == "x_long" else 45.0
        if dur < min_src:
            return None
        plan = plan_multi_beat_guide(
            ctx.get("title", ""),
            dur,
            ctx.get("chapters") or [],
            ctx.get("segments") or [],
            source_video=source_video,
            work_dir=work_dir,
            profile=profile,
        )
        if not plan or not plan.get("beats"):
            return None

        # Fase 1b: filtrar menús/tablas ANTES de narrar
        clean_beats = sanitize_gameplay_beats_against_menus(source_video, plan["beats"], dur, work_dir)
        # Fase 2: Gemini VE el vídeo ya cortado y redacta el guion exacto de lo que sale en pantalla
        grounded_beats = narrate_compiled_beats_from_video(
            source_video, clean_beats, ctx.get("title", ""), profile=profile, work_dir=work_dir
        )

        tag = "xlong" if profile == "x_long" else "mb"
        dub_mp3 = work_dir / f"{video_id}_{tag}_dub.mp3"
        synced_beats, ok_tts = sync_beats_with_voiceover(grounded_beats, dur, dub_mp3, work_dir, profile=profile)
        if not ok_tts or not synced_beats:
            return None

        comp_mp4 = work_dir / f"{video_id}_{tag}_compiled.mp4"
        srt_path = work_dir / f"{video_id}_{tag}_es.srt"
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
    profile: str = "short",
) -> Optional[Tuple[Path, Path, Path, Dict[str, Any]]]:
    """
    Descarga y compila una guía Multi-Beat directamente desde URL (YouTube o X).
    Descarga primero el vídeo en 4K UHD, filtra menús y hace que Gemini VEA el vídeo
    ya montado antes de escribir la narración definitiva.
    """
    if "/shorts/" in (url or "").lower():
        return None
    tag = "xlong" if profile == "x_long" else "mb"
    src_mp4 = work_dir / f"{video_id}_{tag}_src.mp4"
    try:
        ctx = fetch_long_guide_context(url, video_id, work_dir)
        dur = float(ctx.get("duration") or 0)
        min_src = 65.0 if profile == "x_long" else 45.0
        if dur < min_src:
            return None

        dl_res = subprocess.run([
            sys.executable, "-m", "yt_dlp", "--impersonate", "chrome", "--no-check-certificates",
            "-f", "bestvideo[height<=3840][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=3840]+bestaudio/best[height<=3840][ext=mp4]/best",
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
            profile=profile,
        )
        if not plan or not plan.get("beats"):
            return None

        # Fase 1b: filtrar menús/tablas ANTES de narrar
        clean_beats = sanitize_gameplay_beats_against_menus(src_mp4, plan["beats"], dur, work_dir)
        # Fase 2: Gemini VE el vídeo ya cortado y redacta el guion exacto de lo que sale en pantalla
        grounded_beats = narrate_compiled_beats_from_video(
            src_mp4, clean_beats, ctx.get("title", ""), profile=profile, work_dir=work_dir
        )

        dub_mp3 = work_dir / f"{video_id}_{tag}_dub.mp3"
        synced_beats, ok_tts = sync_beats_with_voiceover(grounded_beats, dur, dub_mp3, work_dir, profile=profile)
        if not ok_tts or not synced_beats:
            return None

        comp_mp4 = work_dir / f"{video_id}_{tag}_compiled.mp4"
        srt_path = work_dir / f"{video_id}_{tag}_es.srt"
        ok_vid, _ = compile_multi_beat_video(src_mp4, synced_beats, comp_mp4, srt_path)
        if not ok_vid or not comp_mp4.exists():
            return None

        return comp_mp4, srt_path, dub_mp3, plan
    except Exception as e:
        print(f"[GuideCompiler] Aviso fallback desde URL: {e}")
        return None
    finally:
        src_mp4.unlink(missing_ok=True)

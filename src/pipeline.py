import gc
import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from .config import OUTPUT_DIR, TEMP_DIR, AUTO_DUB_ENGLISH, ENABLE_4K_SHORTS
from .downloader import download_video_and_subtitles
from .translator import translate_srt, generate_video_metadata
from .dubber import generate_voiceover
from .video_editor import render_final_video, get_video_dimensions, detect_horizontal_split_screen
from .channels import mark_video_processed, get_processed_ids
from .uploader import upload_to_youtube
from .social_publisher import SocialPublisher
from .thumbnail_generator import create_video_thumbnail
from .monitor import notify_macos
from .cleaner import clean_temp_directory, clean_uploaded_video_file, enforce_storage_limits
from .copilot import is_copilot_enabled, stage_pending_video, evaluate_autopilot_eligibility, schedule_auto_approve_if_pending

def _count_spoken_words_in_srt(srt_path: Optional[Path]) -> int:
    """Cuenta palabras habladas reales en un SRT ignorando numeración, marcas de tiempo y etiquetas tipo [Music]."""
    if not srt_path or not srt_path.exists():
        return 0
    try:
        words = 0
        for raw_line in srt_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.isdigit() or "-->" in line:
                continue
            cleaned = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", line).strip()
            if cleaned:
                words += len(cleaned.split())
        return words
    except Exception:
        return 0


def _is_pure_visual_title(title: str) -> bool:
    """Detecta comparativas visuales puras o gameplay explícito sin narración."""
    tl = f" {(title or '').lower()} "
    return any(
        kw in tl
        for kw in (
            " vs ", "fps", "comparison", "comparativa",
            "no commentary", "sin comentarios", "pure gameplay", "gameplay only",
            "free roam", "open world", "mundo abierto", "police chase", "walkthrough"
        )
    )


def _is_pure_gameplay_action(title: str) -> bool:
    """Detecta gameplay real in-game (misiones, free roam, persecuciones) frente a reviews o breakdowns hablados."""
    tl = f" {(title or '').lower()} "
    has_gp = any(
        kw in tl
        for kw in (
            "gameplay", "free roam", "first mission", "primera mision", "primera misión",
            "police chase", "open world", "mundo abierto", "walkthrough", "no commentary"
        )
    )
    has_analysis = any(
        kw in tl
        for kw in (
            "breakdown", "review", "tech review", "analysis", "análisis",
            "analisis", "differences", "diferencias", "how long", " vs ", "comparison",
            "discussion", "podcast", "talk", "technology", "digital foundry", "direct special"
        )
    )
    return has_gp and not has_analysis


def _evaluate_gray_frames_retention(frames: list, width: int = 160) -> tuple:
    """
    Evalúa fotogramas en escala de grises (bytes) para detectar planos fijos (talking-head)
    o diapositivas/tarjetas de texto estáticas de fondo claro sin retención visual.
    """
    if len(frames) < 3:
        return True, "OK"

    slide_frames = 0
    for fr in frames:
        n = len(fr)
        if n <= width:
            continue
        bright_flat = 0
        for idx in range(1, n):
            px = fr[idx]
            if px >= 220 and abs(px - fr[idx - 1]) <= 2:
                bright_flat += 1
        if (bright_flat / n) >= 0.48:
            slide_frames += 1

    slide_ratio = slide_frames / len(frames)
    if slide_ratio >= 0.45:
        return False, f"diapositivas/tarjetas estáticas ({slide_frames}/{len(frames)} frames)"

    static_pairs = 0
    for i in range(len(frames) - 1):
        f1, f2 = frames[i], frames[i + 1]
        if len(f1) != len(f2) or not f1:
            continue
        mad = sum(abs(a - b) for a, b in zip(f1, f2)) / len(f1)
        if mad < 7.5:
            static_pairs += 1

    static_ratio = static_pairs / max(len(frames) - 1, 1)
    if static_ratio >= 0.75:
        return False, f"plano fijo sin movimiento ({static_pairs}/{len(frames) - 1} transiciones estáticas)"

    return True, "OK"


def _inspect_clip_motion_and_slides(video_path: Path, clip_dur_sec: float) -> tuple:
    """Extrae hasta 8 mini-fotogramas 160x90 en grises vía ffmpeg y valida dinamismo visual."""
    w, h = 160, 90
    frame_bytes = w * h
    sample_fps = max(0.25, min(0.65, 8.0 / min(max(clip_dur_sec, 12.0), 30.0)))
    try:
        res = subprocess.run(
            [
                "ffmpeg", "-threads", "2", "-t", "30", "-i", str(video_path),
                "-vf", f"fps={sample_fps:.3f},scale={w}:{h},format=gray",
                "-f", "rawvideo", "-pix_fmt", "gray", "-"
            ],
            capture_output=True, timeout=20
        )
        raw = res.stdout
        if not isinstance(raw, (bytes, bytearray)) or len(raw) < frame_bytes * 3:
            return True, "OK"
        count = min(10, len(raw) // frame_bytes)
        frames = [raw[i * frame_bytes:(i + 1) * frame_bytes] for i in range(count)]
        return _evaluate_gray_frames_retention(frames, width=w)
    except Exception:
        return True, "OK"


def _should_reject_static_visuals(
    scene_cuts: int,
    ok_motion: bool,
    motion_reason: str,
    clip_dur_sec: float,
    original_title: str = "",
    mode: str = "",
) -> tuple:
    """Evalúa si un clip carece de dinamismo real sin penalizar gameplay continuo ni comparativas."""
    if not ok_motion:
        return "skipped_static_slides", f"Retención visual insuficiente: {motion_reason}"

    tl = f" {(original_title or '').lower()} "
    is_visual_motion_content = (
        (mode or "").strip().lower() == "gameplay"
        or _is_pure_gameplay_action(original_title)
        or any(
            kw in tl
            for kw in (
                "fps", " vs ", "comparison", "comparativa", "ps5", "xbox",
                "physics", "físicas", "fisicas", "rage 9", "graphics",
                "gráficos", "graficos", "free roam", "police", "chase",
            )
        )
    )
    if scene_cuts < 3:
        if is_visual_motion_content:
            return "", ""
        if scene_cuts == 0:
            return "skipped_static_visuals", f"Vídeo demasiado estático (0 cortes en {clip_dur_sec:.1f}s)"
    return "", ""


def process_single_video(
    url: str,
    video_id: str,
    original_title: str = "",
    creator_name: str = "",
    source_lang: str = "en",
    mode: str = "subs",
    force_short: Optional[bool] = None,
    auto_upload: bool = False,
    privacy_status: Optional[str] = None,
    keep_local_video: bool = False,
    publish_all: bool = False,
    dry_run: bool = False,
    stagger_delay: int = 12,
    copilot_mode: Optional[bool] = None,
    hook_override: Optional[str] = None,
    block_instagram: bool = False,
    allowed_platforms: Optional[list] = None,
    is_manual_ingest: bool = False,
    allow_official_commentary: bool = False,
    candidate_score: int = 0
) -> Optional[Dict[str, Any]]:
    """
    Ejecuta el ciclo de vida completo de un vídeo con transformación editorial real:
    1. Descarga vídeo y subtítulos nativos (yt-dlp).
    2. Procesa / traduce subtítulos al español (Gemini 2.5 Flash).
    3. Genera metadatos virales con tendencias de YouTube, título en MAYÚSCULAS y Fair Use.
    4. Renderiza vídeo transformado con:
       - Intro bumper de 2 segundos (gancho editorial).
       - Marcos de canal y marcas de agua persistentes.
       - Subtítulos dinámicos quemados en imagen (Pillow + VideoToolbox).
    5. Genera miniatura personalizada de alto impacto (1280x720 o 1080x1920).
    6. (Opcional) Sube a YouTube con miniatura y visibilidad indicada.
    7. Limpieza estricta de archivos temporales y vídeo local subido.
    """
    effective_privacy = privacy_status or os.getenv("YOUTUBE_PRIVACY_STATUS", "public")

    print(f"\n=======================================================")
    print(f"[▶] INICIANDO PROCESAMIENTO EDITORIAL: {video_id}")
    print(f"    Título Original: {original_title}")
    print(f"    Creador: {creator_name or 'Rockstar Games'}")
    print(f"    Idioma Origen: {source_lang.upper()}")
    mode_label = (
        "Gameplay / Audio del Juego"
        if mode in ("gameplay", "clean")
        else ("Subtítulos Dinámicos" if mode == "subs" else "Doblaje Neural ES")
    )
    print(f"    Modo: {mode_label}")
    print(f"    Auto-Subida: {'SÍ (' + effective_privacy.upper() + ')' if auto_upload else 'NO'}")
    print(f"=======================================================")

    # 0. PROTOCOLO INNEGOCIABLE DE VALIDACIÓN EXCLUSIVA GTA 6 (Fail-Safe Defense-in-Depth)
    from .channels import is_strictly_gta6, is_official_or_reupload
    from .compliance_auditor import ComplianceAuditor
    if not is_strictly_gta6(original_title):
        if is_manual_ingest:
            if "gta" not in (original_title or "").lower():
                original_title = f"GTA 6: {original_title or 'Gameplay Clip'}"
            print(f"[*] Ingesta manual: Contexto de GTA 6 asegurado para '{original_title}'")
        else:
            err_msg = f"❌ [BLOQUEO DE SEGURIDAD GTA 6] El vídeo '{original_title}' NO trata exclusivamente sobre GTA 6. Abortando inmediatamente."
            print(f"\n{err_msg}")
            try:
                from .telegram_bot import send_telegram_alert
                send_telegram_alert(f"🛡️ *Filtro Exclusivo GTA 6 Activado*\nVídeo descartado (no es GTA 6):\n`{original_title[:60]}`")
            except Exception:
                pass
            return None

    if not is_manual_ingest and not allow_official_commentary and is_official_or_reupload(original_title, creator_name):
        print(f"\n❌ [FILTRO ANTI-OFICIAL] '{original_title}' es contenido oficial de Rockstar o reupload de tráiler. Abortando.")
        try:
            from .telegram_bot import send_telegram_alert
            send_telegram_alert(f"🛡️ *Filtro Anti-Oficial*\nDescartado (tráiler/oficial):\n`{original_title[:60]}`")
        except Exception:
            pass
        return None

    if not block_instagram and ComplianceAuditor.is_streamer(creator_name, original_title):
        block_instagram = True
        print(f"[*] Detectado contenido de streamer ({creator_name}): 'block_instagram: true' activado preventivamente.")

    # Auditoría inicial de almacenamiento
    enforce_storage_limits(max_mb=1000)

    # Pre-check de cuota Anti-Ban antes de descargar o renderizar (evita renders huérfanos en output/)
    if auto_upload:
        from .social_publisher import AntiBanValidator
        from .uploader import _is_youtube_upload_blocked_by_cooldown
        yt_cooldown_blocked, yt_cooldown_reason = _is_youtube_upload_blocked_by_cooldown("", effective_privacy)
        yt_ok = AntiBanValidator.check_daily_limit("youtube") and not yt_cooldown_blocked
        tt_ok = AntiBanValidator.check_daily_limit("tiktok")
        ig_ok = (
            AntiBanValidator.check_daily_limit("instagram")
            and not block_instagram
            and mode not in ("subs", "clean", "gameplay")
        )
        if not (yt_ok or tt_ok or ig_ok):
            reason_extra = f" ({yt_cooldown_reason})" if yt_cooldown_blocked else ""
            print(f"[Anti-Ban Pre-Check] Cuotas diarias o cooldown activos en todas las plataformas elegibles{reason_extra}. Abortando antes de descargar/renderizar.")
            return None

    def report_stage(stage_text: str):
        print(f"\n[*] {stage_text}")
        try:
            from .telegram_bot import send_telegram_alert
            display_title = original_title or video_id
            clean_title = str(display_title).replace("`", "").replace("*", "").replace("_", "")
            send_telegram_alert(f"{stage_text}\n🎬 `{clean_title[:55]}`")
        except Exception as e:
            print(f"[Pipeline] Info Telegram Stage Alert: {e}")

    # 1. Descarga limpia
    res_label = "4K UHD" if ENABLE_4K_SHORTS else "1080p"
    report_stage(f"📥 [1/5] Descargando vídeo y pistas originales ({res_label})...")
    video_path, srt_path, detected_lang = download_video_and_subtitles(
        url, video_id, source_lang=source_lang, trim_official_bumpers=allow_official_commentary
    )
    if not video_path:
        print(f"[!] Falló la descarga del vídeo {video_id}. Abortando.")
        report_stage("⚠️ *Descarga omitida:* El vídeo no está disponible, tiene restricción de edad en YouTube o excedió el tiempo límite.")
        clean_temp_directory(video_id)
        gc.collect()  # Liberar buffers para GaTDSEQ
        return None

    lang_to_use = detected_lang if detected_lang in ["es", "en"] else source_lang

    # Detectar dimensiones, formato y pacing visual real antes de gastar tokens en audio/IA
    width, height = get_video_dimensions(video_path)
    is_vertical = (height > width)
    is_split_comparison = (width > height) and detect_horizontal_split_screen(video_path)

    # Probe de duración y ritmo de cortes (en modo autónomo, rechaza vídeos estáticos con <3 cortes en >=15s salvo split-screen)
    clip_dur_sec = 0.0
    try:
        p_dur = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
        clip_dur_sec = float(p_dur.stdout.strip()) if p_dur.stdout.strip() else 0.0
    except Exception:
        clip_dur_sec = 0.0

    if not is_manual_ingest and not is_split_comparison and not allow_official_commentary and clip_dur_sec >= 15.0:
        try:
            sc_res = subprocess.run(
                [
                    "ffmpeg", "-threads", "2", "-t", "30", "-i", str(video_path),
                    "-vf", "fps=3,scale=320:-1,select='gt(scene,0.22)',showinfo", "-f", "null", "-"
                ],
                capture_output=True, text=True, timeout=25
            )
            scene_cuts = sum(1 for ln in (sc_res.stderr or "").splitlines() if "pts_time:" in ln)
            ok_motion, motion_reason = _inspect_clip_motion_and_slides(video_path, clip_dur_sec)
            reject_status, reject_msg = _should_reject_static_visuals(
                scene_cuts=scene_cuts,
                ok_motion=ok_motion,
                motion_reason=motion_reason,
                clip_dur_sec=clip_dur_sec,
                original_title=original_title,
                mode=mode,
            )
            if not reject_status and scene_cuts < 3:
                print(f"[✓ Quality Visual Shield] Plano continuo con movimiento real ({scene_cuts} cortes, dinamismo OK).")
            if reject_status:
                print(f"[!] [Quality Visual Shield] {reject_msg}. Descartando...")
                mark_video_processed({
                    "id": video_id,
                    "title": original_title,
                    "creator": creator_name,
                    "url": url,
                    "status": reject_status,
                    "date": datetime.now().isoformat()
                })
                clean_temp_directory(video_id)
                gc.collect()
                return None
        except Exception:
            pass

    # En este canal TODO vídeo debe salir obligatoriamente en formato Vertical 9:16 (Shorts/TikTok/Reels),
    # salvo que se indique de forma estricta force_short=False.
    if force_short is False:
        is_short = False
    else:
        is_short = True

    print(f"    Formato Final: {'Vertical 9:16 (Shorts/TikTok/Reels)' if is_short else 'Horizontal 16:9'}")

    # 2. Procesar/Traducir subtítulos si existen (o transcribir audio / comentario editorial con Gemini Flash)
    report_stage("🤖 [2/5] Analizando pistas y generando subtítulos/metadatos...")
    # Usar tanto source_lang como detected_lang e inferencia del título para jamás colar inglés sin doblar
    _en_title_hint = bool(re.search(
        r"\b(the|and|with|from|this|that|just|blew|mind|everyone|everyones|new|gameplay|graphics|comparison|breakdown|missed|things|secrets|details|trailer|now|pre-load|preload|physics|realistic|versus)\b",
        (original_title or "").lower()
    )) and not bool(re.search(
        r"\b(el|la|los|las|del|como|para|por|con|sin|este|esta|estos|nuevo|nueva|nuevos|secretos|detalles|comparativa|graficos|gráficos|fisicas|físicas|lanzamiento|tráiler|filtracion|filtración)\b",
        (original_title or "").lower()
    ))
    if _en_title_hint and lang_to_use == "es":
        lang_to_use = "en"
    audio_needs_dub = (source_lang != "es" or lang_to_use != "es" or _en_title_hint)
    generated_editorial_script = False
    confirmed_no_speech = False
    es_srt_path = None
    if allow_official_commentary and srt_path and srt_path.exists():
        # Conservar pistas de subtítulos reales para traducir y dar contexto exacto a metadatos (sin doblar música de tráilers)
        print("[*] Spot oficial con rótulos/subtítulos detectados: conservando audio original de Rockstar y subtítulos en español...")

    is_pure_gameplay = _is_pure_gameplay_action(original_title)
    skip_tts_for_gameplay = False

    srt_spoken_words = _count_spoken_words_in_srt(srt_path)

    # Streamers y clips en español con voz real: conservar audio original PERO activar subtítulos Karaoke dinámicos
    if (
        mode in ("gameplay", "clean")
        and lang_to_use == "es"
        and not is_split_comparison
        and not allow_official_commentary
        and srt_spoken_words >= 8
    ):
        print(
            f"[*] [Streamer/Voz ES] Detectadas {srt_spoken_words} palabras en español: "
            "activando subtítulos Karaoke dinámicos preservando audio original."
        )
        mode = "subs"
        skip_tts_for_gameplay = True

    # Guardia Anti-Inglés: si IA eligió 'gameplay'/'clean' en autónomo sobre vídeo en inglés con locución real,
    # forzar traducción + autodoblaje — PERO si es gameplay real con diálogos in-game breves (<32 palabras),
    # usar subtítulos en español conservando las voces y el sonido auténtico del juego (sin doblaje TTS encima).
    allow_pure_gameplay = (
        is_manual_ingest
        or is_split_comparison
        or allow_official_commentary
        or lang_to_use == "es"
    )
    if mode in ("gameplay", "clean") and not allow_pure_gameplay:
        if is_pure_gameplay and 8 <= srt_spoken_words < 32:
            print(
                f"[*] [Gameplay Real + Diálogos] Detectadas {srt_spoken_words} palabras in-game: "
                "activando subtítulos dinámicos ES preservando audio auténtico de GTA 6."
            )
            mode = "subs"
            skip_tts_for_gameplay = True
        elif srt_spoken_words >= 12:
            target_mode = "dub" if AUTO_DUB_ENGLISH else "subs"
            print(
                f"[!] [Guardia Anti-Inglés] Detectada locución ({srt_spoken_words} palabras en {lang_to_use.upper()}) "
                f"pese a modo '{mode}'. Activando modo '{target_mode}'."
            )
            mode = target_mode
        elif is_pure_gameplay:
            print("[*] [Gameplay Puro] Conservando audio auténtico del juego sin TTS ni subtítulos inventados.")
        elif not (srt_path and srt_path.exists()) and not _is_pure_visual_title(original_title):
            print(
                f"[*] [Guardia Anti-Inglés] Modo '{mode}' sin subtítulos ni título visual puro: "
                "verificando voz en audio con Gemini antes de conservar audio original..."
            )
            mode = "dub" if AUTO_DUB_ENGLISH else "subs"

    if mode in ("gameplay", "clean"):
        print("[*] Modo Gameplay/Visual limpio: preservando audio del juego sin transcribir diálogos de fondo.")
        es_srt_path = None
    elif srt_path and srt_path.exists():
        es_srt_path = TEMP_DIR / f"{video_id}_es.srt"
        success_trans = translate_srt(
            srt_path,
            es_srt_path,
            source_lang=lang_to_use
        )
        if not success_trans:
            print("[Warning] No se pudieron traducir subtítulos al español.")
            es_srt_path = None
    else:
        # En spots oficiales o gameplay puro NO transcribir letras musicales/diálogos de fondo
        if not allow_official_commentary:
            # Si no hay subtítulos nativos, intentar transcribir directamente el audio del clip con Gemini Flash
            try:
                from .translator import transcribe_and_translate_audio_gemini
                from .dubber import parse_first_cue_start
                temp_audio = TEMP_DIR / f"{video_id}_audio_speech.mp3"
                cmd_extract_audio = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-ar", "16000",
                    "-ac", "1",
                    "-b:a", "64k",
                    str(temp_audio)
                ]
                subprocess.run(cmd_extract_audio, capture_output=True, timeout=25)
                if temp_audio.exists() and temp_audio.stat().st_size > 500:
                    print("[*] Audio extraído. Consultando Gemini Flash para transcripción y traducción al español...")
                    candidate_srt = TEMP_DIR / f"{video_id}_es.srt"
                    success_ai, has_speech = transcribe_and_translate_audio_gemini(temp_audio, candidate_srt, target_lang="es")
                    if success_ai and has_speech and candidate_srt.exists():
                        first_t = parse_first_cue_start(candidate_srt)
                        if first_t <= 12.0:
                            es_srt_path = candidate_srt
                            srt_path = candidate_srt
                            lang_to_use = "es"
                            print(f"[✓] Transcripción y traducción de audio completada con éxito.")
                        else:
                            print(f"[!] Transcripción con timestamp corrupto ({first_t:.1f}s > 12s). Descartando SRT para usar comentario editorial...")
                            candidate_srt.unlink(missing_ok=True)
                    elif success_ai and not has_speech:
                        print("[*] Audio analizado: Clip sin narración (gameplay o efectos de sonido puros).")
                        es_srt_path = None
                        confirmed_no_speech = True
                if temp_audio.exists():
                    temp_audio.unlink(missing_ok=True)
            except Exception as e:
                print(f"[!] Info transcripción multimodal de audio: {e}")

        # Si aún no hay subtítulos y no se detectó voz, intentar OCR como respaldo secundario
        if not es_srt_path:
            try:
                from .ocr_extractor import extract_gameplay_text
                gameplay_text = extract_gameplay_text(video_path, max_chars=120)
                if gameplay_text:
                    print(f"[OCR] Texto de gameplay extraído (<120 car): '{gameplay_text}'")
                    ocr_srt = TEMP_DIR / f"{video_id}_ocr.srt"
                    with open(ocr_srt, "w", encoding="utf-8") as f:
                        f.write(f"1\n00:00:01,000 --> 00:00:06,500\n{gameplay_text}\n\n")
                    if lang_to_use != "es":
                        es_srt_path = TEMP_DIR / f"{video_id}_es.srt"
                        if not translate_srt(ocr_srt, es_srt_path, source_lang=lang_to_use):
                            es_srt_path = ocr_srt
                    else:
                        es_srt_path = ocr_srt
                    srt_path = ocr_srt
            except Exception as e:
                print(f"[OCR] Info extracción de texto en pantalla: {e}")

    # Si el clip no tiene narración hablada o falló la cuota de IA (Gemini 429), generar comentario editorial
    # (multimodal o fallback mecánico 0-API) para aportar narrativa en español, Pop Karaoke y desbloquear IG Reels.
    if (
        (not es_srt_path)
        and (
            mode in ("dub", "subs")
            or (confirmed_no_speech and os.getenv("AUTO_COMMENTARY_ON_SILENT_GAMEPLAY", "true").lower() in ("1", "true", "yes"))
        )
        and not allow_official_commentary
        and not skip_tts_for_gameplay
        and not is_split_comparison
        and mode != "clean"
        and video_path.exists()
        and video_path.stat().st_size > 10000
    ):
        try:
            from .translator import generate_editorial_commentary_srt
            editorial_srt = TEMP_DIR / f"{video_id}_editorial_es.srt"
            if generate_editorial_commentary_srt(
                video_path=video_path,
                original_title=original_title or video_id,
                creator_name=creator_name or "Rockstar Games",
                output_srt=editorial_srt,
                duration_sec=clip_dur_sec or 25.0,
            ) and editorial_srt.exists():
                es_srt_path = editorial_srt
                srt_path = editorial_srt
                lang_to_use = "es"
                audio_needs_dub = True
                mode = "dub"
                confirmed_no_speech = False
                print("[✓] [Alpha Commentary] Guion editorial original en español generado -> activando voz neural y subtítulos.")
        except Exception as e:
            print(f"[!] Info comentario editorial automático: {e}")

    # Si es clip oficial/visual con música/rótulos breves (<12 palabras) o sin locución, usar modo gameplay (conserva audio original sin abortar en Audio Shield)
    _active_caption_words = _count_spoken_words_in_srt(es_srt_path or srt_path)

    if (not es_srt_path and not (srt_path and srt_path.exists())) or (allow_official_commentary and _active_caption_words < 12):
        tl_lower = (original_title or "").lower()
        is_visual_showcase = (
            mode in ("gameplay", "clean")
            or confirmed_no_speech
            or allow_official_commentary
            or any(
                kw in tl_lower
                for kw in (
                    "gameplay", "pre-load", "preload", "trailer", "teaser",
                    "comparison", "comparativa", "physics", "físicas", "fisicas",
                    "graphics", "gráficos", "graficos", "rage 9", "4k", "60fps",
                    "detail", "detalle", "showcase", "captura"
                )
            )
        )
        if is_visual_showcase:
            print("[*] Clip visual/gameplay/oficial sin narración extensa: conservando sonido auténtico en modo gameplay.")
            mode = "gameplay"

    # Blindaje Editorial: Si el contenido tiene voz original en otro idioma y no se pudo traducir, abortar para no publicar sin subtítulos en español.
    # Si es ingesta manual o gameplay/visual sin locución, se permite procesar.
    if lang_to_use != "es" and not es_srt_path and not is_manual_ingest and mode not in ("gameplay", "clean"):
        print(f"[!] [Blindaje Editorial] El vídeo original está en {lang_to_use.upper()} pero no se pudo traducir al español.")
        print("[!] Abortando procesamiento para proteger el canal de vídeos sin traducir.")
        try:
            from .telegram_bot import send_telegram_alert
            send_telegram_alert(
                f"🛡️ *[Blindaje Editorial]* Vídeo '{original_title[:45]}...' omitido:\n"
                f"Está en {lang_to_use.upper()} y la traducción al español no estuvo disponible. Se protege el canal contra contenido en inglés."
            )
        except Exception:
            pass
        clean_temp_directory(video_id)
        return None

    # 4. Doblaje de voz neural en español (obligatorio en autónomo para voz en inglés si AUTO_DUB_ENGLISH=true, o bajo demanda en modo dub)
    # En anuncios oficiales de Rockstar (allow_official_commentary=True), JAMÁS doblar los subtítulos automáticos de música/canciones;
    # preservar el audio original de Rockstar con subtítulos en español.
    dub_audio_path = None
    if allow_official_commentary and not is_manual_ingest:
        print("[*] Anuncio oficial de Rockstar: preservando banda sonora/audio original sin doblar canciones con TTS.")
        should_dub = False
    elif skip_tts_for_gameplay:
        print("[*] Gameplay con audio auténtico preservado: usando subtítulos en español sin doblaje TTS encima.")
        should_dub = False
    else:
        should_dub = (mode in ["dub", "voice"]) or (
            AUTO_DUB_ENGLISH and audio_needs_dub and not is_manual_ingest and mode not in ["gameplay", "clean"]
        )
    if should_dub and es_srt_path and audio_needs_dub:
        dub_audio_path = TEMP_DIR / f"{video_id}_es_voice.mp3"
        print(f"[*] Modo voz activa (ES Neural). Generando locución en español...")
        if generate_voiceover(es_srt_path, dub_audio_path, max_duration=clip_dur_sec or None):
            mode = "dub"
        else:
            dub_audio_path = None

    # 4b. Protocolo Innegociable de Vitalidad Acústica y Narrativa (Anti-Silencio / Anti-Mute)
    from .audio_shield import validate_audio_and_speech_vitality
    has_vo = (dub_audio_path is not None and dub_audio_path.exists())
    is_vital, vital_reason, vital_details = validate_audio_and_speech_vitality(
        video_path=video_path,
        srt_path=es_srt_path or srt_path,
        has_voiceover=has_vo,
        mode=mode,
        is_manual=is_manual_ingest,
        allow_gameplay_sound=(mode in ["gameplay", "clean"] or is_manual_ingest)
    )
    if not is_vital:
        print(f"\n[!] {vital_reason}")
        print("[!] [Anti-Shadowban] Abortando procesamiento para proteger las métricas y la reputación del canal contra clips mudos o B-roll sin voz.")
        try:
            from .telegram_bot import send_telegram_alert
            send_telegram_alert(
                f"🛡️ *[Escudo Anti-Silencio Activado]*\n"
                f"Vídeo descartado para proteger la calidad del canal:\n"
                f"🎬 `{original_title[:45]}...`\n"
                f"⚠️ *Motivo:* {vital_reason}"
            )
        except Exception:
            pass
        clean_temp_directory(video_id)
        gc.collect()
        return None

    # 5. Generación de Metadatos Virales (Título + Gancho + Pregunta Polarizante + Descripción Legal)
    print("[*] Generando metadatos virales con tendencias de YouTube y Fair Use...")
    clip_transcript_text = ""
    active_srt = es_srt_path or srt_path
    if active_srt and active_srt.exists():
        try:
            clip_transcript_text = active_srt.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            clip_transcript_text = ""

    metadata = generate_video_metadata(
        original_title=original_title or video_id,
        original_url=url,
        is_short=is_short,
        creator_name=creator_name,
        source_lang=lang_to_use,
        clip_transcript=clip_transcript_text
    )
    if is_manual_ingest and hook_override:
        hook_text = hook_override
    else:
        hook_text = metadata.get("hook") or hook_override or "¡ANÁLISIS AL DETALLE!"

    # 5a. Filtro adaptativo anti-cliché: solo purga clichés genéricos que no encajan con el arquetipo real
    # Si el contenido genuinamente trata sobre algo "brutal" (gameplay_puro, reaccion_streamer), se respeta.
    # Solo se filtran clichés en arquetipos donde son clickbait vacío (filtracion_misterio, noticia_oficial).
    try:
        from .learning_engine import load_viral_playbook
        _pb = load_viral_playbook()
        _forbidden = [c.lower() for c in _pb.get("active_heuristics", {}).get("forbidden_cliches", [])]
        _archetype = metadata.get("archetype", "")
        _archetypes_strict_filter = {"filtracion_misterio", "noticia_oficial", "analisis_tecnico"}
        if _archetype in _archetypes_strict_filter:
            _gen_title = metadata.get("title", "")
            _changed = False
            for cliche in _forbidden:
                pattern_c = rf"\b{re.escape(cliche)}(?:es|s)?\b"
                if re.search(pattern_c, _gen_title, flags=re.IGNORECASE):
                    _gen_title = re.sub(pattern_c, "", _gen_title, flags=re.IGNORECASE).strip()
                    _gen_title = re.sub(r'\s{2,}', ' ', _gen_title).strip(" !¡")
                    _changed = True
                    print(f"[Playbook] Cliché '{cliche}' eliminado (arquetipo {_archetype} no lo justifica)")
            if _changed and _gen_title:
                metadata["title"] = _gen_title
        elif _forbidden:
            _gen_title = metadata.get("title", "")
            _hits = [c for c in _forbidden if c.lower() in _gen_title.lower()]
            if _hits:
                print(f"[Playbook] Clichés detectados {_hits} pero respetados: el arquetipo '{_archetype}' puede justificarlos.")
    except Exception:
        pass

    # 5b. Inyectar pinned comment con debate_question + enlaces de afiliado
    debate_q = metadata.get("debate_question", "")
    if debate_q and not metadata.get("pinned_comment"):
        try:
            from .affiliates import format_pinned_comment_affiliates, format_pinned_comment_clean, is_affiliates_enabled
            if is_affiliates_enabled():
                metadata["pinned_comment"] = format_pinned_comment_affiliates(debate_q)
            else:
                metadata["pinned_comment"] = format_pinned_comment_clean(debate_q)
        except Exception:
            pass

    # 5. Renderizado final transformado
    stage_msg = "⚙️ [3/5] Renderizando vídeo 9:16 con Doblaje Neural y Subtítulos Dinámicos..." if dub_audio_path else "⚙️ [3/5] Renderizando vídeo 9:16 con VideoToolbox (Subtítulos Hormozi Pop Bounce)..."
    report_stage(stage_msg)
    
    # Comprobar si es contenido oficial de Rockstar o análisis técnico de la industria (para Full Frame Cinema)
    creator_lower = (creator_name or "").lower()
    title_lower = (original_title or "").lower()
    archetype = metadata.get("archetype", "")
    is_official_content = (
        archetype in ["noticia_oficial", "analisis_tecnico"]
        or any(k in creator_lower for k in ["rockstar", "gta series", "take-two", "digital foundry", "york reaction"])
        or any(k in title_lower for k in ["official trailer", "tráiler oficial", "trailer 1", "trailer 2", "rockstar games"])
    )

    # Nombre de archivo viral y legible (evita nombres crudos como SHORT_ID_ES en plataformas como TikTok)
    raw_title = metadata.get("title", original_title or video_id)
    slug = re.sub(r'[^\w\s-]', '', raw_title).strip()
    slug = re.sub(r'[\s_]+', '_', slug)[:55].strip('_')
    if not slug:
        slug = f"GTA_6_{video_id}"
    elif not slug.upper().startswith("GTA"):
        slug = f"GTA_6_{slug}"

    output_filename = f"{slug}_{video_id}.mp4"
    output_path = OUTPUT_DIR / output_filename
    thumb_path = OUTPUT_DIR / f"{slug}_{video_id}_thumb.jpg"
    meta_path = OUTPUT_DIR / f"{slug}_{video_id}_info.json"

    # Selección de encuadre inteligente:
    # - SPLIT: comparativas lado-a-lado 50/50 apiladas verticalmente (93.8% pantalla)
    # - D (83.3%): gameplay puro, físicas, acción, trailers/spots sin textos laterales
    # - C (4:5 / 70.3%): análisis técnicos y comparativas full-frame (2.2x más área visual que FIT)
    is_comparison_or_breakdown = (
        not is_pure_gameplay
        and (
            any(
                kw in title_lower
                for kw in (" vs ", "comparison", "comparativa")
            )
            or any(ch_k in creator_lower for ch_k in ("digital foundry", "elanalistadebits"))
        )
    )

    if is_split_comparison:
        target_preset = "SPLIT"
    elif is_comparison_or_breakdown:
        # Formato C (4:5 / 70.3% de pantalla): mantiene barras comparativas visibles pero con 2.2x más área que FIT
        target_preset = "C"
    else:
        # Formato D (1080x1600 / 83.3% de pantalla): reencuadre vertical inmersivo obligatorio según Regla 5.1 de GEMINI.md
        target_preset = "D"

    render_srt = es_srt_path

    success_render = render_final_video(
        input_video=video_path,
        output_video=output_path,
        srt_subtitles=render_srt,
        dub_audio=dub_audio_path,
        force_short_format=is_short,
        hook_text=hook_text,
        is_official_content=is_official_content,
        archetype=archetype,
        format_preset=target_preset,
        context_badge=metadata.get("context_badge", "")
    )

    if not success_render or not output_path.exists():
        print("[!] Error en el renderizado final del vídeo.")
        clean_temp_directory(video_id)
        gc.collect()  # Liberar buffers para GaTDSEQ
        return None

    # 5b. Validación post-render con ffprobe (detecta archivos corruptos o truncados)
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(output_path)],
            capture_output=True, text=True, timeout=10
        )
        rendered_duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0.0
        if rendered_duration < 5.0:
            print(f"[!] Validación post-render FALLIDA: duración {rendered_duration:.1f}s < 5s. Vídeo descartado.")
            output_path.unlink(missing_ok=True)
            clean_temp_directory(video_id)
            gc.collect()
            return None
        print(f"[✓] Validación post-render OK: {rendered_duration:.1f}s")
        # Warning adaptativo de sweet spot — los umbrales dependen del tipo de contenido
        # Análisis técnicos y noticias oficiales toleran más duración; humor y gameplay deben ser cortos
        if is_short:
            _sweet_max = {"humor_parodia": 28, "gameplay_puro": 32, "reaccion_streamer": 35,
                          "filtracion_misterio": 35, "analisis_tecnico": 50, "noticia_oficial": 55}
            _threshold = _sweet_max.get(archetype, 35)
            if rendered_duration > _threshold:
                print(f"[⚠ Sweet Spot] {rendered_duration:.1f}s > {_threshold}s (umbral para '{archetype or 'genérico'}'). Puede afectar completion rate.")
                try:
                    from .telegram_bot import send_telegram_alert
                    send_telegram_alert(f"⚠️ *Duración {rendered_duration:.0f}s* > umbral {_threshold}s para _{archetype or 'short'}_. Considerar recorte.")
                except Exception:
                    pass
    except Exception as e:
        print(f"[Pipeline] Aviso validación ffprobe: {e}")

    # 6. Generación de Miniatura de alto CTR
    report_stage("📸 [4/5] Generando miniatura personalizada de alto impacto...")
    create_video_thumbnail(
        video_path=output_path,
        output_thumb_path=thumb_path,
        hook_text=hook_text,
        creator_tag=creator_name,
        is_short=is_short
    )

    full_info = {
        "id": video_id,
        "original_url": url,
        "original_title": original_title,
        "creator": creator_name,
        "source_lang": lang_to_use,
        "processed_at": datetime.now().isoformat(),
        "is_short": is_short,
        "mode": mode,
        "output_video": str(output_path),
        "thumbnail": str(thumb_path) if thumb_path.exists() else None,
        "youtube_metadata": metadata
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(full_info, f, indent=2, ensure_ascii=False)

    # 7. Co-Pilot Mode: Aprobación previa humana antes de publicar (o Launch Autopilot opt-in)
    from .config import LAUNCH_AUTOPILOT, LAUNCH_AUTOPILOT_MIN_SCORE, is_gameplay_enabled
    if copilot_mode is None:
        effective_copilot = is_copilot_enabled()
        if not effective_copilot and (auto_upload or publish_all) and not is_manual_ingest:
            try:
                from .performance_tracker import _load_records
                recent_records = [
                    r for r in _load_records()
                    if r.get("views") is not None or r.get("views_24h") is not None
                ]
            except Exception:
                recent_records = []
            gate = evaluate_autopilot_eligibility(
                candidate_score=candidate_score,
                recent_metrics=recent_records,
            )
            if not gate["allow_autopilot"]:
                print(f"[*] [Autopilot Guard] Revertido a Co-Pilot: {gate['reason']}")
                effective_copilot = True
        if (
            effective_copilot
            and LAUNCH_AUTOPILOT
            and is_gameplay_enabled()
            and not is_manual_ingest
            and (auto_upload or publish_all)
            and candidate_score >= LAUNCH_AUTOPILOT_MIN_SCORE
        ):
            print(f"[*] [Launch Autopilot] Score {candidate_score} >= {LAUNCH_AUTOPILOT_MIN_SCORE}: publicando en estreno sin pausa Co-Pilot.")
            effective_copilot = False
    else:
        effective_copilot = copilot_mode
    if effective_copilot:
        print(f"[*] Modo Co-Pilot ACTIVO: Pausando publicación a la espera de aprobación en Telegram...")
        stage_pending_video(
            video_id=video_id,
            original_url=url,
            original_title=original_title,
            creator_name=creator_name,
            output_video_path=output_path,
            thumbnail_path=thumb_path if thumb_path.exists() else None,
            metadata={
                **metadata,
                "block_instagram": block_instagram,
                "allowed_platforms": allowed_platforms,
                "has_voiceover": (dub_audio_path is not None and dub_audio_path.exists()) or (mode in ["dub", "voice"]),
                "is_transformed_visual": is_split_comparison,
                "mode": mode
            },
            is_short=is_short,
            mode=mode,
            publish_all=publish_all,
            privacy_status=privacy_status,
            stagger_delay=stagger_delay,
            keep_local_video=keep_local_video
        )
        # Limpieza estricta de archivos temporales
        clean_temp_directory(video_id)
        gc.collect()  # Liberar buffers para GaTDSEQ
        
        full_info["status"] = "staged_for_copilot"

        # Notificación en Telegram para aprobación (con ventana de veto de 60s)
        try:
            from .telegram_bot import send_copilot_approval_request
            sent_ok = send_copilot_approval_request(
                video_id=video_id,
                title=metadata.get("title", original_title),
                creator=creator_name or "Rockstar Games",
                thumbnail_path=thumb_path if thumb_path.exists() else None,
                is_short=is_short,
                mode=mode,
                hook_text=hook_text,
                original_url=url,
                video_path=output_path if output_path and output_path.exists() else None
            )
            if sent_ok:
                schedule_auto_approve_if_pending(video_id)
        except Exception as e:
            print(f"[Pipeline] Info Co-Pilot Telegram: {e}")

        notify_macos(
            title="Co-Pilot: Vídeo Listo para Aprobación",
            message=f"{metadata.get('title', original_title)[:50]}... Pulsa en Telegram para publicar.",
            subtitle="GTA VI Hub Spain"
        )
        # Registrar en processed.json para evitar que el mismo vídeo sea seleccionado
        # de nuevo mientras espera aprobación (o si es rechazado).
        mark_video_processed({
            "id": video_id,
            "title": original_title,
            "creator": creator_name,
            "url": url,
            "source_lang": lang_to_use,
            "status": "staged_copilot",
            "thumbnail": str(thumb_path) if thumb_path and thumb_path.exists() else None,
            "youtube_title": metadata.get("title", ""),
            "date": datetime.now().isoformat()
        })
        return full_info

    # 8. Publicación Directa (Multiplataforma o YouTube)
    uploaded_yt_id = None
    multiplatform_results = {}

    if publish_all:
        report_stage("🚀 [5/5] Publicando en YouTube Shorts, TikTok e Instagram Reels...")
        publisher = SocialPublisher(dry_run=dry_run)
        multiplatform_results = publisher.publish_all(
            video_path=output_path,
            metadata={
                "title": metadata.get("title", f"GTA 6 - {original_title}").upper(),
                "description": metadata.get("description", ""),
                "thumbnail_path": thumb_path if thumb_path.exists() else None,
                "pinned_comment": metadata.get("pinned_comment"),
                "debate_question": metadata.get("debate_question", ""),
                "hook": hook_text,
                "tags": metadata.get("tags", ["GTA6", "GrandTheftAutoVI", "Gaming", "Shorts"]),
                "original_url": url,
                "privacy": effective_privacy,
                "mode": mode,
                "has_voiceover": (dub_audio_path is not None and dub_audio_path.exists()) or (mode in ["dub", "voice"]),
                "is_transformed_visual": is_split_comparison,
                "block_instagram": block_instagram,
                "allowed_platforms": allowed_platforms
            },
            creator_name=creator_name or "Rockstar Games",
            stagger_delay_minutes=stagger_delay
        )
        full_info["multiplatform_urls"] = multiplatform_results
        if multiplatform_results.get("youtube"):
            yt_val = multiplatform_results["youtube"]
            full_info["uploaded_youtube_url"] = yt_val
            # social_publisher devuelve URL completa; extraer solo el ID para el print
            uploaded_yt_id = yt_val.split("youtu.be/")[-1] if "youtu.be/" in str(yt_val) else yt_val
    elif auto_upload:
        report_stage(f"🚀 [5/5] Subiendo a YouTube Shorts ({effective_privacy.upper()}) vía API v3...")
        uploaded_yt_id = upload_to_youtube(
            video_path=output_path,
            title=metadata.get("title", f"GTA 6 - {original_title}").upper(),
            description=metadata.get("description", ""),
            tags=metadata.get("tags"),
            privacy_status=effective_privacy,
            is_short=is_short,
            thumbnail_path=thumb_path if thumb_path.exists() else None,
            pinned_comment=metadata.get("pinned_comment")
        )
        if uploaded_yt_id:
            full_info["uploaded_youtube_url"] = f"https://youtu.be/{uploaded_yt_id}"

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(full_info, f, indent=2, ensure_ascii=False)

    has_published_any = bool(
        uploaded_yt_id
        or (publish_all and any(v and str(v).startswith("http") for v in multiplatform_results.values()))
    )
    if (auto_upload or publish_all) and not dry_run and not has_published_any and not keep_local_video:
        print("[!] Ninguna plataforma publicó el vídeo (cooldown o cuota). Purgando MP4 huérfano y omitiendo marca 'completed'.")
        clean_temp_directory(video_id)
        clean_uploaded_video_file(output_path)
        gc.collect()
        return None

    # 8. Registro en processed.json
    mark_video_processed({
        "id": video_id,
        "title": original_title,
        "creator": creator_name,
        "url": url,
        "source_lang": lang_to_use,
        "status": "completed",
        "thumbnail": str(thumb_path) if thumb_path.exists() else None,
        "youtube_title": metadata.get("title", ""),
        "youtube_uploaded_url": full_info.get("uploaded_youtube_url"),
        "multiplatform": multiplatform_results if publish_all else None,
        "date": datetime.now().isoformat()
    })

    # 8b. Registro en performance_tracker y ChannelSentinel para monitorización 24/7 (solo en subidas reales)
    if not dry_run and (auto_upload or publish_all or full_info.get("uploaded_youtube_url")):
        try:
            from .performance_tracker import record_published_video
            from .channel_sentinel import record_video_for_sentinel, update_realtime_metrics, get_resilient_publishing_target
            record_published_video(
                video_id=video_id,
                title=original_title,
                youtube_url=full_info.get("uploaded_youtube_url", ""),
                base_score=0,
                velocity_vpd=0.0,
                days_old=0,
                is_short=is_short
            )
            record_video_for_sentinel(
                video_id=video_id,
                title=original_title,
                platform_urls=multiplatform_results if multiplatform_results else {"youtube": full_info.get("uploaded_youtube_url", "")},
                target_channel=get_resilient_publishing_target("youtube"),
                archetype=metadata.get("archetype", "general")
            )
            # Auto-monitorización en segundo plano: rastrear checkpoints de vistas de vídeos previos
            update_realtime_metrics(max_items=2)
        except Exception as e:
            print(f"[Pipeline] Info performance_tracker / ChannelSentinel: {e}")

    # 9. REGLAS ESTRICTAS DE LIMPIEZA
    # Limpiar todos los archivos de trabajo en temp/
    clean_temp_directory(video_id)
    gc.collect()  # Liberar buffers para GaTDSEQ

    # Si se subió con éxito a alguna plataforma (YouTube/TikTok/Instagram) y no se pidió conservar copia pesada, borrar el mp4 local
    if has_published_any and not keep_local_video:
        clean_uploaded_video_file(output_path)

    print(f"\n[✓✓✓] ¡Procesamiento transformacional completado!")
    print(f"  -> Título YouTube: {metadata.get('title')}")
    print(f"  -> Miniatura: {thumb_path}")
    print(f"  -> Metadatos: {meta_path}")
    if uploaded_yt_id:
        print(f"  -> Vídeo Subido: https://youtu.be/{uploaded_yt_id}")
    print("")

    # Notificación nativa en macOS
    notify_macos(
        title="¡Vídeo Procesado con Éxito!",
        message=f"{metadata.get('title', original_title)[:50]}... por {creator_name}",
        subtitle="GTA VI Hub Spain"
    )

    # Notificación remota push en Telegram (si está configurado)
    try:
        from .telegram_bot import send_telegram_notification, send_telegram_alert, send_telegram_photo, send_telegram_video
        has_real_uploads = bool(uploaded_yt_id or (publish_all and any(multiplatform_results.values())))

        if has_real_uploads:
            notif_sent = send_telegram_notification(
                title=metadata.get("title", original_title),
                creator=creator_name or "Rockstar Games",
                multiplatform_urls=multiplatform_results if publish_all else {"youtube": full_info.get("uploaded_youtube_url")},
                thumbnail_path=thumb_path if thumb_path.exists() else None
            )
            if notif_sent:
                print("[Pipeline] [✓] Notificación de resumen multiplataforma entregada a Telegram.")
            else:
                print("[Pipeline] [!] No se pudo entregar la notificación resumen a Telegram.")
        else:
            upload_reason = (
                "⚠️ *Fallo en subida automática:* El token de YouTube expiró o las cookies no están activas."
                if (auto_upload or publish_all)
                else "💡 *Modo Co-Pilot Local:* Vídeo listo para revisión táctil en Telegram."
            )
            local_report = (
                "🎬 *VÍDEO RENDERIZADO (VISTA PREVIA LOCAL)*\n"
                + ("═" * 36) + "\n\n"
                f"• *Título:* `{metadata.get('title', original_title)}`\n"
                f"• *Autor:* `{creator_name or 'Rockstar Games'}`\n"
                f"• *Archivo:* `{Path(output_path).name}`\n\n"
                f"{upload_reason}\n\n"
                "Para publicarlo ejecuta:\n"
                f"`./run.sh --url \"{url}\" --upload`"
            )
            # Prioridad absoluta: enviar el VÍDEO reproducible directamente a Telegram
            if output_path and Path(output_path).exists():
                sent_vid = send_telegram_video(Path(output_path), caption=local_report, thumbnail_path=thumb_path if thumb_path.exists() else None)
                if not sent_vid and thumb_path and thumb_path.exists():
                    send_telegram_photo(thumb_path, local_report)
            elif thumb_path and thumb_path.exists():
                send_telegram_photo(thumb_path, local_report)
            else:
                send_telegram_alert(local_report)
    except Exception as e:
        print(f"[Pipeline] Info Telegram: {e}")

    return full_info

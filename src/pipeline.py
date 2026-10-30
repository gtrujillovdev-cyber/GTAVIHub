import gc
import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from .config import OUTPUT_DIR, TEMP_DIR, AUTO_DUB_ENGLISH
from .downloader import download_video_and_subtitles
from .translator import translate_srt, generate_video_metadata
from .dubber import generate_voiceover
from .video_editor import render_final_video, get_video_dimensions
from .channels import mark_video_processed, get_processed_ids
from .uploader import upload_to_youtube
from .social_publisher import SocialPublisher
from .thumbnail_generator import create_video_thumbnail
from .monitor import notify_macos
from .cleaner import clean_temp_directory, clean_uploaded_video_file, enforce_storage_limits
from .copilot import is_copilot_enabled, stage_pending_video

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
    hook_override: Optional[str] = None
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
    print(f"    Modo: {'Subtítulos Dinámicos' if mode == 'subs' else 'Doblaje de Voz'}")
    print(f"    Auto-Subida: {'SÍ (' + effective_privacy.upper() + ')' if auto_upload else 'NO'}")
    print(f"=======================================================")

    # 0. PROTOCOLO INNEGOCIABLE DE VALIDACIÓN EXCLUSIVA GTA 6 (Fail-Safe Defense-in-Depth)
    from .channels import is_strictly_gta6
    if not is_strictly_gta6(original_title):
        err_msg = f"❌ [BLOQUEO DE SEGURIDAD GTA 6] El vídeo '{original_title}' NO trata exclusivamente sobre GTA 6. Abortando inmediatamente."
        print(f"\n{err_msg}")
        try:
            from .telegram_bot import send_telegram_alert
            send_telegram_alert(f"🛡️ *Filtro Exclusivo GTA 6 Activado*\nVídeo descartado (no es GTA 6):\n`{original_title[:60]}`")
        except Exception:
            pass
        return None

    # Auditoría inicial de almacenamiento
    enforce_storage_limits(max_mb=1000)

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
    report_stage("📥 [1/5] Descargando vídeo y pistas originales (1080p)...")
    video_path, srt_path, detected_lang = download_video_and_subtitles(url, video_id, source_lang=source_lang)
    if not video_path:
        print(f"[!] Falló la descarga del vídeo {video_id}. Abortando.")
        report_stage("⚠️ *Descarga omitida:* El vídeo no está disponible, tiene restricción de edad en YouTube o excedió el tiempo límite.")
        clean_temp_directory(video_id)
        gc.collect()  # Liberar buffers para GaTDSEQ
        return None

    lang_to_use = detected_lang if detected_lang in ["es", "en"] else source_lang

    # Detectar dimensiones y formato
    width, height = get_video_dimensions(video_path)
    is_vertical = (height > width)
    # En este canal TODO vídeo debe salir obligatoriamente en formato Vertical 9:16 (Shorts/TikTok/Reels),
    # salvo que se indique de forma estricta force_short=False.
    if force_short is False:
        is_short = False
    else:
        is_short = True

    print(f"    Formato Final: {'Vertical 9:16 (Shorts/TikTok/Reels)' if is_short else 'Horizontal 16:9'}")

    # 2. Procesar/Traducir subtítulos si existen (sin inventar bucles artificiales)
    report_stage("🤖 [2/5] Analizando con Gemini Flash y generando metadatos virales...")
    es_srt_path = None
    if srt_path and srt_path.exists():
        es_srt_path = TEMP_DIR / f"{video_id}_es.srt"
        success_trans = translate_srt(
            srt_path,
            es_srt_path,
            source_lang=lang_to_use
        )
        if not success_trans:
            print("[Warning] No se pudieron traducir subtítulos, se continuará sin subtítulos quemados.")
            es_srt_path = None

    # 4. Doblaje de voz neural en español (solo si el usuario lo solicita explícitamente con mode='dub'/'voice')
    dub_audio_path = None
    should_dub = (mode in ["dub", "voice"]) or (mode != "short" and AUTO_DUB_ENGLISH and lang_to_use != "es")
    if should_dub and lang_to_use != "es" and es_srt_path:
        dub_audio_path = TEMP_DIR / f"{video_id}_es_voice.mp3"
        print(f"[*] Modo voz activa ({lang_to_use.upper()} -> ES). Generando locución neural en español...")
        if generate_voiceover(es_srt_path, dub_audio_path):
            mode = "dub"
        else:
            dub_audio_path = None

    # 5. Generación de Metadatos Virales (Título + Gancho + Pregunta Polarizante + Descripción Legal)
    print("[*] Generando metadatos virales con tendencias de YouTube y Fair Use...")
    metadata = generate_video_metadata(
        original_title=original_title or video_id,
        original_url=url,
        is_short=is_short,
        creator_name=creator_name,
        source_lang=lang_to_use
    )
    hook_text = hook_override if hook_override else metadata.get("hook", "¡ANÁLISIS AL DETALLE!")

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
                if cliche.lower() in _gen_title.lower():
                    _gen_title = re.sub(re.escape(cliche), "", _gen_title, flags=re.IGNORECASE).strip()
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
            from .affiliates import format_pinned_comment_affiliates
            metadata["pinned_comment"] = format_pinned_comment_affiliates(debate_q)
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

    success_render = render_final_video(
        input_video=video_path,
        output_video=output_path,
        srt_subtitles=es_srt_path,
        dub_audio=dub_audio_path,
        force_short_format=is_short,
        hook_text=hook_text,
        is_official_content=is_official_content,
        archetype=archetype
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

    # 7. Co-Pilot Mode: Aprobación previa humana antes de publicar
    effective_copilot = is_copilot_enabled() if copilot_mode is None else copilot_mode
    if effective_copilot:
        print(f"[*] Modo Co-Pilot ACTIVO: Pausando publicación a la espera de aprobación en Telegram...")
        stage_pending_video(
            video_id=video_id,
            original_url=url,
            original_title=original_title,
            creator_name=creator_name,
            output_video_path=output_path,
            thumbnail_path=thumb_path if thumb_path.exists() else None,
            metadata=metadata,
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

        # Notificación en Telegram para aprobación
        try:
            from .telegram_bot import send_copilot_approval_request
            send_copilot_approval_request(
                video_id=video_id,
                title=metadata.get("title", original_title),
                creator=creator_name or "Rockstar Games",
                thumbnail_path=thumb_path if thumb_path.exists() else None,
                is_short=is_short,
                mode=mode,
                hook_text=hook_text,
                original_url=url
            )
        except Exception as e:
            print(f"[Pipeline] Info Co-Pilot Telegram: {e}")

        notify_macos(
            title="Co-Pilot: Vídeo Listo para Aprobación",
            message=f"{metadata.get('title', original_title)[:50]}... Pulsa en Telegram para publicar.",
            subtitle="GTA VI Hub Spain"
        )
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
                "privacy": effective_privacy
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
            privacy_status=effective_privacy,
            is_short=is_short,
            thumbnail_path=thumb_path if thumb_path.exists() else None,
            pinned_comment=metadata.get("pinned_comment")
        )
        if uploaded_yt_id:
            full_info["uploaded_youtube_url"] = f"https://youtu.be/{uploaded_yt_id}"

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(full_info, f, indent=2, ensure_ascii=False)

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

    # 8b. Registro en performance_tracker para el bucle de feedback de 24h
    try:
        from .performance_tracker import record_published_video
        record_published_video(
            video_id=video_id,
            title=original_title,
            youtube_url=full_info.get("uploaded_youtube_url", ""),
            base_score=0,
            velocity_vpd=0.0,
            days_old=0,
            is_short=is_short
        )
    except Exception as e:
        print(f"[Pipeline] Info performance_tracker: {e}")

    # 9. REGLAS ESTRICTAS DE LIMPIEZA
    # Limpiar todos los archivos de trabajo en temp/
    clean_temp_directory(video_id)
    gc.collect()  # Liberar buffers para GaTDSEQ

    # Si se subió con éxito y no se especificó guardar copia pesada, borrar el mp4 local
    if uploaded_yt_id and not keep_local_video:
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
        from .telegram_bot import send_telegram_notification, send_telegram_alert, send_telegram_photo
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
                else "💡 *Modo local:* Vídeo generado listo para revisión o publicación manual."
            )
            local_report = (
                "🎬 *VÍDEO RENDERIZADO EN DISCO (LOCAL)*\n"
                + ("═" * 36) + "\n\n"
                f"• *Título:* `{metadata.get('title', original_title)}`\n"
                f"• *Autor:* `{creator_name or 'Rockstar Games'}`\n"
                f"• *Archivo:* `{Path(output_path).name}`\n\n"
                f"{upload_reason}\n\n"
                "Para publicarlo ejecuta:\n"
                f"`./run.sh --url \"{url}\" --upload`"
            )
            if thumb_path and thumb_path.exists():
                send_telegram_photo(thumb_path, local_report)
            else:
                send_telegram_alert(local_report)
    except Exception as e:
        print(f"[Pipeline] Info Telegram: {e}")

    return full_info

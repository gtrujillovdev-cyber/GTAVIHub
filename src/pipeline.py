import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from .config import OUTPUT_DIR, TEMP_DIR
from .downloader import download_video_and_subtitles
from .translator import translate_srt, generate_video_metadata
from .dubber import generate_voiceover
from .video_editor import render_final_video, get_video_dimensions
from .channels import mark_video_processed
from .uploader import upload_to_youtube
from .social_publisher import SocialPublisher
from .thumbnail_generator import create_video_thumbnail
from .cleaner import clean_temp_directory, clean_uploaded_video_file, enforce_storage_limits

def process_single_video(
    url: str,
    video_id: str,
    original_title: str = "",
    creator_name: str = "",
    source_lang: str = "en",
    mode: str = "subs",
    force_short: Optional[bool] = None,
    auto_upload: bool = False,
    privacy_status: str = "private",
    keep_local_video: bool = False,
    publish_all: bool = False,
    dry_run: bool = False,
    stagger_delay: int = 12
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
    print(f"\n=======================================================")
    print(f"[▶] INICIANDO PROCESAMIENTO EDITORIAL: {video_id}")
    print(f"    Título Original: {original_title}")
    print(f"    Creador: {creator_name or 'Rockstar Games'}")
    print(f"    Idioma Origen: {source_lang.upper()}")
    print(f"    Modo: {'Subtítulos Dinámicos' if mode == 'subs' else 'Doblaje de Voz'}")
    print(f"    Auto-Subida: {'SÍ (' + privacy_status + ')' if auto_upload else 'NO'}")
    print(f"=======================================================")

    # Auditoría inicial de almacenamiento
    enforce_storage_limits(max_mb=1000)

    # 1. Descarga limpia
    video_path, srt_path, detected_lang = download_video_and_subtitles(url, video_id)
    if not video_path:
        print(f"[!] Falló la descarga del vídeo {video_id}. Abortando.")
        clean_temp_directory(video_id)
        return None

    lang_to_use = detected_lang if detected_lang in ["es", "en"] else source_lang

    # Detectar dimensiones y formato
    width, height = get_video_dimensions(video_path)
    is_vertical = (height > width)
    is_short = force_short if force_short is not None else is_vertical

    # 2. Procesar/Traducir subtítulos si existen
    es_srt_path = None
    if srt_path and srt_path.exists():
        es_srt_path = TEMP_DIR / f"{video_id}_es.srt"
        success_trans = translate_srt(srt_path, es_srt_path, source_lang=lang_to_use)
        if not success_trans:
            print("[Warning] No se pudieron traducir subtítulos, se continuará sin subtítulos quemados.")
            es_srt_path = None

    # 3. Doblaje de voz opcional
    dub_audio_path = None
    if mode == "dub" and lang_to_use != "es" and es_srt_path:
        dub_audio_path = TEMP_DIR / f"{video_id}_es_voice.mp3"
        generate_voiceover(es_srt_path, dub_audio_path)

    # 4. Generación de Metadatos Virales (Título MAYÚSCULAS + Gancho + Descripción Legal)
    print("[*] Generando metadatos virales con tendencias de YouTube y Fair Use...")
    metadata = generate_video_metadata(
        original_title=original_title or video_id,
        original_url=url,
        is_short=is_short,
        creator_name=creator_name,
        source_lang=lang_to_use
    )
    hook_text = metadata.get("hook", "¡ANÁLISIS AL DETALLE!")

    # 5. Renderizado final transformado
    prefix = "SHORT" if is_short else "VIDEO"
    output_filename = f"{prefix}_{video_id}_ES.mp4"
    output_path = OUTPUT_DIR / output_filename

    success_render = render_final_video(
        input_video=video_path,
        output_video=output_path,
        srt_subtitles=es_srt_path,
        dub_audio=dub_audio_path,
        force_short_format=is_short,
        hook_text=hook_text
    )

    if not success_render or not output_path.exists():
        print("[!] Error en el renderizado final del vídeo.")
        clean_temp_directory(video_id)
        return None

    # 6. Generación de Miniatura de alto CTR
    thumb_path = OUTPUT_DIR / f"{prefix}_{video_id}_thumb.jpg"
    create_video_thumbnail(
        video_path=output_path,
        output_thumb_path=thumb_path,
        hook_text=hook_text,
        creator_tag=creator_name,
        is_short=is_short
    )

    meta_path = OUTPUT_DIR / f"{prefix}_{video_id}_ES_info.json"
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

    # 7. Publicación (Multiplataforma o YouTube)
    uploaded_yt_id = None
    multiplatform_results = {}

    if publish_all:
        publisher = SocialPublisher(dry_run=dry_run)
        multiplatform_results = publisher.publish_all(
            video_path=output_path,
            metadata={
                "title": metadata.get("title", f"GTA 6 - {original_title}").upper(),
                "description": metadata.get("description", ""),
                "thumbnail_path": thumb_path if thumb_path.exists() else None
            },
            creator_name=creator_name or "Rockstar Games",
            stagger_delay_minutes=stagger_delay
        )
        full_info["multiplatform_urls"] = multiplatform_results
        if multiplatform_results.get("youtube"):
            full_info["uploaded_youtube_url"] = multiplatform_results["youtube"]
    elif auto_upload:
        uploaded_yt_id = upload_to_youtube(
            video_path=output_path,
            title=metadata.get("title", f"GTA 6 - {original_title}").upper(),
            description=metadata.get("description", ""),
            privacy_status=privacy_status,
            is_short=is_short,
            thumbnail_path=thumb_path if thumb_path.exists() else None
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

    # 9. REGLAS ESTRICTAS DE LIMPIEZA
    # Limpiar todos los archivos de trabajo en temp/
    clean_temp_directory(video_id)

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
    return full_info

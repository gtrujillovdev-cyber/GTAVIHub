import sys
import os
import glob
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from .config import TEMP_DIR

def download_video_and_subtitles(url: str, video_id: str) -> Tuple[Optional[Path], Optional[Path], str]:
    """
    Descarga el video (limitado a 1080p) y extrae los subtítulos disponibles
    en español o inglés (automáticos o manuales).
    Retorna: (video_path, srt_path, detected_lang)
    """
    output_template = str(TEMP_DIR / f"{video_id}.%(ext)s")
    
    # Paso 1: Descargar vídeo limpio
    cmd_video = [
        sys.executable, "-m", "yt_dlp",
        "--impersonate", "chrome",
        "--no-check-certificates",
        "--no-playlist",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url
    ]

    print(f"[*] Descargando vídeo de {url}...")
    try:
        subprocess.run(cmd_video, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Error al descargar vídeo {url}: {e.stderr.strip() if e.stderr else e}")
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

    detected_lang = "en"
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
                res = subprocess.run(cmd_subs, capture_output=True, text=True)
                # Buscar si se generó algún archivo srt o vtt
                found_subs = list(TEMP_DIR.glob(f"{video_id}*.srt")) + list(TEMP_DIR.glob(f"{video_id}*.vtt"))
                if found_subs:
                    chosen = found_subs[0]
                    # Si es VTT, convertirlo a SRT con ffmpeg
                    if chosen.suffix.lower() == ".vtt":
                        converted_srt = chosen.with_suffix(".srt")
                        subprocess.run(["ffmpeg", "-y", "-i", str(chosen), str(converted_srt)], capture_output=True)
                        if converted_srt.exists():
                            chosen = converted_srt
                    srt_path = chosen
                    detected_lang = lang_code
                    print(f"[*] Subtítulos descargados con éxito ({target_lang} -> {detected_lang})")
                    break
            except Exception:
                continue

    if not srt_path:
        print("[*] No se encontraron subtítulos automáticos en YouTube (se continuará sin ellos o con plantilla de clip)")

    return (video_path if video_path and video_path.exists() else None, srt_path, detected_lang)

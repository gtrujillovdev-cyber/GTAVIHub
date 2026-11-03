#!/usr/bin/env python3
"""
Simulacro 100% Real del Pipeline — Sin Subidas Públicas
Procesa el clip ganador de TGG con doblaje neural en español, subtítulos karaoke,
gancho, compliance Fair Use y enlaces de afiliados, enviándolo directamente a Telegram.
"""
import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.pipeline import process_single_video
from src.telegram_bot import send_telegram_video, send_telegram_alert

URL = "https://www.youtube.com/shorts/P38MIdiNOAA"
VIDEO_ID = "P38MIdiNOAA"
CREATOR = "TGG (Shorts)"
TITLE = "Why I Couldn't Explain Everything I Saw in GTA 6"

def main():
    print("=" * 70)
    print("🚀 PROCESANDO CLIP HIPOTÉTICO GANADOR: TGG")
    print(f"URL: {URL}")
    print("=" * 70)

    # 1. Ejecutar pipeline completo con doblaje neural en español + subtítulos + Fair Use
    result = process_single_video(
        url=URL,
        video_id=VIDEO_ID,
        mode="dub",
        auto_upload=False,
        force_short=True,
        keep_local_video=True,
        publish_all=False,
        original_title=TITLE,
        creator_name=CREATOR,
        source_lang="en"
    )

    if not result or not result.get("output_video"):
        print("[!] Error: No se generó el archivo de salida.")
        return

    out_file = Path(result["output_video"])
    print(f"[✓] Vídeo renderizado con éxito: {out_file} ({out_file.stat().st_size / (1024*1024):.2f} MB)")

    # 2. Cargar metadatos generados
    metadata = result.get("youtube_metadata", {})

    viral_title = metadata.get("title", TITLE)
    debate_q = metadata.get("debate_question", "¿Qué crees que vio TGG en GTA 6?")
    pinned = metadata.get("pinned_comment", "")
    full_desc = metadata.get("description", "")

    # 3. Enviar a Telegram
    print("[*] Enviando vídeo procesado a Telegram...")
    caption = (
        f"🎬 *[SIMULACRO DE PUBLICACIÓN — TGG]*\n\n"
        f"📌 *Título:* {viral_title}\n"
        f"👤 *Autor Original:* {CREATOR}\n"
        f"🔗 *Fuente:* {URL}\n"
        f"💬 *Debate Comunitario:* `{debate_q}`\n\n"
        f"⚠️ *ESTADO: SIMULACRO 100% REAL — CERO SUBIDAS PÚBLICAS*"
    )
    sent_video = send_telegram_video(out_file, caption=caption)
    if sent_video:
        print("[✓] Vídeo entregado a Telegram.")
    else:
        print("[!] No se pudo enviar el vídeo a Telegram.")

    # 4. Enviar ficha completa de metadatos (descripción legal, afiliados y pinned comment)
    meta_report = (
        f"📋 *FICHA TÉCNICA Y MONETIZACIÓN GENERADA:*\n\n"
        f"📌 *Primer Comentario Fijado (Afiliados & Debate):*\n"
        f"```\n{pinned}\n```\n\n"
        f"⚖️ *Descripción Oficial (Fair Use + Linktree):*\n"
        f"```\n{full_desc[:800]}...\n```"
    )
    send_telegram_alert(meta_report)
    print("[✓] Ficha técnica y enlaces de afiliados enviados a Telegram.")

if __name__ == "__main__":
    main()

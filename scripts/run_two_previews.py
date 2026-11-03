#!/usr/bin/env python3
"""
Renderiza y envía a Telegram los 2 clips seleccionados:
1. GTA Series Videos (Shorts) — In-Game Gameplay Clips
2. ElAnalistaDeBits (Shorts) — GTA VI vs GTA V Comparativa

CERO SUBIDAS PÚBLICAS. Higiene de disco estricta (temp/ purgado a 0 bytes tras cada clip).
"""
import os
import sys
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.pipeline import process_single_video
from src.telegram_bot import send_telegram_video, send_telegram_alert
from src.config import TEMP_DIR

CLIPS = [
    {
        "id": "Ocr0VNk_rlI",
        "url": "https://www.youtube.com/shorts/Ocr0VNk_rlI",
        "title": "GTA 6 - NEW Gameplay Clips",
        "creator": "GTA Series Videos (Shorts)",
        "mode": "subs",
        "label": "1/2: GAMEPLAY PURO IN-GAME (GTA Series Videos)"
    },
    {
        "id": "gvL9awaPiKU",
        "url": "https://www.youtube.com/shorts/gvL9awaPiKU",
        "title": "GTA VI vs GTA V",
        "creator": "ElAnalistaDeBits (Shorts)",
        "mode": "subs",
        "label": "2/2: COMPARATIVA GRÁFICA Y FÍSICAS (ElAnalistaDeBits)"
    }
]

def purge_temp():
    """Higiene estricta de disco: deja temp/ en 0 bytes."""
    print("[🧹 Higiene Disco] Limpiando temp/...")
    if TEMP_DIR.exists():
        for item in TEMP_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                print(f"  [!] No se pudo eliminar {item.name}: {e}")
    print("[✓] Directorio temp/ purgado a 0 bytes.")

def process_and_send(clip_info: dict, index: int):
    print("\n" + "=" * 70)
    print(f"🎬 PROCESANDO CLIP {index}/2: {clip_info['title']}")
    print(f"   Canal : {clip_info['creator']}")
    print(f"   URL   : {clip_info['url']}")
    print("=" * 70)

    result = process_single_video(
        url=clip_info["url"],
        video_id=clip_info["id"],
        mode=clip_info["mode"],
        auto_upload=False,
        force_short=True,
        keep_local_video=True,
        publish_all=False,
        original_title=clip_info["title"],
        creator_name=clip_info["creator"],
        source_lang="es"
    )

    if not result or not result.get("output_video"):
        print(f"[!] Error procesando clip {clip_info['id']}")
        purge_temp()
        return False

    out_file = Path(result["output_video"])
    print(f"[✓] Vídeo exportado: {out_file.name} ({out_file.stat().st_size / (1024*1024):.2f} MB)")

    metadata = result.get("youtube_metadata", {})
    viral_title = metadata.get("title", clip_info["title"])
    debate_q = metadata.get("debate_question", "¿Qué opinas?")
    pinned = metadata.get("pinned_comment", "")
    full_desc = metadata.get("description", "")

    # 1. Enviar vídeo a Telegram
    print(f"[*] Enviando {clip_info['label']} a Telegram...")
    caption = (
        f"🎬 *[PREVIEW #{index} — {clip_info['creator']}]*\n\n"
        f"📌 *Título:* {viral_title}\n"
        f"🎯 *Formato:* {clip_info['label']}\n"
        f"💬 *Debate:* `{debate_q}`\n\n"
        f"⚠️ *SIMULACRO LOCAL (CERO SUBIDAS PÚBLICAS)*"
    )
    sent = send_telegram_video(out_file, caption=caption)
    if sent:
        print(f"  [✓] Vídeo entregado a Telegram.")
    else:
        print(f"  [!] Falló el envío del vídeo a Telegram.")

    # 2. Enviar ficha de monetización
    meta_card = (
        f"📋 *FICHA DE MONETIZACIÓN #{index} ({clip_info['creator']}):*\n\n"
        f"📌 *Comentario Fijado (Afiliados Amazon & Redes):*\n"
        f"```\n{pinned}\n```\n\n"
        f"⚖️ *Atribución & Fair Use:*\n"
        f"• Fuente: {clip_info['url']}\n"
        f"• Licencia: Fair Use Art. 107 (Divulgación y Comparativa)"
    )
    send_telegram_alert(meta_card)

    # 3. Purga inmediata de temp
    purge_temp()
    return True

def main():
    print("=" * 70)
    print("🚀 INICIANDO PREVIEWS DE GAMEPLAY REAL Y COMPARATIVA")
    print("   Destino: Solo Telegram (Cero subidas)")
    print("=" * 70)

    for i, clip in enumerate(CLIPS, 1):
        process_and_send(clip, i)

    print("\n" + "=" * 70)
    print("🎉 AMBOS PREVIEWS ENVIADOS A TELEGRAM CON ÉXITO")
    print("   Temp final: 0 bytes.")
    print("=" * 70)

if __name__ == "__main__":
    main()

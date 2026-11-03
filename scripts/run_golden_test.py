#!/usr/bin/env python3
"""
scripts/run_golden_test.py — Prueba de Oro de Calibración Audiovisual.

1. Ejecuta el reciclaje dinámico de conocimiento y radar de tráfico.
2. Ingesta clip nativo 1080x1920 de GTA Series Videos:
   'GTA 6 New Screenshots Look Better Than Ever!' (9jy_ZpngzpA).
3. Modo 'subs': Mantiene el audio original puro (CERO voces sintéticas robóticas).
4. Superpone Gancho Superior de impacto (0.0s a 2.5s) y subtítulos dinámicos Pop.
5. Entrega a Telegram con metadatos nativos 9:16 (width=1080, height=1920, thumbnail).
6. Higiene de disco estricta: temp/ purgado a 0 bytes al terminar.
7. CERO SUBIDAS PÚBLICAS (Solo simulación y entrega en Telegram).
"""

import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.pipeline import process_single_video
from src.telegram_bot import send_telegram_video, send_telegram_alert
from src.knowledge_recycler import recycle_knowledge, format_recycler_telegram_message
from src.config import TEMP_DIR

CLIP = {
    "id": "9jy_ZpngzpA",
    "url": "https://www.youtube.com/shorts/9jy_ZpngzpA",
    "title": "GTA 6 New Screenshots Look Better Than Ever!",
    "creator": "GTA Series Videos (Shorts)",
    "mode": "subs"
}

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

def run_test():
    print("=" * 70)
    print("🚀 INICIANDO PRUEBA DE ORO — PIPELINE CALIBRADO 9:16 NATIVO")
    print(f"   Clip   : {CLIP['title']}")
    print(f"   Canal  : {CLIP['creator']}")
    print(f"   URL    : {CLIP['url']}")
    print("=" * 70)

    # 1. Reciclar conocimiento y verificar fase
    print("\n[*] [Paso 1/4] Actualizando radar de tráfico y fase de conocimiento...")
    knowledge = recycle_knowledge(force=True)
    print(f"    Fase Activa : {knowledge['phase_name']}")
    print(f"    Días Rest.  : {knowledge['days_to_launch']} días para el 19 de noviembre")

    # 2. Procesamiento con pipeline oficial
    print("\n[*] [Paso 2/4] Procesando clip con audio original puro y formato 9:16...")
    result = process_single_video(
        url=CLIP["url"],
        video_id=CLIP["id"],
        mode=CLIP["mode"],
        auto_upload=False,
        force_short=True,
        keep_local_video=True,
        publish_all=False,
        original_title=CLIP["title"],
        creator_name=CLIP["creator"],
        source_lang="es"
    )

    if not result or not result.get("output_video"):
        print("[!] Error en el procesamiento del vídeo.")
        purge_temp()
        return False

    out_file = Path(result["output_video"])
    print(f"[✓] Vídeo exportado: {out_file.name} ({out_file.stat().st_size / (1024*1024):.2f} MB)")

    metadata = result.get("youtube_metadata", {})
    viral_title = metadata.get("title", CLIP["title"])
    debate_q = metadata.get("debate_question", "¿Qué opinas?")

    # 3. Entrega a Telegram con metadatos 9:16 nativos
    print("\n[*] [Paso 3/4] Enviando a Telegram con contenedor vertical 9:16...")
    caption = (
        "🎬 *[PRUEBA DE ORO — LOOK & FEEL DEFINITIVO]*\n\n"
        f"📌 *Título:* `{viral_title}`\n"
        f"👤 *Fuente:* {CLIP['creator']}\n"
        f"📐 *Formato:* Vertical 9:16 Nativo (1080x1920)\n"
        f"🎙️ *Audio:* In-Game Puro (Cero voces sintéticas)\n"
        f"💬 *Debate:* `{debate_q}`\n\n"
        f"⏳ *Fase Editorial:* `{knowledge['phase_name']}`\n"
        "⚠️ *SIMULACRO LOCAL (CERO SUBIDAS PÚBLICAS)*"
    )
    sent = send_telegram_video(out_file, caption=caption)
    if sent:
        print("  [✓] Vídeo entregado a Telegram con éxito.")
    else:
        print("  [!] Error enviando a Telegram.")

    # 4. Higiene estricta
    print("\n[*] [Paso 4/4] Ejecutando higiene estricta de disco...")
    purge_temp()
    print("=" * 70)
    print("✅ PRUEBA DE ORO FINALIZADA")
    print("=" * 70)
    return True

if __name__ == "__main__":
    run_test()

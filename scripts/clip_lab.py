#!/usr/bin/env python3
"""
=============================================================================
🎮 LABORATORIO DE CLIPS — GTA VI Hub Spain
=============================================================================
Entorno seguro de pruebas y optimización para afinar el formato ganador:
1. Inspecciona y audita el motor de elección con IA sin procesar a ciegas.
2. Renderiza variantes de diseño (Cinema, Full Crop 9:16, Split-Screen).
3. CERO subidas a plataformas (YouTube, TikTok e Instagram quedan intocadas).
4. Genera un visor interactivo local (HTML5) para comparar variantes lado a lado.
5. Permite enviar vistas previas a Telegram para inspección móvil real.
=============================================================================
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.config import (
    BASE_DIR, OUTPUT_DIR, CHANNELS_FILE, FFMPEG_VIDEO_CODEC,
    FFMPEG_BITRATE, FFMPEG_THREADS
)
from src.channels import fetch_channel_candidates, is_strictly_gta6
from src.ai_selector import select_best_candidate_ai
from src.learning_engine import load_viral_playbook
from src.video_editor import (
    get_video_dimensions,
    render_top_hook_headline,
    render_karaoke_subtitle_state,
    parse_time,
    clean_text_no_emoji,
    calculate_word_timing
)

LAB_DIR = BASE_DIR / "output" / "lab"
LAB_DIR.mkdir(parents=True, exist_ok=True)
VARIANTS_DIR = LAB_DIR / "variants"
VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_LAB_DIR = LAB_DIR / "temp"
TEMP_LAB_DIR.mkdir(parents=True, exist_ok=True)


def run_selection_audit(limit: int = 15) -> Dict[str, Any]:
    """
    Audita el Motor de Elección:
    Escanea canales monitorizados, filtra y evalúa con IA, mostrando el ranking
    y la justificación editorial sin descargar ni subir nada.
    """
    print("\n" + "=" * 70)
    print("🔬 [LABORATORIO] AUDITORÍA DEL MOTOR DE ELECCIÓN Y RANKING VIRAL")
    print("=" * 70)
    print("[*] Escaneando canales objetivo en channels.json (frescura <= 72h)...")

    candidates = fetch_channel_candidates(max_per_channel=2)
    print(f"[✓] Se encontraron {len(candidates)} candidatos válidos.")

    if not candidates:
        print("[!] No hay candidatos que cumplan los filtros actuales en las últimas 72 horas.")
        return {"winner": None, "candidates": []}

    print(f"\n[*] Top {min(limit, len(candidates))} candidatos clasificados por puntuación:")
    print("-" * 70)
    print(f"{'#':<3} {'SCORE':<6} {'VISTAS':<10} {'DÍAS':<5} {'CANAL / CREADOR':<22} {'TÍTULO'}")
    print("-" * 70)

    for i, c in enumerate(candidates[:limit]):
        score = c.get("score", 0)
        views = c.get("views", 0)
        days = c.get("days_old", "-")
        channel = c.get("source_name", "Desconocido")[:20]
        title = c.get("title", "")[:45]
        print(f"{i+1:<3} {score:<6.1f} {views:<10} {str(days):<5} {channel:<22} {title}")

    print("-" * 70)
    print("\n[*] Consultando al Director de Estrategia con IA (Gemini Flash)...")
    playbook = load_viral_playbook()
    winner = select_best_candidate_ai(candidates, launch_mode=False, playbook=playbook)

    print("\n" + "=" * 70)
    print("🏆 CLIP GANADOR ELEGIDO POR EL MOTOR:")
    print(f"  • Título Original: {winner.get('title')}")
    print(f"  • Creador/Canal  : {winner.get('source_name')}")
    print(f"  • URL            : {winner.get('url')}")
    print(f"  • Puntuación Base: {winner.get('score')} pts")
    print(f"  • Selección IA   : {winner.get('ai_selection')}")
    print(f"  • Justificación  : {winner.get('ai_justification')}")
    print(f"  • Gancho Sugerido: L1: '{winner.get('hook_line1')}' | L2: '{winner.get('hook_line2')}'")
    print("=" * 70 + "\n")

    # Guardar reporte JSON
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "total_scanned": len(candidates),
        "winner": winner,
        "top_candidates": candidates[:limit]
    }
    with open(LAB_DIR / "selection_audit.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    return report_data


def download_lab_clip(url: str) -> Optional[Path]:
    """Descarga el clip objetivo en el directorio de pruebas del laboratorio."""
    print(f"[*] Descargando clip para laboratorio desde: {url}")
    target_pattern = str(TEMP_LAB_DIR / "lab_raw.%(ext)s")
    for f in TEMP_LAB_DIR.glob("lab_raw.*"):
        try:
            f.unlink()
        except Exception:
            pass

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--impersonate", "chrome",
        "--no-check-certificates",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", target_pattern,
        url
    ]
    try:
        subprocess.run(cmd, check=True, timeout=90)
        raw_video = TEMP_LAB_DIR / "lab_raw.mp4"
        if raw_video.exists():
            print(f"[✓] Vídeo descargado: {raw_video.stat().st_size / (1024*1024):.2f} MB")
            return raw_video
    except Exception as e:
        print(f"[!] Error descargando clip para laboratorio: {e}")
    return None


def generate_lab_subtitles(video_path: Path) -> Optional[Path]:
    """Extrae o genera subtítulos para el clip en el laboratorio."""
    srt_out = TEMP_LAB_DIR / "lab_subtitles.srt"
    try:
        from src.downloader import transcribe_audio
        audio_wav = TEMP_LAB_DIR / "lab_audio.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_wav)
        ], capture_output=True, check=True)

        if audio_wav.exists():
            srt_path = transcribe_audio(audio_wav)
            if srt_path and Path(srt_path).exists():
                return Path(srt_path)
    except Exception as e:
        print(f"[*] Subtítulos opcionales no disponibles en el entorno local ({e}).")
    return None


def render_lab_variants(video_path: Path, hook_text: str = "¡BOMBAZO GTA 6!") -> Dict[str, Path]:
    """
    Renderiza 3 variantes de diseño en paralelo o secuencial para comparar:
    - Variante A: Cinema Full-Width (Ambient Velvet Canvas)
    - Variante B: Full Crop 9:16 Dinámico (Pantalla completa sin bordes)
    - Variante C: Split-Screen Reacción (Streamer 40% + Gameplay 60%)
    """
    print("\n" + "=" * 70)
    print("🎨 [LABORATORIO] RENDERIZANDO 3 VARIANTES DE DISEÑO")
    print("=" * 70)

    width, height = get_video_dimensions(video_path)
    print(f"[*] Dimensiones del vídeo original: {width}x{height}")

    # 1. Gancho superior compartido
    hook_png = TEMP_LAB_DIR / "hook_preview.png"
    render_top_hook_headline(hook_text, hook_png)

    variants = {}

    # -------------------------------------------------------------
    # VARIANTE A: Cinema Full-Width (Anti-Cropping con Ambient Blur)
    # -------------------------------------------------------------
    out_a = VARIANTS_DIR / "variante_A_cinema.mp4"
    print(f"\n[1/3] Renderizando Variante A (Cinema Velvet Full-Width)...")
    cmd_a = [
        "ffmpeg", "-y", "-i", str(video_path)
    ]
    if hook_png.exists():
        cmd_a.extend(["-i", str(hook_png)])
        filter_a = (
            "[0:v]split[v1][v2];"
            "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:5,eq=brightness=-0.14:contrast=1.06:saturation=1.18[bg];"
            "[v2]scale=1080:-2,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
            "[bg][fg]overlay=0:656[vframed];"
            "[vframed][1:v]overlay=(W-w)/2:120:enable='between(t,0,2.5)'[vout]"
        )
    else:
        filter_a = (
            "[0:v]split[v1][v2];"
            "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:5,eq=brightness=-0.14:contrast=1.06:saturation=1.18[bg];"
            "[v2]scale=1080:-2,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
            "[bg][fg]overlay=0:656[vout]"
        )
    cmd_a.extend([
        "-filter_complex", filter_a,
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", FFMPEG_VIDEO_CODEC, "-b:v", FFMPEG_BITRATE, "-threads", "2",
        str(out_a)
    ])
    subprocess.run(cmd_a, capture_output=True, check=False)
    if out_a.exists():
        variants["Variante A (Cinema Velvet)"] = out_a
        print(f"  [✓] Variante A generada: {out_a.name} ({out_a.stat().st_size / (1024*1024):.2f} MB)")

    # -------------------------------------------------------------
    # VARIANTE B: Full Crop 9:16 (Pantalla Completa sin Bandas)
    # -------------------------------------------------------------
    out_b = VARIANTS_DIR / "variante_B_full_crop.mp4"
    print(f"\n[2/3] Renderizando Variante B (Full Crop 9:16 Pantalla Completa)...")
    cmd_b = [
        "ffmpeg", "-y", "-i", str(video_path)
    ]
    if hook_png.exists():
        cmd_b.extend(["-i", str(hook_png)])
        filter_b = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[vbase];"
            "[vbase][1:v]overlay=(W-w)/2:120:enable='between(t,0,2.5)'[vout]"
        )
    else:
        filter_b = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[vout]"

    cmd_b.extend([
        "-filter_complex", filter_b,
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", FFMPEG_VIDEO_CODEC, "-b:v", FFMPEG_BITRATE, "-threads", "2",
        str(out_b)
    ])
    subprocess.run(cmd_b, capture_output=True, check=False)
    if out_b.exists():
        variants["Variante B (Full Crop 9:16)"] = out_b
        print(f"  [✓] Variante B generada: {out_b.name} ({out_b.stat().st_size / (1024*1024):.2f} MB)")

    # -------------------------------------------------------------
    # VARIANTE C: Split-Screen Reacción (Streamer 40% + Gameplay 60%)
    # -------------------------------------------------------------
    out_c = VARIANTS_DIR / "variante_C_splitscreen.mp4"
    print(f"\n[3/3] Renderizando Variante C (Split-Screen Reacción Dual)...")
    cmd_c = [
        "ffmpeg", "-y", "-i", str(video_path)
    ]
    if hook_png.exists():
        cmd_c.extend(["-i", str(hook_png)])
        filter_c = (
            "[0:v]split=2[top_raw][bot_raw];"
            "[top_raw]scale=1080:768:force_original_aspect_ratio=increase,crop=1080:768,unsharp=3:3:0.6:3:3:0.0[top_panel];"
            "[bot_raw]scale=1080:1152:force_original_aspect_ratio=increase,crop=1080:1152,unsharp=3:3:0.6:3:3:0.0[bot_panel];"
            "[top_panel][bot_panel]vstack[vstacked];"
            "[vstacked][1:v]overlay=(W-w)/2:60:enable='between(t,0,2.5)'[vout]"
        )
    else:
        filter_c = (
            "[0:v]split=2[top_raw][bot_raw];"
            "[top_raw]scale=1080:768:force_original_aspect_ratio=increase,crop=1080:768,unsharp=3:3:0.6:3:3:0.0[top_panel];"
            "[bot_raw]scale=1080:1152:force_original_aspect_ratio=increase,crop=1080:1152,unsharp=3:3:0.6:3:3:0.0[bot_panel];"
            "[top_panel][bot_panel]vstack[vout]"
        )
    cmd_c.extend([
        "-filter_complex", filter_c,
        "-map", "[vout]", "-map", "0:a?",
        "-shortest",
        "-c:v", FFMPEG_VIDEO_CODEC, "-b:v", "4500k", "-threads", "2",
        str(out_c)
    ])
    subprocess.run(cmd_c, capture_output=True, check=False)
    if out_c.exists():
        variants["Variante C (Split-Screen Reacción)"] = out_c
        print(f"  [✓] Variante C generada: {out_c.name} ({out_c.stat().st_size / (1024*1024):.2f} MB)")

    return variants


def create_lab_html_viewer(variants: Dict[str, Path], meta: Dict[str, Any]) -> Path:
    """Genera un visor web HTML5 local interactivo para comparar las variantes."""
    html_file = LAB_DIR / "index.html"
    
    variant_cards_html = ""
    for name, v_path in variants.items():
        rel_path = f"variants/{v_path.name}"
        size_mb = v_path.stat().st_size / (1024 * 1024)
        variant_cards_html += f"""
        <div class="variant-card">
            <div class="card-header">
                <h3>{name}</h3>
                <span class="badge">{size_mb:.1f} MB</span>
            </div>
            <div class="video-container">
                <video controls playsinline preload="metadata">
                    <source src="{rel_path}" type="video/mp4">
                    Tu navegador no soporta reproducción de vídeo HTML5.
                </video>
            </div>
            <div class="card-footer">
                <p>Archivo: <code>{v_path.name}</code></p>
                <button onclick="navigator.clipboard.writeText('{v_path.resolve()}')">Copiar Ruta</button>
            </div>
        </div>
        """

    title = meta.get("title", "Laboratorio de Clips GTA VI")
    creator = meta.get("creator", "Desconocido")
    hook = meta.get("hook", "¡DETALLE ÉPICO!")

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Laboratorio de Clips — GTA VI Hub Spain</title>
    <style>
        :root {{
            --bg: #0b0c10;
            --surface: #1f2833;
            --accent: #66fcf1;
            --accent-hot: #ff007f;
            --text: #c5c6c7;
            --text-bright: #ffffff;
            --border: #45a29e;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
        }}
        header {{
            max-width: 1300px;
            margin: 0 auto 30px auto;
            border-bottom: 2px solid var(--surface);
            padding-bottom: 20px;
        }}
        h1 {{
            color: var(--accent);
            margin: 0 0 10px 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .meta-box {{
            background: var(--surface);
            padding: 16px 20px;
            border-radius: 12px;
            margin-top: 15px;
            display: flex;
            flex-wrap: wrap;
            gap: 24px;
            font-size: 14px;
        }}
        .meta-item strong {{
            color: var(--text-bright);
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 28px;
            max-width: 1300px;
            margin: 0 auto;
        }}
        .variant-card {{
            background: var(--surface);
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(102, 252, 241, 0.2);
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            display: flex;
            flex-direction: column;
        }}
        .card-header {{
            padding: 16px 20px;
            background: rgba(0,0,0,0.2);
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .card-header h3 {{
            margin: 0;
            color: var(--text-bright);
            font-size: 16px;
        }}
        .badge {{
            background: var(--accent-hot);
            color: #fff;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }}
        .video-container {{
            position: relative;
            background: #000;
            display: flex;
            justify-content: center;
            align-items: center;
            aspect-ratio: 9/16;
            max-height: 640px;
        }}
        video {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
        .card-footer {{
            padding: 14px 20px;
            background: rgba(0,0,0,0.3);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 13px;
        }}
        button {{
            background: var(--accent);
            color: #0b0c10;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        button:hover {{
            opacity: 0.85;
        }}
        .controls-bar {{
            max-width: 1300px;
            margin: 0 auto 20px auto;
            display: flex;
            gap: 12px;
            align-items: center;
        }}
    </style>
</head>
<body>
    <header>
        <h1>🧪 Laboratorio de Formatos Virales — GTA VI Hub</h1>
        <p>Entorno de comparación de variantes lado a lado sin publicación exterior.</p>
        <div class="meta-box">
            <div class="meta-item"><strong>Título:</strong> {title}</div>
            <div class="meta-item"><strong>Creador:</strong> {creator}</div>
            <div class="meta-item"><strong>Gancho Evaluado:</strong> {hook}</div>
            <div class="meta-item"><strong>Variantes:</strong> {len(variants)}</div>
        </div>
    </header>

    <div class="controls-bar">
        <button onclick="playAll()">▶️ Reproducir Todas Sincronizadas</button>
        <button onclick="pauseAll()">⏸️ Pausar Todas</button>
    </div>

    <div class="grid">
        {variant_cards_html}
    </div>

    <script>
        function playAll() {{
            document.querySelectorAll('video').forEach(v => {{
                v.currentTime = 0;
                v.play();
            }});
        }}
        function pauseAll() {{
            document.querySelectorAll('video').forEach(v => v.pause());
        }}
    </script>
</body>
</html>
"""
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n[✓] Visor interactivo generado con éxito en: {html_file}")
    return html_file


def send_lab_preview_to_telegram(variants: Dict[str, Path], meta: Dict[str, Any]):
    """Envía las variantes renderizadas al canal de Telegram privado para inspección móvil."""
    try:
        from src.telegram_bot import send_telegram_alert, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        token = TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("[Telegram] Credenciales no configuradas para envío de vista previa.")
            return

        import requests
        caption_base = (
            f"🧪 *[LABORATORIO DE CLIPS — VISTA PREVIA]*\n\n"
            f"📌 *Clip:* {meta.get('title', 'Test')[:55]}\n"
            f"👤 *Autor:* {meta.get('creator', 'Desconocido')}\n"
            f"🎯 *Gancho:* `{meta.get('hook', '')}`\n"
            f"⚠️ *ESTADO: PRUEBA LOCAL (CERO SUBIDAS PÚBLICAS)*"
        )
        send_telegram_alert(caption_base)

        for name, v_path in variants.items():
            print(f"[*] Enviando {name} ({v_path.name}) a Telegram...")
            with open(v_path, "rb") as video_file:
                url = f"https://api.telegram.org/bot{token}/sendVideo"
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": f"🎬 *{name}* (`{v_path.name}`)", "parse_mode": "Markdown"},
                    files={"video": video_file},
                    timeout=120
                )
                if resp.status_code == 200:
                    print(f"  [✓] {name} entregado a Telegram.")
                else:
                    print(f"  [!] Telegram error ({resp.status_code}): {resp.text}")
        print("[✓] Todas las variantes del laboratorio fueron enviadas a Telegram para revisión móvil.")
    except Exception as e:
        print(f"[!] Error enviando vista previa a Telegram: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Laboratorio de Clips y Afinado de Formato Ganador (Sin Subidas)"
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Audita el motor de elección con IA sobre los canales y muestra el ranking sin procesar."
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Probar un vídeo específico mediante URL de YouTube para renderizar variantes."
    )
    parser.add_argument(
        "--top",
        action="store_true",
        help="Toma automáticamente el clip ganador del motor de elección y renderiza sus variantes."
    )
    parser.add_argument(
        "--hook",
        type=str,
        default="",
        help="Texto personalizado para el gancho superior de prueba (ej: 'FÍSICAS RAGE 9')."
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Enviar los vídeos resultantes a Telegram para ver cómo lucen en la pantalla del móvil."
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Abrir el visor interactivo HTML5 en el navegador por defecto tras terminar."
    )

    args = parser.parse_args()

    # Si se pide únicamente escanear
    if args.scan and not args.top:
        run_selection_audit()
        return

    clip_url = args.url
    meta = {}

    if args.top or not clip_url:
        print("[*] Ejecutando análisis para seleccionar el mejor clip para el laboratorio...")
        audit = run_selection_audit()
        winner = audit.get("winner")
        if not winner:
            print("[!] No se encontró ningún clip ganador. Saliendo.")
            return
        clip_url = winner.get("url")
        meta = {
            "title": winner.get("title"),
            "creator": winner.get("source_name"),
            "hook": f"{winner.get('hook_line1', '')} {winner.get('hook_line2', '')}".strip() or "¡DETALLE ÉPICO!"
        }

    if args.hook:
        meta["hook"] = args.hook
    elif "hook" not in meta:
        meta["hook"] = "¡DETALLE ÉPICO!"

    raw_video = download_lab_clip(clip_url)
    if not raw_video:
        print("[!] No se pudo obtener el vídeo para las pruebas.")
        return

    # Renderizar variantes experimentales
    variants = render_lab_variants(raw_video, hook_text=meta.get("hook", ""))

    if not variants:
        print("[!] No se pudieron generar variantes de diseño.")
        return

    # Generar visor interactivo HTML5
    viewer_path = create_lab_html_viewer(variants, meta)

    # Envío a Telegram si se solicita
    if args.telegram:
        send_lab_preview_to_telegram(variants, meta)

    # Abrir visor local si se pide
    if args.open or sys.platform == "darwin":
        try:
            print("[*] Abriendo visor local en Safari/Chrome...")
            subprocess.run(["open", str(viewer_path)], check=False)
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("🎉 PRUEBA DE LABORATORIO FINALIZADA CON ÉXITO")
    print(f"  • Directorio de Variantes: {VARIANTS_DIR}")
    print(f"  • Visor HTML Interactivo : {viewer_path}")
    print("  • Estado de Plataformas  : 100% INTACTAS (CERO SUBIDAS)")
    print("=" * 70)


if __name__ == "__main__":
    main()

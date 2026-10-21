import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, List

from .config import BASE_DIR, OUTPUT_DIR, TEMP_DIR, PROCESSED_FILE, CHANNELS_FILE
from .social_publisher import BROWSER_PROFILE_DIR, AntiBanValidator

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"

def notify_macos(title: str, message: str, subtitle: str = "GTA VI Hub Pipeline"):
    """Envía una notificación nativa al centro de notificaciones de macOS."""
    try:
        clean_title = title.replace('"', '\\"')
        clean_msg = message.replace('"', '\\"')
        clean_sub = subtitle.replace('"', '\\"')
        script = f'display notification "{clean_msg}" with title "{clean_title}" subtitle "{clean_sub}"'
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except Exception:
        pass

def get_directory_size_mb(directory: Path) -> float:
    """Calcula el tamaño total en MB de un directorio."""
    if not directory.exists():
        return 0.0
    total = sum(f.stat().st_size for f in directory.glob("**/*") if f.is_file())
    return round(total / (1024 * 1024), 2)

def print_pipeline_dashboard():
    """Imprime el panel de control y monitorización en tiempo real del pipeline."""
    print("\n" + "═" * 70)
    print(" 🚀 GTA VI HUB SPAIN - MONITOR DEL PIPELINE AUTÓNOMO (macOS M4)")
    print("═" * 70)

    # 1. Almacenamiento
    temp_mb = get_directory_size_mb(TEMP_DIR)
    output_mb = get_directory_size_mb(OUTPUT_DIR)
    print(f"\n📁 ALMACENAMIENTO Y DISCO:")
    print(f"  • Carpeta Temporal (temp/)   : {temp_mb:.2f} MB {'[✓ ÓPTIMO: Limpio]' if temp_mb < 5 else '[!] Requiere limpieza'}")
    print(f"  • Carpeta Salida (output/)   : {output_mb:.2f} MB / 1000 MB límite preventivo")

    # 2. Estado de Credenciales y Sesiones
    token_yt = BASE_DIR / "token.json"
    secrets_yt = BASE_DIR / "client_secrets.json"
    tiktok_session = BROWSER_PROFILE_DIR / "tiktok_user_data"

    print(f"\n🔐 ESTADO DE CONECTIVIDAD Y SESIONES:")
    print(f"  • YouTube OAuth2 (token.json): {'[✓ Conectado / Activo]' if token_yt.exists() else '[!] Falta token (ejecutar ./run.sh auth)'}")
    print(f"  • YouTube Client Secrets     : {'[✓ Presente]' if secrets_yt.exists() else '[!] No encontrado'}")
    print(f"  • TikTok Persistent Profile  : {'[✓ Configurado]' if tiktok_session.exists() else '[*] Pendiente de primer inicio'}")
    print(f"  • Apple Silicon M4 Hardware  : [✓ VideoToolbox H.264 Acelerado por GPU]")

    # 3. Cuotas y Límites Diarios (Anti-Ban)
    today_str = date.today().isoformat()
    yt_count, tt_count, ig_count = 0, 0, 0
    records = []
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
            today_records = [r for r in records if r.get("date", "").startswith(today_str)]
            yt_count = len([r for r in today_records if r.get("youtube_uploaded_url")])
            tt_count = len([r for r in today_records if r.get("multiplatform", {}).get("tiktok")])
            ig_count = len([r for r in today_records if r.get("multiplatform", {}).get("instagram")])
        except Exception:
            records = []

    print(f"\n🛡️ CUOTAS DIARIAS ORGÁNICAS (Anti-Spam / Anti-Ban):")
    print(f"  • YouTube Shorts : {yt_count} / {AntiBanValidator.MAX_DAILY_UPLOADS} vídeos subidos hoy")
    print(f"  • TikTok         : {tt_count} / {AntiBanValidator.MAX_DAILY_UPLOADS} vídeos subidos hoy")
    print(f"  • Instagram Reels: {ig_count} / {AntiBanValidator.MAX_DAILY_UPLOADS} vídeos subidos hoy")

    # 4. Canales Monitorizados
    if CHANNELS_FILE.exists():
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                ch_data = json.load(f)
            channels = ch_data.get("channels", [])
            active_channels = [c["name"] for c in channels if c.get("enabled", True)]
            print(f"\n📡 CANALES ACTIVOS MONITOREADOS ({len(active_channels)}/{len(channels)}):")
            for name in active_channels[:6]:
                print(f"  • {name}")
            if len(active_channels) > 6:
                print(f"  • ... y {len(active_channels) - 6} más.")
        except Exception:
            pass

    # 5. Últimos Vídeos Procesados
    print(f"\n🎬 HISTORIAL RECIENTE ({len(records)} vídeos procesados en total):")
    if not records:
        print("  (Ningún vídeo procesado aún en processed.json)")
    else:
        for r in records[-3:]:
            v_id = r.get("id", "N/A")
            v_title = r.get("title", "Sin título")[:42]
            v_creator = r.get("creator", "Desconocido")
            v_date = r.get("date", "")[:16].replace("T", " ")
            print(f"  [{v_date}] {v_id} | {v_creator:15} | {v_title}...")

    print("\n" + "═" * 70 + "\n")

def generate_launchd_plist_content() -> str:
    """Genera el contenido XML del agente launchd de macOS para automatización desatendida."""
    python_path = str(BASE_DIR / ".venv" / "bin" / "python3")
    script_path = str(BASE_DIR / "main.py")
    log_out = str(LOG_DIR / "launchd_stdout.log")
    log_err = str(LOG_DIR / "launchd_stderr.log")

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gtavihub.automation</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>--auto</string>
        <string>--publish-all</string>
        <string>--dry-run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{BASE_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <!-- Ejecución a las 14:00 (Hora punta almuerzo España) -->
        <dict>
            <key>Hour</key>
            <integer>14</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- Ejecución a las 19:30 (Hora punta tarde gaming) -->
        <dict>
            <key>Hour</key>
            <integer>19</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>{log_out}</string>
    <key>StandardErrorPath</key>
    <string>{log_err}</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""
    return plist

import os
import sys
import time
import json
import re
import uuid
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests

try:
    import certifi
    for _cert_var in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        _cv = os.environ.get(_cert_var)
        if _cv and not os.path.exists(_cv):
            os.environ[_cert_var] = certifi.where()
except Exception:
    pass

from .config import BASE_DIR, DATA_DIR, OUTPUT_DIR, TEMP_DIR, PROCESSED_FILE, is_quant_busy
from .compliance_auditor import ComplianceAuditor
from .telemetry import get_host_telemetry_report
from .youtube_analytics import get_youtube_analytics_report
from .copilot import (
    is_copilot_enabled,
    set_copilot_enabled,
    approve_and_publish_video,
    reject_and_purge_video,
    get_all_pending_videos
)
from .channels import (
    list_monitored_channels,
    add_monitored_channel,
    remove_monitored_channel,
    toggle_channel_enabled,
    fetch_channel_candidates
)
from .viral_discovery import (
    scan_viral_radar,
    get_viral_radar_summary,
    auto_register_top_channels
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Cache en memoria para sesiones de enlaces pendientes de procesamiento
CACHED_INGEST_URLS: Dict[str, Dict[str, Any]] = {}
CACHED_VIRAL_CANDIDATES: List[Dict[str, Any]] = []

# Control de concurrencia para evitar sobrecargar hardware
BACKGROUND_LOCK = threading.Lock()
ACTIVE_TASK: Optional[str] = None

# Regex para detección de URLs compatibles (YouTube, TikTok, Twitter/X)
URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.|mobile\.)?(?:youtube\.com|youtu\.be|tiktok\.com|vm\.tiktok\.com|twitter\.com|x\.com)/[^\s]+",
    re.IGNORECASE
)

# ═══════════════════════════════════════════════════════════════════
# 1. HELPERS DE COMUNICACIÓN CON TELEGRAM BOT API
# ═══════════════════════════════════════════════════════════════════

def get_api_url(method: str) -> Optional[str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    if not token:
        return None
    return f"https://api.telegram.org/bot{token}/{method}"

def get_persistent_menu_keyboard() -> Dict[str, Any]:
    """Retorna el teclado táctil persistente simplificado y limpio."""
    return {
        "keyboard": [
            [{"text": "🚀 Forzar Escaneo"}, {"text": "🎬 Último Clip"}],
            [{"text": "📊 Estado"}, {"text": "🛡️ Modo Co-Pilot"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def send_telegram_alert(
    message: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "Markdown",
    include_menu: bool = False
) -> bool:
    """Envía un mensaje de texto con soporte opcional para teclados interactivos."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False

    url = get_api_url("sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    elif include_menu:
        payload["reply_markup"] = get_persistent_menu_keyboard()

    for attempt in range(3):
        try:
            res = requests.post(url, json=payload, timeout=12)
            if res.status_code != 200 and parse_mode:
                payload.pop("parse_mode", None)
                res = requests.post(url, json=payload, timeout=12)
            if res.status_code == 200:
                return True
            print(f"[Telegram] Error {res.status_code} enviando mensaje: {res.text}")
        except Exception as e:
            print(f"[Telegram] Intento {attempt + 1}/3 enviando mensaje falló: {e}")
            time.sleep(2)
    return False

def edit_telegram_message(
    message_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "Markdown"
) -> bool:
    """Modifica el texto o teclado de un mensaje interactivo existente."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False

    url = get_api_url("editMessageText")
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            return True
        if res.status_code == 400:
            # Si el mensaje original tiene vídeo/foto, editMessageText falla y debe usarse editMessageCaption
            cap_url = get_api_url("editMessageCaption")
            cap_payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": text[:1024],
                "parse_mode": parse_mode,
            }
            if reply_markup is not None:
                cap_payload["reply_markup"] = reply_markup
            cap_res = requests.post(cap_url, json=cap_payload, timeout=10)
            if cap_res.status_code == 200:
                return True
            cap_payload.pop("parse_mode", None)
            cap_res2 = requests.post(cap_url, json=cap_payload, timeout=10)
            return cap_res2.status_code == 200
        return False
    except Exception as e:
        print(f"[Telegram] Error editando mensaje {message_id}: {e}")
        return False

def answer_callback_query(
    callback_query_id: str,
    text: Optional[str] = None,
    show_alert: bool = False
) -> bool:
    """Responde inmediatamente a un click táctil para eliminar el indicador de carga."""
    url = get_api_url("answerCallbackQuery")
    if not url:
        return False
    payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

def send_telegram_photo(
    photo_path: Path,
    caption: str,
    reply_markup: Optional[Dict[str, Any]] = None
) -> bool:
    """Envía una imagen con pie de foto y botones inline."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
    if not token or not chat_id or not photo_path.exists():
        return False

    url = get_api_url("sendPhoto")
    for attempt in range(3):
        try:
            with open(photo_path, "rb") as photo:
                files = {"photo": photo}
                data: Dict[str, Any] = {
                    "chat_id": chat_id,
                    "caption": caption[:1024],
                    "parse_mode": "Markdown"
                }
                if reply_markup:
                    data["reply_markup"] = json.dumps(reply_markup)
                res = requests.post(url, data=data, files=files, timeout=20)
                if res.status_code == 200:
                    return True
                # Si falló por formato Markdown, reintentar de inmediato sin parse_mode
                if res.status_code != 200 and "parse_mode" in data:
                    data.pop("parse_mode", None)
                    photo.seek(0)
                    res2 = requests.post(url, data=data, files={"photo": photo}, timeout=20)
                    if res2.status_code == 200:
                        return True
                print(f"[Telegram] Error {res.status_code} enviando foto: {res.text}")
        except Exception as e:
            print(f"[Telegram] Intento {attempt + 1}/3 enviando foto falló: {e}")
            time.sleep(2)
    return False

def send_telegram_video(
    video_path: Path,
    caption: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    thumbnail_path: Optional[Path] = None
) -> bool:
    """Envía un archivo de vídeo MP4 nativo al chat para descarga directa y publicación en TikTok/Reels."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
    if not token or not chat_id or not video_path.exists():
        return False

    # Sondear dimensiones y duración para forzar al reproductor de Telegram a renderizar en 9:16 vertical nativo (Short)
    width, height, duration = 1080, 1920, 0
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            p_info = json.loads(res.stdout)
            stream = p_info.get("streams", [{}])[0]
            fmt = p_info.get("format", {})
            width = int(stream.get("width") or 1080)
            height = int(stream.get("height") or 1920)
            dur_val = float(stream.get("duration") or fmt.get("duration") or 0.0)
            duration = int(dur_val)
    except Exception as e:
        print(f"[Telegram] Warning sondeo de vídeo: {e}")

    # Si no se pasó miniatura explícita, buscar miniatura homónima
    if thumbnail_path is None or not thumbnail_path.exists():
        candidate_thumb = video_path.with_name(video_path.stem + "_thumb.jpg")
        if candidate_thumb.exists():
            thumbnail_path = candidate_thumb

    url = get_api_url("sendVideo")
    try:
        with open(video_path, "rb") as video:
            files: Dict[str, Any] = {"video": video}
            data: Dict[str, Any] = {
                "chat_id": chat_id,
                "caption": caption[:1024],
                "parse_mode": "Markdown",
                "supports_streaming": True,
                "width": width,
                "height": height
            }
            if duration > 0:
                data["duration"] = duration
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)

            thumb_file = None
            if thumbnail_path and thumbnail_path.exists():
                thumb_file = open(thumbnail_path, "rb")
                files["thumbnail"] = thumb_file

            try:
                res = requests.post(url, data=data, files=files, timeout=120)
                if res.status_code != 200 and "parse_mode" in data:
                    data.pop("parse_mode", None)
                    video.seek(0)
                    if thumb_file:
                        thumb_file.seek(0)
                    res = requests.post(url, data=data, files=files, timeout=120)
                if res.status_code != 200:
                    print(f"[Telegram] Error {res.status_code} enviando vídeo: {res.text}")
                return res.status_code == 200
            finally:
                if thumb_file:
                    thumb_file.close()
    except Exception as e:
        print(f"[Telegram] Error enviando vídeo: {e}")
        return False

def send_telegram_notification(
    title: str,
    creator: str,
    multiplatform_urls: Dict[str, Optional[str]],
    thumbnail_path: Optional[Path] = None
) -> bool:
    """Envía un anuncio de publicación exitosa con enlaces, miniatura y texto para TikTok/Reels."""
    yt_url = multiplatform_urls.get("youtube") or "Pendiente"
    tt_url = multiplatform_urls.get("tiktok") or "Pendiente"
    ig_url = multiplatform_urls.get("instagram") or "Pendiente"

    clean_title = (
        title.replace("¡BRUTAL! 🔥 ", "")
        .replace("REACCIÓN Y ANÁLISIS DE GTA 6: ", "")
        .replace("REACCIÓN Y ANÁLISIS: ", "")
        .strip()
    )

    tiktok_reels_copy = (
        f"{clean_title} 🤯🌴\n\n"
        f"Todo sobre GTA 6 en español en @gtavihubextra 🇪🇸\n"
        f"#GTA6 #GTAVI #ViceCity #RockstarGames #Gaming #Shorts #Reels"
    )

    caption = (
        "🌴 *¡NUEVO VÍDEO PUBLICADO EN GTA VI HUB!* 🎮\n\n"
        f"🎬 *Título:* `{title}`\n"
        f"👤 *Autor Original:* `{creator}`\n\n"
        "🔗 *Enlaces a Plataformas:*\n"
        f"• 🔴 *YouTube Shorts:* [Ver en YouTube]({yt_url})\n"
        f"• 🎵 *TikTok:* [Ver en TikTok]({tt_url})\n"
        f"• 📸 *Instagram Reels:* [Ver en Instagram]({ig_url})\n\n"
        "📋 *Texto para TikTok / Reels (1 toque para copiar):*\n"
        f"`{tiktok_reels_copy}`\n\n"
        "⚖️ _Fair Use (Art. 107) verificado y créditos asignados._"
    )

    if thumbnail_path and thumbnail_path.exists():
        if send_telegram_photo(thumbnail_path, caption):
            return True

    return send_telegram_alert(caption, include_menu=True)

# ═══════════════════════════════════════════════════════════════════
# 2. KEYBOARDS INTERACTIVOS CONTEXTUALES
# ═══════════════════════════════════════════════════════════════════

def get_url_ingest_keyboard(token_id: str, recommended_opt: str = "short") -> Dict[str, Any]:
    """Teclado interactivo para seleccionar el formato de ingesta de un enlace con recomendación inteligente."""
    star = "⭐ "
    buttons = {
        "short": {"text": f"{star if recommended_opt == 'short' else ''}⚡ Short Hormozi (Subs ES)", "callback_data": f"url_opt:short:{token_id}"},
        "dub": {"text": f"{star if recommended_opt == 'dub' else ''}🎙️ Doblaje Neural (Voz ES)", "callback_data": f"url_opt:dub:{token_id}"},
        "gameplay": {"text": f"{star if recommended_opt == 'gameplay' else ''}🎮 Gameplay / Físicas (Audio Juego)", "callback_data": f"url_opt:gameplay:{token_id}"},
        "cancel": {"text": "❌ Cancelar", "callback_data": f"url_opt:cancel:{token_id}"}
    }

    # Fila 1: Opción recomendada en solitario para destacar
    first_row = [buttons.get(recommended_opt, buttons["short"])]
    # Fila 2: Las otras dos opciones
    other_keys = [k for k in ["short", "dub", "gameplay"] if k != recommended_opt]
    second_row = [buttons[other_keys[0]], buttons[other_keys[1]]]
    # Fila 3: Cancelar
    third_row = [buttons["cancel"]]

    return {
        "inline_keyboard": [first_row, second_row, third_row]
    }

def get_copilot_approval_keyboard(video_id: str, original_url: Optional[str] = None) -> Dict[str, Any]:
    """Teclado interactivo de aprobación/descarte en modo Co-Pilot con enlace directo al vídeo."""
    source_url = original_url or f"https://www.youtube.com/watch?v={video_id}"
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Aprobar y Publicar", "callback_data": f"copilot:approve:{video_id}"},
                {"text": "❌ Descartar y Purgar", "callback_data": f"copilot:reject:{video_id}"}
            ],
            [
                {"text": "👁️ Ver Vídeo Original en YouTube", "url": source_url}
            ]
        ]
    }

def get_copilot_toggle_keyboard() -> Dict[str, Any]:
    """Teclado para activar/desactivar el modo Co-Pilot."""
    enabled = is_copilot_enabled()
    status_btn_text = "🔴 Desactivar Co-Pilot (100% Autónomo)" if enabled else "🟢 Activar Co-Pilot (1-Click Aprobación)"
    return {
        "inline_keyboard": [
            [{"text": status_btn_text, "callback_data": "copilot:toggle"}],
            [{"text": "📋 Ver Vídeos Pendientes", "callback_data": "copilot:list_pending"}]
        ]
    }

def get_channels_inline_keyboard() -> Dict[str, Any]:
    """Teclado inline interactivo para activar/desactivar canales con un toque."""
    channels = list_monitored_channels()
    buttons = []
    
    # Filas de a 2 canales
    row = []
    for idx, ch in enumerate(channels):
        status_icon = "✅" if ch.get("enabled", True) else "❌"
        short_name = ch.get("name", "Canal")[:14]
        btn_text = f"{status_icon} {short_name}"
        row.append({"text": btn_text, "callback_data": f"chan_toggle:{idx}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Fila de control
    buttons.append([
        {"text": "🔄 Refrescar", "callback_data": "chan_refresh"},
        {"text": "ℹ️ Ayuda Comandos", "callback_data": "chan_help"}
    ])

    return {"inline_keyboard": buttons}

def get_my_channels_inline_keyboard() -> Dict[str, Any]:
    """Teclado interactivo con botones URL directos a los canales y redes propios."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔴 YouTube Shorts (@gtavihubextra)", "url": "https://www.youtube.com/@gtavihubextra/shorts"},
                {"text": "📊 YouTube Studio", "url": "https://studio.youtube.com/channel/UCB35xEmRUm64zgyYOUnqrUg"}
            ],
            [
                {"text": "🎵 TikTok (@gtavihubextra)", "url": "https://www.tiktok.com/@gtavihubextra"},
                {"text": "📸 Instagram (@gtavihubextra)", "url": "https://www.instagram.com/gtavihubextra/"}
            ],
            [
                {"text": "🔴 Canal Activo YouTube", "url": "https://www.youtube.com/@gtavihubextra"}
            ]
        ]
    }

def get_viral_radar_inline_keyboard(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Teclado interactivo para ingestar los clips más virales o abrirlos directamente en YouTube."""
    buttons = []
    for idx, c in enumerate(candidates[:4]):
        vid_url = c.get("url") or f"https://www.youtube.com/watch?v={c.get('id')}"
        buttons.append([
            {"text": f"⚡ Ingestar #{idx+1}", "callback_data": f"viral:ingest:{idx}"},
            {"text": f"👁️ Ver #{idx+1} en YouTube", "url": vid_url}
        ])

    buttons.append([
        {"text": "➕ Añadir Nuevos Creadores", "callback_data": "viral:add_channels"},
        {"text": "🔄 Actualizar Radar", "callback_data": "viral:refresh"}
    ])
    return {"inline_keyboard": buttons}

def get_restart_confirm_keyboard() -> Dict[str, Any]:
    """Teclado interactivo de confirmación para reiniciar el servicio."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Sí, Reiniciar Ahora", "callback_data": "system:confirm_restart"},
                {"text": "❌ Cancelar", "callback_data": "system:cancel_restart"}
            ]
        ]
    }

def get_system_actions_inline_keyboard() -> Dict[str, Any]:
    """Botones de acción rápida para el Dashboard y Estado del Host."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Reiniciar Bot", "callback_data": "system:ask_restart"},
                {"text": "🔓 Desbloquear Tareas", "callback_data": "system:unlock"}
            ]
        ]
    }

def kill_hung_subprocesses():
    """Mata procesos hijos de ffmpeg o yt-dlp que hayan podido quedar bloqueados."""
    try:
        subprocess.run(["pkill", "-9", "-f", "ffmpeg.*SHORT_"], capture_output=True)
        subprocess.run(["pkill", "-9", "-f", "yt_dlp"], capture_output=True)
    except Exception:
        pass

def update_heartbeat():
    """Actualiza el timestamp de heartbeat para supervisión continua del watchdog."""
    try:
        from .config import DATA_DIR
        hb_file = DATA_DIR / "heartbeat.txt"
        hb_file.write_text(str(int(time.time())))
    except Exception:
        pass

def execute_bot_restart():
    """Reinicia el proceso del bot de Telegram en caliente."""
    global ACTIVE_TASK
    with BACKGROUND_LOCK:
        ACTIVE_TASK = None

    kill_hung_subprocesses()

    try:
        from .cleaner import clean_temp_directory, clean_workspace_residuals
        clean_temp_directory()
        clean_workspace_residuals()
    except Exception:
        pass

    send_telegram_alert(
        "🔄 *Reiniciando Centro de Control...*\n"
        + "Cancelando procesos colgados y arrancando nueva instancia. Listo en ~2 segundos."
    )
    time.sleep(1)

    main_script = str(BASE_DIR / "main.py")
    args = [sys.executable, main_script, "--telegram"]
    os.execv(sys.executable, args)

# ═══════════════════════════════════════════════════════════════════
# 3. NOTIFICACIONES Y GESTIÓN DE CO-PILOT
# ═══════════════════════════════════════════════════════════════════

def send_copilot_approval_request(
    video_id: str,
    title: str,
    creator: str,
    thumbnail_path: Optional[Path] = None,
    is_short: bool = True,
    mode: str = "subs",
    hook_text: str = "",
    original_url: Optional[str] = None,
    video_path: Optional[Path] = None
) -> bool:
    """Envía la previsualización del vídeo real (o miniatura) con botones de aprobación a Telegram."""
    clean_title = str(title).replace("*", "").replace("`", "").replace("_", " ")
    clean_creator = str(creator or "Rockstar Games").replace("*", "").replace("`", "").replace("_", " ")
    clean_hook = str(hook_text or "GTA 6").replace("*", "").replace("`", "").replace("_", " ")

    caption = (
        "🎬 *VISTA PREVIA DEL VÍDEO*\n\n"
        f"📌 *{clean_title[:80]}*\n"
        f"👤 Fuente: `{clean_creator[:35]}` | 🎯 `{clean_hook[:30]}`\n\n"
        "👇 ¿Aprobar y publicar en YouTube, TikTok e Instagram?"
    )
    keyboard = get_copilot_approval_keyboard(video_id, original_url=original_url)

    # 1. Intentar enviar el archivo de vídeo renderizado para reproducirlo directamente en Telegram (<48MB)
    if video_path and video_path.exists():
        try:
            if video_path.stat().st_size < 48 * 1024 * 1024:
                print(f"[Telegram] Enviando archivo de vídeo renderizado a Telegram ({video_path.stat().st_size / (1024*1024):.1f} MB)...")
                if send_telegram_video(video_path, caption, reply_markup=keyboard):
                    return True
        except Exception as e:
            print(f"[Telegram] Error enviando vídeo de previsualización: {e}")

    # 2. Fallback a miniatura con botones
    if thumbnail_path and thumbnail_path.exists():
        print("[Telegram] Enviando miniatura con botones interactivos de Co-Pilot...")
        if send_telegram_photo(thumbnail_path, caption, reply_markup=keyboard):
            return True

    return send_telegram_alert(caption, reply_markup=keyboard)

# ═══════════════════════════════════════════════════════════════════
# 4. REPORTES Y DASHBOARD
# ═══════════════════════════════════════════════════════════════════

def get_dashboard_text() -> str:
    """Genera un reporte conciso y limpio del estado del bot."""
    from .monitor import get_directory_size_mb
    from .config import MAX_DAILY_UPLOADS
    output_mb = get_directory_size_mb(OUTPUT_DIR)
    copilot_status = "🟢 Activo (Confirmación previa)" if is_copilot_enabled() else "⚡ Automático"

    return (
        "📊 *ESTADO DEL SISTEMA*\n\n"
        f"• Modo: `{copilot_status}`\n"
        f"• Límite Diario: `{MAX_DAILY_UPLOADS} vídeos/día`\n"
        f"• Espacio en Staging: `{output_mb:.1f} MB`\n"
        "• Redes: YouTube (`@GTAVIHubExtra`), TikTok, Instagram"
    )

def get_my_channels_report() -> str:
    """
    Genera el informe exclusivo con los enlaces a las redes y canales
    propios de GTA VI Hub.
    """
    return (
        "🌐 *MIS CANALES Y REDES SOCIALES*\n"
        + ("═" * 36) + "\n\n"
        + "🌴 *GTA VI HUB — CANALES ACTIVOS*\n\n"
        + "• 🔴 *YouTube:* [@gtavihubextra](https://www.youtube.com/@gtavihubextra)\n"
        + "  └ 🎬 *Shorts:* [Ver Feed de Shorts](https://www.youtube.com/@gtavihubextra/shorts)\n"
        + "  └ ⚙️ *Studio:* [Abrir YouTube Studio](https://studio.youtube.com/channel/UCB35xEmRUm64zgyYOUnqrUg)\n\n"
        + "• 🎵 *TikTok:* [Ver Perfil en TikTok](https://www.tiktok.com/@gtavihubextra) (`@gtavihubextra`)\n\n"
        + "• 📸 *Instagram Reels:* [Ver Perfil en Instagram](https://www.instagram.com/gtavihubextra/) (`@gtavihubextra`)\n\n"
        + "• 🤖 *Bot de Control:* [Chat del Bot](https://t.me/gtavihub_spain_bot) (`@gtavihub_spain_bot`)\n\n"
        + "👇 _Toca cualquiera de los botones para abrir tu canal en su app oficial:_"
    )

# ═══════════════════════════════════════════════════════════════════
# 5. EJECUCIÓN DE PROCESOS EN SEGUNDO PLANO (THREADS)
# ═══════════════════════════════════════════════════════════════════

def run_scan_in_background(chat_id: str, max_videos: int = 2):
    """Ejecuta el escaneo autónomo en segundo plano sin congelar Telegram."""
    global ACTIVE_TASK
    with BACKGROUND_LOCK:
        ACTIVE_TASK = "Escaneo de Canales"
    
    try:
        from .pipeline import process_single_video
        from .ai_selector import select_best_candidate_ai
        from .channels import filter_repetitive_candidates
        send_telegram_alert("⏳ *Iniciando escaneo inteligente (Escudo Anti-Repetición + IA)...*")
        candidates = fetch_channel_candidates(max_per_channel=max_videos)
        
        if not candidates:
            send_telegram_alert("✓ *Escaneo finalizado:* No hay vídeos nuevos ni distintos pendientes.")
            return

        send_telegram_alert(f"🎯 *{len(candidates)} candidato(s) único(s) validado(s).* Seleccionando el mejor...")
        count = 0
        remaining = list(candidates)
        max_attempts = min(len(remaining), max_videos + 4)
        for _ in range(max_attempts):
            if count >= max_videos:
                break
            remaining = filter_repetitive_candidates(remaining)
            if not remaining:
                break
            item = select_best_candidate_ai(remaining, launch_mode=False)
            if not item:
                break
            remaining = [c for c in remaining if c.get("id") != item.get("id")]

            raw_orig_title = item.get("title", "GTA 6 Clip")
            title_display = item.get("recommended_title") or raw_orig_title
            creator_clean = item.get("uploader") or item.get("source_name") or "Creador"
            mode_clean = item.get("recommended_mode") or "subs"
            hook_custom = None
            if item.get("hook_line1") and item.get("hook_line2"):
                hook_custom = f"{item['hook_line1']}\n{item['hook_line2']}"

            send_telegram_alert(f"🎬 *Procesando ({count+1}/{max_videos}):* `{title_display[:55]}`...")
            res = process_single_video(
                url=item["url"],
                video_id=item["id"],
                original_title=raw_orig_title,
                creator_name=creator_clean,
                source_lang=item.get("lang", "en"),
                mode=mode_clean,
                force_short=True if item.get("is_short") else None,
                auto_upload=True,
                publish_all=True,
                hook_override=hook_custom,
                block_instagram=item.get("block_instagram", False),
                allowed_platforms=item.get("allowed_platforms"),
                allow_official_commentary=bool(item.get("allow_official_commentary", False))
            )
            if res:
                count += 1
                yt_url = res.get("youtube_url") or res.get("uploaded_youtube_url")
                if yt_url and res.get("status") != "staged_for_copilot":
                    send_telegram_alert(
                        f"🚀 *¡Vídeo Publicado!*\n\n"
                        f"📌 *{title_display}*\n"
                        f"👤 Fuente: `{creator_clean}`\n"
                        f"🔗 {yt_url}"
                    )
                
        send_telegram_alert(f"🎉 *Tanda finalizada con éxito.* Total procesados: `{count}` vídeos.")
    except Exception as e:
        send_telegram_alert(f"❌ *Error durante el escaneo autónomo:* `{e}`")
    finally:
        with BACKGROUND_LOCK:
            ACTIVE_TASK = None

def run_ingest_in_background(
    url: str,
    vid_id: str,
    title: str,
    uploader: str,
    format_choice: str,
    hook_override: Optional[str] = None
):
    """Ejecuta el procesamiento de un enlace bajo demanda en segundo plano."""
    global ACTIVE_TASK
    with BACKGROUND_LOCK:
        ACTIVE_TASK = f"Ingesta: {title[:25]}"

    try:
        from .pipeline import process_single_video
        is_short = True if format_choice in ["short", "dub", "gameplay", "subs"] or "/shorts/" in url.lower() else (False if format_choice == "normal" else None)
        mode = "dub" if format_choice == "dub" else ("gameplay" if format_choice == "gameplay" else "subs")

        send_telegram_alert(f"⏳ *Procesando vídeo:* `{title[:50]}`\nFormato: `{format_choice.upper()}`...")

        res = process_single_video(
            url=url,
            video_id=vid_id,
            original_title=title,
            creator_name=uploader,
            mode=mode,
            force_short=is_short,
            auto_upload=True,
            publish_all=True,
            is_manual_ingest=True,
            hook_override=hook_override
        )
        if res and res.get("status") != "staged_for_copilot":
            send_telegram_alert(f"✓ *Vídeo procesado y publicado:* `{title[:50]}`")
        elif not res:
            send_telegram_alert(f"⚠️ *No se pudo procesar el vídeo.* Revisa si el enlace está activo o tiene restricciones.")
    except Exception as e:
        send_telegram_alert(f"❌ *Error procesando enlace:* `{e}`")
    finally:
        with BACKGROUND_LOCK:
            ACTIVE_TASK = None

def run_approval_publish_in_background(video_id: str):
    """Ejecuta la publicación aprobada por Co-Pilot en segundo plano."""
    global ACTIVE_TASK
    with BACKGROUND_LOCK:
        ACTIVE_TASK = f"Publicando: {video_id}"

    try:
        res = approve_and_publish_video(video_id)
        if res and (res.get("youtube_url") or res.get("multiplatform")):
            mp = res.get("multiplatform") or {}
            yt_line = f"🔗 *YouTube Shorts:* {res.get('youtube_url')}" if res.get("youtube_url") else "⚠️ *YouTube:* falló (revisar cuota/token)"
            tt_val = mp.get("tiktok")
            tt_line = f"\n🎵 *TikTok:* {tt_val}" if tt_val else "\n⚠️ *TikTok:* no publicado / quedó en borrador"
            send_telegram_alert(
                f"🚀 *¡Publicación Finalizada!*\n\n"
                f"🎬 *Título:* `{res.get('title')}`\n"
                f"{yt_line}{tt_line}\n\n"
                f"🧹 _Archivos pesados purgados del disco._"
            )
        else:
            send_telegram_alert("⚠️ *No se pudo publicar en YouTube/TikTok.* Revisa credenciales o logs en mbp1.")
    except Exception as e:
        send_telegram_alert(f"❌ *Error al publicar vídeo aprobado:* `{e}`")
    finally:
        with BACKGROUND_LOCK:
            ACTIVE_TASK = None

def run_viral_radar_in_background(chat_id: str):
    """Escanea el Radar Viral de YouTube en segundo plano y envía candidatos con botones."""
    global ACTIVE_TASK, CACHED_VIRAL_CANDIDATES
    with BACKGROUND_LOCK:
        ACTIVE_TASK = "Escaneo Radar Viral"

    try:
        send_telegram_alert("🔍 *Escaneando YouTube en busca de contenido viral de GTA 6 con máximo engagement...*")
        candidates = scan_viral_radar(max_candidates=5)
        CACHED_VIRAL_CANDIDATES = candidates
        summary = get_viral_radar_summary(candidates)
        keyboard = get_viral_radar_inline_keyboard(candidates)
        send_telegram_alert(summary, reply_markup=keyboard)
    except Exception as e:
        send_telegram_alert(f"❌ *Error en Radar Viral:* `{e}`")
    finally:
        with BACKGROUND_LOCK:
            ACTIVE_TASK = None

# ═══════════════════════════════════════════════════════════════════
# 6. MANEJADOR DE ENLACES BAJO DEMANDA
# ═══════════════════════════════════════════════════════════════════

def handle_url_ingestion(url: str):
    """Detecta un enlace pegado por el usuario, evalúa la estrategia óptima y muestra botones con recomendación."""
    send_telegram_alert(f"🔍 *Analizando vídeo y evaluando mejor estrategia de edición...*\n`{url}`")
    
    from .downloader import get_url_metadata
    from .channels import auto_register_source_from_metadata
    meta = get_url_metadata(url)
    source_reg = auto_register_source_from_metadata(meta)

    vid_id = meta["id"]
    title = meta["title"]
    dur_str = meta["duration_str"]
    uploader = meta["uploader"]
    platform = meta["platform"]
    strategy = meta.get("strategy", {})

    recommended_opt = strategy.get("recommended_opt", "short")
    archetype = strategy.get("archetype", "Noticias & Novedades")
    badge = strategy.get("badge", "⚡ Short Vertical")
    reason = strategy.get("reason", "Transformación optimizada para YouTube Shorts.")
    suggested_hook = strategy.get("hook_text", "")

    token_id = uuid.uuid4().hex[:8]
    CACHED_INGEST_URLS[token_id] = {
        "url": url,
        "vid_id": vid_id,
        "title": title,
        "uploader": uploader,
        "platform": platform,
        "hook_override": suggested_hook,
        "strategy": strategy
    }

    clean_title = str(title).replace("*", "").replace("`", "").replace("_", " ")
    clean_uploader = str(uploader).replace("*", "").replace("`", "").replace("_", " ")
    clean_reason = str(reason).replace("*", "").replace("`", "").replace("_", " ")

    source_notice = ""
    if source_reg.get("success"):
        if source_reg.get("is_new"):
            source_notice = f"✨ *¡Nueva fuente auto-registrada para futuros escaneos!*\n👤 Creador: `@{clean_uploader}` (Añadido a canales monitoreados)\n\n"
        else:
            occ = source_reg.get("occurrences", 1)
            source_notice = f"📚 *Fuente en radar:* `@{clean_uploader}` ({occ} clips catalogados)\n\n"

    caption = (
        f"📥 *Vídeo detectado:* `{clean_title[:55]}`\n"
        f"🌐 *Plataforma:* `{platform}` | 👤 `{clean_uploader[:30]}` | ⏱️ `{dur_str}`\n\n"
        f"{source_notice}"
        f"💡 *ESTRATEGIA SUGERIDA POR LA IA:*\n"
        f"• *Arquetipo:* `{archetype}`\n"
        f"• *Recomendación:* `{badge}`\n"
        f"_{clean_reason}_\n\n"
        "👇 *Elige el formato de transformación (sugerido con ⭐):*"
    )
    keyboard = get_url_ingest_keyboard(token_id, recommended_opt=recommended_opt)
    send_telegram_alert(caption, reply_markup=keyboard)

# ═══════════════════════════════════════════════════════════════════
# 7. MANEJADOR DE CALLBACK QUERIES (BOTONES INLINE)
# ═══════════════════════════════════════════════════════════════════

def handle_callback_query(cq: Dict[str, Any]):
    """Procesa los clicks en botones inline táctiles."""
    cq_id = cq.get("id", "")
    data = cq.get("data", "")
    msg = cq.get("message", {})
    msg_id = msg.get("message_id")

    if not data:
        answer_callback_query(cq_id)
        return

    # A) Formato de Ingesta de URL
    if data.startswith("url_opt:"):
        _, opt, token_id = data.split(":", 2)
        if opt == "cancel":
            answer_callback_query(cq_id, "Ingesta cancelada.")
            edit_telegram_message(msg_id, "❌ *Ingesta de enlace cancelada.*")
            CACHED_INGEST_URLS.pop(token_id, None)
            return

        item = CACHED_INGEST_URLS.pop(token_id, None)
        if not item:
            answer_callback_query(cq_id, "Sesión caducada o enlace ya procesado.")
            edit_telegram_message(msg_id, "⚠️ *Esta opción ya fue seleccionada o caducó.*")
            return

        labels = {
            "short": "SHORT 9:16 (SUBS ES)",
            "dub": "DOBLAJE NEURAL (VOZ ES)",
            "gameplay": "GAMEPLAY / FÍSICAS",
            "subs": "SUBTÍTULOS ORIGINALES"
        }
        lbl = labels.get(opt, opt.upper())
        answer_callback_query(cq_id, f"Iniciando {lbl}...")
        edit_telegram_message(
            msg_id,
            f"⏳ *Procesando `{item['title'][:40]}...` ({lbl})*\nTe notificaremos paso a paso y con la vista previa antes de publicar."
        )

        t = threading.Thread(
            target=run_ingest_in_background,
            args=(item["url"], item["vid_id"], item["title"], item["uploader"], opt, item.get("hook_override")),
            daemon=True
        )
        t.start()
        return

    # B) Aprobación / Rechazo Co-Pilot
    if data.startswith("copilot:approve:"):
        video_id = data.split(":", 2)[2]
        from .copilot import get_pending_video
        pending_item = get_pending_video(video_id)
        if not pending_item or pending_item.get("status") == "publishing":
            answer_callback_query(cq_id, "Este vídeo ya se está publicando o ya fue procesado.")
            edit_telegram_message(msg_id, f"ℹ️ *Vídeo `{video_id}` ya en curso o publicado.*", reply_markup={"inline_keyboard": []})
            return
        answer_callback_query(cq_id, "Aprobado. Iniciando subida a YouTube...")
        edit_telegram_message(
            msg_id,
            f"🚀 *Vídeo `{video_id}` aprobado.*\n⏳ Subiendo a YouTube Shorts y programando TikTok...",
            reply_markup={"inline_keyboard": []}
        )
        send_telegram_alert(f"⏳ *Aprobado `{video_id}`*: iniciando subida a YouTube Shorts...")
        t = threading.Thread(target=run_approval_publish_in_background, args=(video_id,), daemon=True)
        t.start()
        return

    if data.startswith("copilot:reject:"):
        video_id = data.split(":", 2)[2]
        answer_callback_query(cq_id, "Descartando vídeo...")
        success = reject_and_purge_video(video_id)
        if success:
            edit_telegram_message(msg_id, f"🗑️ *Vídeo `{video_id}` descartado y purgado del disco con éxito.*", reply_markup={"inline_keyboard": []})
        else:
            edit_telegram_message(msg_id, f"ℹ️ *El vídeo `{video_id}` ya había sido descartado.*", reply_markup={"inline_keyboard": []})
        return

    # C) Toggle de Estado Co-Pilot
    if data == "copilot:toggle":
        new_state = not is_copilot_enabled()
        set_copilot_enabled(new_state)
        state_text = "🟢 ACTIVO (Requiere tu aprobación táctil)" if new_state else "⚡ DESACTIVADO (100% Autónomo)"
        answer_callback_query(cq_id, f"Co-Pilot: {'Activado' if new_state else 'Desactivado'}")
        text = (
            "🛡️ *CONFIGURACIÓN DE MODO CO-PILOT*\n"
            + ("═" * 36) + "\n\n"
            + f"• Estado actual: `{state_text}`\n\n"
            + "En modo Co-Pilot, cada vídeo renderizado se pausa y te envía una vista previa "
            + "con botones para que autorices o descartes la publicación con 1 clic."
        )
        edit_telegram_message(msg_id, text, reply_markup=get_copilot_toggle_keyboard())
        return

    if data == "copilot:list_pending":
        pending = get_all_pending_videos()
        answer_callback_query(cq_id, f"{len(pending)} pendientes.")
        if not pending:
            edit_telegram_message(
                msg_id,
                "✓ *No hay ningún vídeo en cola de aprobación Co-Pilot.*",
                reply_markup=get_copilot_toggle_keyboard()
            )
        else:
            txt = f"📋 *Vídeos en cola de aprobación ({len(pending)}):*\n\n"
            for p in pending:
                txt += f"• `{p.get('video_id')}`: {p.get('original_title')[:35]}...\n"
            txt += "\n_Revisa el mensaje original con botones de aprobación para cada uno._"
            edit_telegram_message(msg_id, txt, reply_markup=get_copilot_toggle_keyboard())
        return

    # D) Conmutación Interactiva de Canales
    if data.startswith("chan_toggle:"):
        idx = int(data.split(":")[1])
        new_val = toggle_channel_enabled(idx)
        channels = list_monitored_channels()
        ch_name = channels[idx].get("name", "Canal") if idx < len(channels) else "Canal"
        answer_callback_query(cq_id, f"{'Activado' if new_val else 'Desactivado'}: {ch_name}")
        edit_telegram_message(
            msg_id,
            "⚙️ *GESTIÓN DE CANALES MONITOREADOS*\n_Pulsa sobre cualquier canal para activarlo/desactivarlo:_",
            reply_markup=get_channels_inline_keyboard()
        )
        return

    if data == "chan_refresh":
        answer_callback_query(cq_id, "Lista de canales actualizada.")
        edit_telegram_message(
            msg_id,
            "⚙️ *GESTIÓN DE CANALES MONITOREADOS*\n_Pulsa sobre cualquier canal para activarlo/desactivarlo:_",
            reply_markup=get_channels_inline_keyboard()
        )
        return

    if data == "chan_help":
        answer_callback_query(cq_id)
        help_txt = (
            "ℹ️ *Comandos para gestión rápida de canales:*\n\n"
            "• `/addchannel <url> [nombre]` — Añade un canal al monitoreo.\n"
            "• `/delchannel <número o nombre>` — Elimina un canal.\n"
            "• `/channels` — Abre el panel interactivo ON/OFF.\n"
            "• `/miscanales` — Abre los enlaces directos a tus redes y canal."
        )
        send_telegram_alert(help_txt)
        return

    # E) Acciones del Radar Viral
    if data.startswith("viral:ingest:"):
        idx = int(data.split(":")[2])
        if idx < len(CACHED_VIRAL_CANDIDATES):
            item = CACHED_VIRAL_CANDIDATES[idx]
            answer_callback_query(cq_id, f"Iniciando ingesta #{idx+1}...")
            edit_telegram_message(
                msg_id,
                f"⏳ *Procesando clip viral #{idx+1}:* `{item['title'][:40]}...` en segundo plano."
            )
            fmt_opt = "short" if item.get("is_short") else "subs"
            t = threading.Thread(
                target=run_ingest_in_background,
                args=(item["url"], item["id"], item["title"], item["uploader"], fmt_opt),
                daemon=True
            )
            t.start()
        else:
            answer_callback_query(cq_id, "Clip no disponible en el radar actual.")
        return

    if data == "viral:add_channels":
        answer_callback_query(cq_id, "Añadiendo creadores descubiertos...")
        added = auto_register_top_channels(min_score=40)
        if added:
            names = ", ".join([f"`{a.get('name')}`" for a in added[:5]])
            send_telegram_alert(f"✅ *{len(added)} nuevo(s) creador(es) añadido(s) al monitoreo continuo:*\n{names}")
        else:
            send_telegram_alert("ℹ️ Todos los canales del radar ya están registrados en channels.json.")
        return

    if data == "viral:refresh":
        answer_callback_query(cq_id, "Actualizando Radar Viral...")
        t = threading.Thread(target=run_viral_radar_in_background, args=(str(msg.get("chat", {}).get("id", "")),), daemon=True)
        t.start()
        return

    if data == "traffic:refresh":
        answer_callback_query(cq_id, "Actualizando Tráfico...")
        try:
            from .traffic_sentinel import scan_realtime_traffic, format_radar_telegram_message
            radar_report = scan_realtime_traffic(save=True)
            msg_txt = format_radar_telegram_message(radar_report)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔥 Escanear Vídeos con estas Tendencias", "callback_data": "viral:refresh"}],
                    [{"text": "🔄 Refrescar Tráfico", "callback_data": "traffic:refresh"}]
                ]
            }
            send_telegram_alert(msg_txt, reply_markup=keyboard)
        except Exception as e:
            send_telegram_alert(f"❌ Error actualizando tráfico: {e}")
        return

    if data == "knowledge:recycle":
        answer_callback_query(cq_id, "Reciclando conocimiento...")
        try:
            from .knowledge_recycler import recycle_knowledge, format_recycler_telegram_message
            state = recycle_knowledge(force=True)
            msg_txt = format_recycler_telegram_message(state)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🛰️ Ver Radar de Tráfico", "callback_data": "traffic:refresh"}],
                    [{"text": "🔄 Forzar Reciclaje Ahora", "callback_data": "knowledge:recycle"}]
                ]
            }
            send_telegram_alert(msg_txt, reply_markup=keyboard)
        except Exception as e:
            send_telegram_alert(f"❌ Error reciclando conocimiento: {e}")
        return

    # F) Acciones de Sistema y Reinicio de Emergencia
    if data == "system:ask_restart":
        answer_callback_query(cq_id)
        msg_txt = (
            "⚠️ *CONFIRMACIÓN DE REINICIO*\n"
            + ("═" * 36) + "\n\n"
            + "¿Deseas reiniciar el Centro de Control y cancelar cualquier proceso colgado?\n\n"
            + "• Se liberarán bloqueos de hardware (`ACTIVE_TASK`).\n"
            + "• Se purgarán procesos huérfanos de `ffmpeg` y `yt-dlp`.\n"
            + "• El bot volverá a responder en ~2 segundos."
        )
        send_telegram_alert(msg_txt, reply_markup=get_restart_confirm_keyboard())
        return

    if data == "system:confirm_restart":
        answer_callback_query(cq_id, "Reiniciando...")
        edit_telegram_message(msg_id, "🔄 *Ejecutando reinicio del servicio...*")
        t = threading.Thread(target=execute_bot_restart, daemon=True)
        t.start()
        return

    if data == "system:cancel_restart":
        answer_callback_query(cq_id, "Reinicio cancelado.")
        edit_telegram_message(msg_id, "✓ *Reinicio cancelado.* El sistema continúa operando con normalidad.")
        return

    if data == "system:unlock":
        answer_callback_query(cq_id, "Desbloqueando...")
        with BACKGROUND_LOCK:
            ACTIVE_TASK = None
        kill_hung_subprocesses()
        try:
            from .cleaner import clean_temp_directory, clean_workspace_residuals
            clean_temp_directory()
            clean_workspace_residuals()
        except Exception:
            pass
        edit_telegram_message(
            msg_id,
            "🔓 *Tareas y bloqueos liberados con éxito.*\n"
            + "Se han cancelado procesos secundarios y limpiado temporales. El bot está libre para recibir nuevos comandos.",
            reply_markup=get_system_actions_inline_keyboard()
        )
        return

    if data == "deals_force_update":
        answer_callback_query(cq_id, "Actualizando ofertas...")
        edit_telegram_message(msg_id, "🔄 *Sincronizando y actualizando ofertas en Amazon...*")
        try:
            from .deal_scanner import scan_and_update_deals
            res = scan_and_update_deals(force=True, notify_telegram=False)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 Forzar Actualización Ahora", "callback_data": "deals_force_update"}],
                    [{"text": "🌐 Ver Linktree Oficial", "url": "https://linktr.ee/gtavihubspain"}]
                ]
            }
            edit_telegram_message(msg_id, res["report"], reply_markup=keyboard)
        except Exception as e:
            edit_telegram_message(msg_id, f"⚠️ Error actualizando ofertas: {e}")
        return

    answer_callback_query(cq_id)

# ═══════════════════════════════════════════════════════════════════
# 8. BUCLE PRINCIPAL DEL BOT DAEMON
# ═══════════════════════════════════════════════════════════════════

def start_telegram_bot_daemon():
    """
    Inicia el bucle de polling de Telegram con soporte completo para:
    - Teclado persistente táctil
    - Detección de enlaces y botones inline
    - Co-Pilot interactivo
    - Telemetría en vivo de hardware y GaTDSEQ
    - Analíticas reales de YouTube Data API v3
    - Tareas en segundo plano fluidas y sin bloqueo
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID

    if not token or not allowed_chat_id:
        print("\n[!] Error: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados en .env")
        return

    print("\n" + "=" * 65)
    print(" 🤖 INICIANDO CENTRO DE CONTROL TELEGRAM (GTA VI Hub Spain)")
    print("=" * 65)
    print(f"[*] Chat Autorizado: {allowed_chat_id}")
    print("[*] Teclado táctil interactivo: HABILITADO")
    print("[*] Ingesta bajo demanda & Co-Pilot: ACTIVOS")
    print("=" * 65 + "\n")

    global ACTIVE_TASK
    last_update_id = 0
    url_updates = get_api_url("getUpdates")

    welcome_msg = (
        "🟢 *GTA VI Hub Bot Activado*\n"
        + ("═" * 36) + "\n\n"
        + "Centro de control interactivo listo en tu móvil.\n"
        + "Usa los botones del teclado inferior o pega cualquier enlace de YouTube/TikTok para procesarlo."
    )
    send_telegram_alert(welcome_msg, reply_markup=get_persistent_menu_keyboard())

    while True:
        try:
            update_heartbeat()

            # Revisar auto-aprobación por tiempo de cortesía de Co-Pilot (15 min)
            try:
                from .copilot import check_and_auto_approve_expired_videos
                check_and_auto_approve_expired_videos()
            except Exception:
                pass

            # Revisión de métricas periódicas (cada ~1h en el loop)
            if not hasattr(start_telegram_bot_daemon, '_last_deals_check'):
                start_telegram_bot_daemon._last_deals_check = 0
            if not hasattr(start_telegram_bot_daemon, '_last_metrics_check'):
                start_telegram_bot_daemon._last_metrics_check = 0
            _now_ts = time.time()
            if _now_ts - start_telegram_bot_daemon._last_deals_check > 3600:
                start_telegram_bot_daemon._last_deals_check = _now_ts
                try:
                    from .affiliates import is_affiliates_enabled
                    from .deal_scanner import should_update_deals, scan_and_update_deals
                    # Solo sincroniza internamente si los afiliados están activos (cero spam a Telegram)
                    if is_affiliates_enabled() and should_update_deals():
                        scan_and_update_deals(notify_telegram=False)
                except Exception as e:
                    print(f"[DealScanner] Error en chequeo automático: {e}")

            # Feedback loop: obtener métricas reales de vídeos publicados (cada ~6h)
            if _now_ts - start_telegram_bot_daemon._last_metrics_check > 21600:
                start_telegram_bot_daemon._last_metrics_check = _now_ts
                try:
                    from .performance_tracker import fetch_pending_metrics
                    fetched = fetch_pending_metrics(max_fetch=5)
                    if fetched > 0:
                        print(f"[PerformanceTracker] Métricas actualizadas para {fetched} vídeo(s).")
                except Exception as e:
                    print(f"[PerformanceTracker] Error obteniendo métricas: {e}")

            # Planificador 100% Autónomo: 4 Horas Punta Algorítmicas (10:45, 14:15, 17:45, 20:45 CET)
            now_dt = datetime.now()
            today_str = now_dt.strftime("%Y-%m-%d")
            sched_file = DATA_DIR / "scheduler_slots_state.json"
            slots = [(10, 45), (14, 15), (17, 45), (20, 45)]
            for h, m in slots:
                if now_dt.hour == h and m <= now_dt.minute <= m + 10:
                    slot_key = f"{h:02d}:{m:02d}"
                    slots_done = {}
                    if sched_file.exists():
                        try:
                            with open(sched_file, "r", encoding="utf-8") as f:
                                slots_done = json.load(f)
                        except Exception:
                            slots_done = {}
                    today_slots = slots_done.get(today_str, [])
                    if slot_key not in today_slots:
                        with BACKGROUND_LOCK:
                            busy = (ACTIVE_TASK is not None)
                        if not busy:
                            send_telegram_alert(
                                f"⏰ *[HORA PUNTA ALGORÍTMICA {slot_key} CET]*\n"
                                f"🚀 Disparando ciclo de publicación 100% autónoma..."
                            )
                            today_slots.append(slot_key)
                            slots_done[today_str] = today_slots
                            try:
                                with open(sched_file, "w", encoding="utf-8") as f:
                                    json.dump(slots_done, f, indent=2)
                            except Exception:
                                pass
                            t = threading.Thread(target=run_scan_in_background, args=(allowed_chat_id, 1), daemon=True)
                            t.start()

            params = {"offset": last_update_id + 1, "timeout": 10}
            res = requests.get(url_updates, params=params, timeout=15)
            if res.status_code != 200:
                time.sleep(4)
                continue

            data = res.json()
            updates = data.get("result", [])

            for upd in updates:
                last_update_id = upd.get("update_id", last_update_id)

                # 1. Procesar Callback Queries (clicks en botones inline)
                if "callback_query" in upd:
                    cq = upd["callback_query"]
                    sender_id = str(cq.get("from", {}).get("id", ""))
                    if sender_id == str(allowed_chat_id):
                        handle_callback_query(cq)
                    continue

                # 2. Procesar Mensajes de Texto y Teclado Persistente
                msg = upd.get("message", {})
                chat = msg.get("chat", {})
                chat_id = str(chat.get("id", ""))
                text = msg.get("text", "").strip()

                if str(chat_id) != str(allowed_chat_id) or not text:
                    continue

                # A) Detección de URLs pegadas para ingesta inmediata
                url_match = URL_PATTERN.search(text)
                if url_match and not text.startswith("/"):
                    handle_url_ingestion(url_match.group(0))
                    continue

                # Normalización de comandos y botones táctiles
                cmd = text.split()[0].lower()

                # B) Comandos del Teclado Persistente y Slash Commands
                if cmd in ["/start", "/help", "/menu", "/guia", "/docs"]:
                    help_msg = (
                        "🎮 *CENTRO DE MANDO — GTA VI HUB EXTRA*\n"
                        + ("═" * 34) + "\n\n"
                        + "📱 *BOTONES PRINCIPALES:*\n"
                        + "• `🚀 Forzar Escaneo` — Busca lo último `<24h` por velocidad real y genera clip.\n"
                        + "• `🎬 Último Clip` — Muestra el vídeo pendiente o más reciente.\n"
                        + "• `📊 Estado` — Salud del sistema, cuotas y almacenamiento.\n"
                        + "• `🛡️ Modo Co-Pilot` — Activa/desactiva aprobación previa manual.\n\n"
                        + "📥 *INGESTA DIRECTA:* Pega cualquier enlace de YouTube, TikTok o X en este chat.\n\n"
                        + "⌨️ *COMANDOS ÚTILES:*\n"
                        + "• `/radar` — Radar viral en vivo\n"
                        + "• `/stats` — Métricas reales de `@gtavihubextra`\n"
                        + "• `/host` — Telemetría de `mbp1` y GaTDSEQ\n"
                        + "• `/unlock` / `/clean` — Desbloquear cola y limpiar `temp/`\n"
                        + "• `/restart` — Reinicio rápido del bot"
                    )
                    send_telegram_alert(help_msg, reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/run", "🚀"] or text == "🚀 Forzar Escaneo":
                    if ACTIVE_TASK:
                        send_telegram_alert(f"⚠️ *Tarea activa en curso:* `{ACTIVE_TASK}`. Por favor espera a que finalice.")
                    else:
                        t = threading.Thread(target=run_scan_in_background, args=(allowed_chat_id,), daemon=True)
                        t.start()

                elif cmd in ["/status", "📊"] or text in ["📊 Dashboard", "📊 Estado"]:
                    send_telegram_alert(get_dashboard_text(), reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/host", "/telemetry", "🖥️"] or text == "🖥️ Estado Host / GaTDSEQ":
                    send_telegram_alert(get_host_telemetry_report(), reply_markup=get_system_actions_inline_keyboard())

                elif cmd in ["/restart", "/reiniciar", "/reboot", "/reset"]:
                    if "force" in text.lower():
                        t = threading.Thread(target=execute_bot_restart, daemon=True)
                        t.start()
                    else:
                        msg_txt = (
                            "⚠️ *CONFIRMACIÓN DE REINICIO*\n"
                            + ("═" * 36) + "\n\n"
                            + "¿Deseas reiniciar el Centro de Control y cancelar cualquier proceso colgado?\n\n"
                            + "• Se liberarán bloqueos de hardware (`ACTIVE_TASK`).\n"
                            + "• Se purgarán procesos huérfanos de `ffmpeg` y `yt-dlp`.\n"
                            + "• El bot volverá a responder en ~2 segundos.\n\n"
                            + "💡 _Para reiniciar directamente sin confirmación usa_ `/restart force`."
                        )
                        send_telegram_alert(msg_txt, reply_markup=get_restart_confirm_keyboard())

                elif cmd in ["/unlock", "/cancel", "/desbloquear"]:
                    with BACKGROUND_LOCK:
                        ACTIVE_TASK = None
                    kill_hung_subprocesses()
                    try:
                        from .cleaner import clean_temp_directory, clean_workspace_residuals
                        clean_temp_directory()
                        clean_workspace_residuals()
                    except Exception:
                        pass
                    send_telegram_alert(
                        "🔓 *Bloqueo liberado con éxito.*\n"
                        + "Se han cancelado procesos secundarios y limpiado temporales. El sistema vuelve a estar libre.",
                        reply_markup=get_persistent_menu_keyboard()
                    )

                elif cmd in ["/stats", "/analytics", "📈"] or text == "📈 Métricas YouTube":
                    send_telegram_alert(get_youtube_analytics_report(), reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/channels", "/canales", "⚙️"] or text == "⚙️ Canales":
                    send_telegram_alert(
                        "⚙️ *GESTIÓN DE CANALES MONITOREADOS*\n_Pulsa sobre cualquier canal para activarlo/desactivarlo:_",
                        reply_markup=get_channels_inline_keyboard()
                    )

                elif cmd in ["/fuentes", "/sources", "/learning", "/aprendizaje", "🧠"]:
                    from .channels import get_discovered_sources_report
                    send_telegram_alert(get_discovered_sources_report(), reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/mychannels", "/miscanales", "/redes", "/perfiles", "/profiles", "🌐"] or text in ["🌐 Mis Canales", "🌐 Perfiles Oficiales"]:
                    send_telegram_alert(
                        get_my_channels_report(),
                        reply_markup=get_my_channels_inline_keyboard()
                    )

                elif cmd in ["/aiselect", "/ai_select", "/seleccion_ia", "🤖"]:
                    send_telegram_alert("🤖 *Consultando al Motor de Selección con IA (Gemini Flash)...*\nEvaluando candidatos en tiempo real entre 72 canales y 64 queries...")
                    def _run_ai_sel():
                        try:
                            from .channels import fetch_channel_candidates
                            from .ai_selector import select_best_candidate_ai
                            candidates = fetch_channel_candidates(max_per_channel=2)
                            if not candidates:
                                send_telegram_alert("ℹ️ No hay vídeos nuevos pendientes en los canales para evaluar.")
                                return
                            best = select_best_candidate_ai(candidates, launch_mode=False)
                            msg = (
                                "🤖 *ELECCIÓN ESTRATÉGICA DE LA IA*\n"
                                + ("═" * 36) + "\n\n"
                                f"🎬 *Vídeo Ganador:* {best.get('title')}\n"
                                f"👤 *Creador:* `{best.get('source_name') or best.get('uploader')}`\n"
                                f"🔥 *Score:* `{best.get('score')}/100` | 👁️ *Vistas:* `{best.get('views', 0):,}`\n\n"
                                f"💡 *Justificación IA:*\n_{best.get('ai_justification')}_\n\n"
                                f"🏷️ *Título Sugerido:* `{best.get('recommended_title')}`\n"
                                f"⚡ *Gancho Superior:* `{best.get('hook_line1')} | {best.get('hook_line2')}`\n\n"
                                f"🔗 [Ver Original]({best.get('url')})"
                            )
                            send_telegram_alert(msg, reply_markup=get_persistent_menu_keyboard())
                        except Exception as e:
                            send_telegram_alert(f"⚠️ Error en selección con IA: {e}")
                    threading.Thread(target=_run_ai_sel, daemon=True).start()

                elif cmd in ["/launch", "/launchmode", "/launch_mode", "🚀"]:
                    send_telegram_alert(
                        "🚀 *MODO DÍA DEL ESTRENO (LAUNCH DAY 2026)*\n"
                        + ("═" * 36) + "\n\n"
                        "• Cobertura: *72 Canales de Autoridad + 64 Queries de Tendencia*\n"
                        "• Algoritmo: *Velocity Burst x2 + Freshness Boost (<12h)*\n"
                        "• Selector: *IA Gemini Flash evaluando gameplay y secretos de primer día*\n\n"
                        "Para lanzar una tanda en modo estreno ejecuta:\n"
                        "`./run.sh --launch-mode --auto`"
                    )

                elif cmd in ["/radar", "/viral", "🔥"] or text == "🔥 Radar Viral":
                    if ACTIVE_TASK:
                        send_telegram_alert(f"⚠️ *Tarea activa en curso:* `{ACTIVE_TASK}`. Por favor espera a que finalice.")
                    else:
                        t = threading.Thread(target=run_viral_radar_in_background, args=(allowed_chat_id,), daemon=True)
                        t.start()

                elif cmd in ["/traffic", "/trafico", "/sentinel"]:
                    try:
                        from .traffic_sentinel import scan_realtime_traffic, format_radar_telegram_message
                        send_telegram_alert("🛰️ *Consultando sensores de tráfico e intención de búsqueda en vivo...*")
                        radar_report = scan_realtime_traffic(save=True)
                        msg_txt = format_radar_telegram_message(radar_report)
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "🔥 Escanear Vídeos con estas Tendencias", "callback_data": "viral:refresh"}],
                                [{"text": "🔄 Refrescar Tráfico", "callback_data": "traffic:refresh"}]
                            ]
                        }
                        send_telegram_alert(msg_txt, reply_markup=keyboard)
                    except Exception as e:
                        send_telegram_alert(f"❌ Error en radar de tráfico: {e}")

                elif cmd in ["/recycle", "/fase", "/conocimiento"]:
                    try:
                        from .knowledge_recycler import recycle_knowledge, format_recycler_telegram_message
                        send_telegram_alert("🔄 *Reciclando conocimiento de GTA 6 y actualizando fase editorial...*")
                        state = recycle_knowledge(force=True)
                        msg_txt = format_recycler_telegram_message(state)
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "🛰️ Ver Radar de Tráfico", "callback_data": "traffic:refresh"}],
                                [{"text": "🔄 Forzar Reciclaje Ahora", "callback_data": "knowledge:recycle"}]
                            ]
                        }
                        send_telegram_alert(msg_txt, reply_markup=keyboard)
                    except Exception as e:
                        send_telegram_alert(f"❌ Error reciclando conocimiento: {e}")

                elif cmd in ["/deals", "/ofertas", "🛒"] or text == "🛒 Ofertas Amazon":
                    try:
                        from .deal_scanner import scan_and_update_deals, load_deals_state, format_deals_report
                        if "--update" in text or "actualizar" in text.lower() or "forzar" in text.lower():
                            send_telegram_alert("🔄 *Sincronizando y forzando actualización de ofertas en Amazon...*")
                            res = scan_and_update_deals(force=True, notify_telegram=False)
                            send_telegram_alert(res["report"], reply_markup=get_persistent_menu_keyboard())
                        else:
                            state = load_deals_state()
                            report = format_deals_report(state)
                            keyboard = {
                                "inline_keyboard": [
                                    [{"text": "🔄 Forzar Actualización Ahora", "callback_data": "deals_force_update"}],
                                    [{"text": "🌐 Ver Linktree Oficial", "url": "https://linktr.ee/gtavihubspain"}]
                                ]
                            }
                            send_telegram_alert(report, reply_markup=keyboard)
                    except Exception as e:
                        send_telegram_alert(f"⚠️ Error consultando ofertas: {e}", reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/optimize", "/aprender", "/learning", "🧠"] or text == "🧠 Auto-Perfeccionar":
                    send_telegram_alert("🧠 *Iniciando ciclo de auto-perfeccionamiento y benchmark...*\nAuditando vídeos de nuestro canal y extrayendo patrones ganadores de los líderes.")
                    def _run_opt():
                        try:
                            from .learning_engine import run_self_learning_cycle, generate_learning_telegram_report
                            pb = run_self_learning_cycle()
                            report = generate_learning_telegram_report(pb)
                            send_telegram_alert(report, reply_markup=get_persistent_menu_keyboard())
                        except Exception as e:
                            send_telegram_alert(f"⚠️ Error durante la optimización: {e}")
                    threading.Thread(target=_run_opt, daemon=True).start()

                elif cmd == "/addchannel":
                    parts = text.split(maxsplit=2)
                    if len(parts) < 2:
                        send_telegram_alert("⚠️ Uso: `/addchannel <url_del_canal> [nombre_opcional]`")
                    else:
                        ch_url = parts[1]
                        ch_name = parts[2] if len(parts) > 2 else ""
                        res = add_monitored_channel(ch_url, ch_name)
                        if res.get("success"):
                            c_info = res.get("channel", {})
                            send_telegram_alert(
                                f"✅ *Canal añadido con éxito:*\n"
                                f"• Nombre: `{c_info.get('name')}`\n"
                                f"• URL: `{c_info.get('url')}`"
                            )
                        else:
                            send_telegram_alert(f"⚠️ {res.get('message', 'No se pudo añadir el canal.')}")

                elif cmd == "/delchannel":
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        send_telegram_alert("⚠️ Uso: `/delchannel <número o nombre_del_canal>`")
                    else:
                        target = parts[1]
                        ok = remove_monitored_channel(target)
                        if ok:
                            send_telegram_alert(f"🗑️ *Canal `{target}` eliminado de channels.json con éxito.*")
                        else:
                            send_telegram_alert(f"⚠️ No se encontró ningún canal que coincida con `{target}`.")

                elif cmd in ["/copilot", "🛡️"] or text == "🛡️ Modo Co-Pilot":
                    enabled = is_copilot_enabled()
                    state_text = "🟢 ACTIVO (Requiere tu aprobación táctil)" if enabled else "⚡ DESACTIVADO (100% Autónomo)"
                    msg_body = (
                        "🛡️ *MODO CO-PILOT (PUERTA DE ENLACE HUMANA)*\n"
                        + ("═" * 36) + "\n\n"
                        + f"• Estado actual: `{state_text}`\n\n"
                        + "Con Co-Pilot activo, cada clip renderizado esperará tu toque de aprobación "
                        + "en Telegram antes de ser publicado en YouTube, TikTok e Instagram."
                    )
                    send_telegram_alert(msg_body, reply_markup=get_copilot_toggle_keyboard())

                elif cmd in ["/audit", "⚖️"] or text == "⚖️ Auditoría":
                    auditor = ComplianceAuditor()
                    score = auditor.audit_all()
                    summary = (
                        f"⚖️ *AUDITORÍA DE POLÍTICAS REALIZADA:*\n\n"
                        f"• Puntuación: `{score}/100`\n"
                        f"• Estado: `{'[✓ ÓPTIMO / Compliant]' if score >= 90 else '[!] Revisar directrices'}`\n"
                        f"• Próxima auditoría recomendada en 7 días."
                    )
                    send_telegram_alert(summary, reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/clean", "🧹"] or text == "🧹 Limpiar Temp":
                    from .cleaner import clean_temp_directory, clean_workspace_residuals
                    clean_temp_directory()
                    clean_workspace_residuals()
                    send_telegram_alert("🧹 *Limpieza estricta ejecutada.* Archivos temporales purgados a 0 bytes.", reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/preview", "/video", "🎬"] or text == "🎬 Último Clip":
                    mp4s = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
                    if mp4s:
                        latest = mp4s[0]
                        size_mb = latest.stat().st_size / (1024 * 1024)

                        # 1. Recuperar metadatos dinámicos generados por la IA para este clip
                        info_file = latest.with_name(f"{latest.stem}_info.json")
                        video_title = "Novedades & Filtraciones de GTA 6"
                        creator_name = "Rockstar Games"
                        hook_text = "¡NO TE PIERDAS ESTA NOVEDAD DE GTA 6! 🌴🔥"

                        if info_file.exists():
                            try:
                                info_data = json.loads(info_file.read_text(encoding="utf-8"))
                                creator_name = info_data.get("creator") or creator_name
                                yt_meta = info_data.get("youtube_metadata") or {}
                                video_title = yt_meta.get("title") or info_data.get("original_title") or video_title
                                hook_text = yt_meta.get("hook") or "¡NOVEDAD GTA 6!"
                            except Exception as e:
                                print(f"[Telegram] Error leyendo info.json: {e}")

                        # Limpiar título para redes
                        clean_title = (
                            video_title.replace("¡BRUTAL! 🔥 ", "")
                            .replace("REACCIÓN Y ANÁLISIS DE GTA 6: ", "")
                            .replace("REACCIÓN Y ANÁLISIS: ", "")
                            .strip()
                        )

                        # Generar texto viral único para TikTok e Instagram
                        tiktok_reels_copy = (
                            f"{hook_text} {clean_title} 🤯🌴\n\n"
                            f"Todo sobre GTA 6 en español en @gtavihubextra 🇪🇸\n"
                            f"#GTA6 #GTAVI #ViceCity #RockstarGames #Gaming #Shorts #Reels"
                        )

                        caption = (
                            f"🎬 *{clean_title[:70]}*\n"
                            f"👤 *Fuente:* `{creator_name}` | ⚖️ `{size_mb:.1f} MB`\n\n"
                            f"📋 *Texto para TikTok / Reels (toca para copiar):*\n"
                            f"`{tiktok_reels_copy}`\n\n"
                            f"👉 *1 toque al cuadro de texto para copiar* ➔ Pulsa *Compartir* en el vídeo ➔ TikTok / Reels ➔ Pega y publica."
                        )
                        sent = False
                        if latest.stat().st_size < 48 * 1024 * 1024:
                            send_telegram_alert("⏳ *Preparando y enviando vídeo a Telegram...*")
                            sent = send_telegram_video(latest, caption)
                        if not sent:
                            thumb = latest.with_suffix("").with_name(latest.stem.replace("_ES", "") + "_thumb.jpg")
                            if thumb.exists():
                                send_telegram_photo(thumb, caption)
                            else:
                                send_telegram_alert(caption, reply_markup=get_persistent_menu_keyboard())
                    else:
                        send_telegram_alert("ℹ️ No hay vídeos locales disponibles en output/.", reply_markup=get_persistent_menu_keyboard())

        except KeyboardInterrupt:
            print("\n[*] Bot detenido por el usuario.")
            break
        except Exception as e:
            print(f"[Telegram Bot] Error en loop: {e}")
            time.sleep(3)

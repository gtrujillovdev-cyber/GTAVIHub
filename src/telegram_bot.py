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

from .config import BASE_DIR, OUTPUT_DIR, TEMP_DIR, PROCESSED_FILE, is_quant_busy
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

# Regex para detección de URLs compatibles
URL_PATTERN = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be|tiktok\.com|vm\.tiktok\.com)/[^\s]+")

# ═══════════════════════════════════════════════════════════════════
# 1. HELPERS DE COMUNICACIÓN CON TELEGRAM BOT API
# ═══════════════════════════════════════════════════════════════════

def get_api_url(method: str) -> Optional[str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    if not token:
        return None
    return f"https://api.telegram.org/bot{token}/{method}"

def get_persistent_menu_keyboard() -> Dict[str, Any]:
    """Retorna el teclado táctil persistente principal para la barra inferior."""
    return {
        "keyboard": [
            [{"text": "🚀 Forzar Escaneo"}, {"text": "📊 Dashboard"}],
            [{"text": "🎬 Último Clip"}, {"text": "🖥️ Estado Host / GaTDSEQ"}],
            [{"text": "📈 Métricas YouTube"}, {"text": "⚙️ Canales"}],
            [{"text": "🔥 Radar Viral"}, {"text": "🛡️ Modo Co-Pilot"}],
            [{"text": "🧹 Limpiar Temp"}]
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

    try:
        res = requests.post(url, json=payload, timeout=12)
        return res.status_code == 200
    except Exception as e:
        print(f"[Telegram] Error enviando mensaje: {e}")
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
        return res.status_code == 200
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
            return res.status_code == 200
    except Exception as e:
        print(f"[Telegram] Error enviando foto: {e}")
        return False

def send_telegram_notification(
    title: str,
    creator: str,
    multiplatform_urls: Dict[str, Optional[str]],
    thumbnail_path: Optional[Path] = None
) -> bool:
    """Envía un anuncio de publicación exitosa con enlaces y miniatura."""
    yt_url = multiplatform_urls.get("youtube") or "Pendiente"
    tt_url = multiplatform_urls.get("tiktok") or "Pendiente"
    ig_url = multiplatform_urls.get("instagram") or "Pendiente"

    caption = (
        "🌴 *¡NUEVO VÍDEO PUBLICADO EN GTA VI HUB!* 🎮\n\n"
        f"🎬 *Título:* `{title}`\n"
        f"👤 *Autor Original:* `{creator}`\n\n"
        "🔗 *Enlaces a Plataformas:*\n"
        f"• 🔴 *YouTube Shorts:* [Ver en YouTube]({yt_url})\n"
        f"• 🎵 *TikTok:* [Ver en TikTok]({tt_url})\n"
        f"• 📸 *Instagram Reels:* [Ver en Instagram]({ig_url})\n\n"
        "⚖️ _Fair Use (Art. 107) verificado y créditos asignados._"
    )

    if thumbnail_path and thumbnail_path.exists():
        if send_telegram_photo(thumbnail_path, caption):
            return True

    return send_telegram_alert(caption, include_menu=True)

# ═══════════════════════════════════════════════════════════════════
# 2. KEYBOARDS INTERACTIVOS CONTEXTUALES
# ═══════════════════════════════════════════════════════════════════

def get_url_ingest_keyboard(token_id: str) -> Dict[str, Any]:
    """Teclado interactivo para seleccionar el formato de ingesta de un enlace."""
    return {
        "inline_keyboard": [
            [
                {"text": "⚡ Short Vertical Hormozi", "callback_data": f"url_opt:short:{token_id}"},
                {"text": "🎙️ Doblaje Neural + Subs", "callback_data": f"url_opt:dub:{token_id}"}
            ],
            [
                {"text": "💬 Solo Subtítulos (Orig)", "callback_data": f"url_opt:subs:{token_id}"},
                {"text": "❌ Cancelar", "callback_data": f"url_opt:cancel:{token_id}"}
            ]
        ]
    }

def get_copilot_approval_keyboard(video_id: str) -> Dict[str, Any]:
    """Teclado interactivo de aprobación/descarte en modo Co-Pilot."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Aprobar y Publicar", "callback_data": f"copilot:approve:{video_id}"},
                {"text": "❌ Descartar y Purgar", "callback_data": f"copilot:reject:{video_id}"}
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

def get_viral_radar_inline_keyboard(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Teclado interactivo para ingestar los clips más virales o registrar creadores nuevos."""
    buttons = []
    row = []
    for idx, c in enumerate(candidates[:4]):
        row.append({"text": f"⚡ Ingestar #{idx+1}", "callback_data": f"viral:ingest:{idx}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        {"text": "➕ Añadir Nuevos Creadores", "callback_data": "viral:add_channels"},
        {"text": "🔄 Actualizar Radar", "callback_data": "viral:refresh"}
    ])
    return {"inline_keyboard": buttons}

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
    hook_text: str = ""
) -> bool:
    """Envía la tarjeta de revisión Co-Pilot a Telegram con botones de acción."""
    caption = (
        "🛡️ *CO-PILOT: VÍDEO EN ESPERA DE APROBACIÓN*\n"
        + ("═" * 36) + "\n\n"
        + f"🎬 *Título Propuesto:* `{title}`\n"
        + f"👤 *Autor Original:* `{creator}`\n"
        + f"⏱️ *Formato:* `{'Short 9:16 (Vertical)' if is_short else 'Vídeo 16:9'}`\n"
        + f"🎙️ *Modo:* `{'Doblaje IA + Subs' if mode == 'dub' else 'Subtítulos Hormozi'}`\n"
        + f"🎯 *Gancho Inicial:* `{hook_text or 'EXCLUSIVA GTA 6'}`\n"
        + "⚖️ *Compliance:* `[✓ Fair Use y Atribución Listos]`\n\n"
        + "👇 *Pulsa una opción para proceder:*"
    )
    keyboard = get_copilot_approval_keyboard(video_id)

    if thumbnail_path and thumbnail_path.exists():
        if send_telegram_photo(thumbnail_path, caption, reply_markup=keyboard):
            return True

    return send_telegram_alert(caption, reply_markup=keyboard)

# ═══════════════════════════════════════════════════════════════════
# 4. REPORTES Y DASHBOARD
# ═══════════════════════════════════════════════════════════════════

def get_dashboard_text() -> str:
    """Genera un reporte conciso del estado del pipeline para Telegram."""
    from .monitor import get_directory_size_mb
    temp_mb = get_directory_size_mb(TEMP_DIR)
    output_mb = get_directory_size_mb(OUTPUT_DIR)

    token_yt = BASE_DIR / "token.json"
    tiktok_session = BASE_DIR / "assets" / ".browser_profiles" / "tiktok_user_data"
    copilot_status = "🟢 Activo (Requiere Aprobación)" if is_copilot_enabled() else "⚡ 100% Autónomo"

    msg = (
        "📊 *GTA VI HUB SPAIN — ESTADO DEL PIPELINE*\n"
        + ("═" * 36) + "\n\n"
        + "📁 *Almacenamiento Pipeline:*\n"
        + f"• Temp: `{temp_mb:.2f} MB` {'(✓ Limpio)' if temp_mb < 5 else '(!)'}\n"
        + f"• Output Staging: `{output_mb:.2f} MB`\n\n"
        + "🔐 *Sesiones y Redes:*\n"
        + f"• YouTube Data API: {'✅ Activo' if token_yt.exists() else '❌ Desconectado'}\n"
        + f"• TikTok / Instagram: {'✅ Perfil Configurado' if tiktok_session.exists() else 'ℹ️ Activo vía navegador'}\n"
        + f"• Modo Co-Pilot: `{copilot_status}`\n\n"
        + "⚖️ *Políticas Anti-Strike:* `[✓ Compliant]`\n"
        + f"📡 *Canales Activos:* `{len(list_monitored_channels())} monitoreados`\n"
    )
    return msg

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
        send_telegram_alert("⏳ *Iniciando escaneo de canales en segundo plano...*")
        candidates = fetch_channel_candidates(max_per_channel=max_videos)
        
        if not candidates:
            send_telegram_alert("✓ *Escaneo finalizado:* No hay vídeos nuevos pendientes.")
            return

        send_telegram_alert(f"🎯 *{len(candidates)} nuevo(s) vídeo(s) detectado(s).* Comenzando procesamiento...")
        count = 0
        for item in candidates[:max_videos]:
            send_telegram_alert(f"🎬 *Procesando ({count+1}/{min(len(candidates), max_videos)}):* `{item['title'][:55]}`...")
            res = process_single_video(
                url=item["url"],
                video_id=item["id"],
                original_title=item["title"],
                creator_name=item.get("source_name", "Rockstar"),
                source_lang=item.get("lang", "en"),
                mode="subs",
                force_short=True if item.get("is_short") else None,
                auto_upload=True,
                publish_all=True
            )
            if res:
                count += 1
                
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
    format_choice: str
):
    """Ejecuta el procesamiento de un enlace bajo demanda en segundo plano."""
    global ACTIVE_TASK
    with BACKGROUND_LOCK:
        ACTIVE_TASK = f"Ingesta: {title[:25]}"

    try:
        from .pipeline import process_single_video
        is_short = True if format_choice == "short" or "/shorts/" in url.lower() else (False if format_choice == "normal" else None)
        mode = "dub" if format_choice == "dub" else "subs"

        send_telegram_alert(f"⏳ *Renderizando vídeo:* `{title[:50]}` en formato `{format_choice.upper()}`...")

        res = process_single_video(
            url=url,
            video_id=vid_id,
            original_title=title,
            creator_name=uploader,
            mode=mode,
            force_short=is_short,
            auto_upload=True,
            publish_all=True
        )
        if res and res.get("status") != "staged_for_copilot":
            send_telegram_alert(f"✓ *Vídeo procesado y subido:* `{title[:50]}`")
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
        if res and res.get("youtube_url"):
            send_telegram_alert(
                f"🚀 *¡Vídeo Aprobado y Publicado con Éxito!*\n\n"
                f"🎬 *Título:* `{res.get('title')}`\n"
                f"🔗 *YouTube Shorts:* {res.get('youtube_url')}\n\n"
                f"🧹 _Archivos pesados purgados del disco._"
            )
        else:
            send_telegram_alert("⚠️ *Vídeo procesado, pero revisa las credenciales de publicación.*")
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
    """Detecta un enlace pegado por el usuario, extrae metadatos y muestra botones."""
    send_telegram_alert(f"🔍 *Analizando enlace de vídeo...*\n`{url}`")
    
    # Extracción rápida con yt-dlp
    try:
        res = subprocess.run([
            sys.executable, "-m", "yt_dlp",
            "--impersonate", "chrome",
            "--no-check-certificates",
            "--print", "%(id)s\t%(title)s\t%(duration)s\t%(uploader)s",
            url
        ], capture_output=True, text=True, timeout=20)
        
        parts = res.stdout.strip().split("\t")
        vid_id = parts[0] if len(parts) > 0 and parts[0] else "custom_vid"
        title = parts[1] if len(parts) > 1 and parts[1] else "Vídeo GTA 6"
        dur_raw = parts[2] if len(parts) > 2 else "0"
        uploader = parts[3] if len(parts) > 3 and parts[3] else "Desconocido"
        try:
            dur_sec = int(float(dur_raw))
            dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d} min"
        except Exception:
            dur_str = "Desconocida"
    except Exception as e:
        vid_id = f"vid_{int(time.time())}"
        title = "Clip Enlace Externo"
        uploader = "Desconocido"
        dur_str = "Auto"

    token_id = uuid.uuid4().hex[:8]
    CACHED_INGEST_URLS[token_id] = {
        "url": url,
        "vid_id": vid_id,
        "title": title,
        "uploader": uploader
    }

    caption = (
        "📥 *ENLACE DETECTADO PARA INGESTA*\n"
        + ("═" * 36) + "\n\n"
        + f"🎬 *Título:* `{title[:65]}`\n"
        + f"👤 *Canal:* `{uploader}`\n"
        + f"⏱️ *Duración:* `{dur_str}`\n\n"
        + "🎯 *Selecciona el formato de procesamiento deseado:*"
    )
    keyboard = get_url_ingest_keyboard(token_id)
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

        answer_callback_query(cq_id, f"Iniciando formato {opt.upper()}...")
        edit_telegram_message(
            msg_id,
            f"⏳ *Procesando `{item['title'][:40]}...` en segundo plano.* Te notificaremos con el resultado."
        )

        t = threading.Thread(
            target=run_ingest_in_background,
            args=(item["url"], item["vid_id"], item["title"], item["uploader"], opt),
            daemon=True
        )
        t.start()
        return

    # B) Aprobación / Rechazo Co-Pilot
    if data.startswith("copilot:approve:"):
        video_id = data.split(":", 2)[2]
        answer_callback_query(cq_id, "Aprobando y publicando...")
        edit_telegram_message(msg_id, f"🚀 *Vídeo `{video_id}` aprobado.* Publicando en segundo plano...")
        t = threading.Thread(target=run_approval_publish_in_background, args=(video_id,), daemon=True)
        t.start()
        return

    if data.startswith("copilot:reject:"):
        video_id = data.split(":", 2)[2]
        answer_callback_query(cq_id, "Descartando vídeo...")
        success = reject_and_purge_video(video_id)
        if success:
            edit_telegram_message(msg_id, f"🗑️ *Vídeo `{video_id}` descartado y purgado del disco con éxito.*")
        else:
            edit_telegram_message(msg_id, f"ℹ️ *El vídeo `{video_id}` ya había sido descartado.*")
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
            "• `/channels` — Abre este panel interactivo."
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
            params = {"offset": last_update_id + 1, "timeout": 20}
            res = requests.get(url_updates, params=params, timeout=25)
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
                        "🎮 *CENTRO DE MANDO MÓVIL — GTA VI HUB SPAIN*\n"
                        + ("═" * 36) + "\n\n"
                        + "📱 *BOTONES DE CONTROL EN PANTALLA:*\n"
                        + "• `🚀 Forzar Escaneo` — Rastrea los 22 canales configurados y publica nuevos clips.\n"
                        + "• `🔥 Radar Viral` — Rastrear clips de GTA 6 con mayor engagement y creadores emergentes.\n"
                        + "• `🛡️ Modo Co-Pilot` — Activa/desactiva la puerta de enlace humana (1-clic para aprobar o purgar).\n"
                        + "• `📊 Dashboard` — Estado de cuotas orgánicas, almacenamiento y sesiones de redes.\n"
                        + "• `🖥️ Estado Host / GaTDSEQ` — CPU load, RAM real en Mac, SSD, batería y convivencia quant.\n"
                        + "• `📈 Métricas YouTube` — Suscriptores, visualizaciones y analíticas en tiempo real vía API v3.\n"
                        + "• `⚙️ Canales` — Conmutador interactivo para activar/pausar las 22 fuentes con 1 toque.\n"
                        + "• `🎬 Último Clip` — Envía la miniatura renderizada y los metadatos del clip más reciente.\n"
                        + "• `🧹 Limpiar Temp` — Purga estricta de archivos de trabajo volátiles a 0 bytes.\n\n"
                        + "📥 *INGESTA BAJO DEMANDA DE ENLACES:*\n"
                        + "Pega cualquier enlace de YouTube o TikTok en este chat. El bot detectará el vídeo y desplegará botones para elegir el formato:\n"
                        + "  • `⚡ Short Vertical Hormozi`: Reencuadre 9:16 + subtítulos Pop Bounce.\n"
                        + "  • `🎙️ Doblaje Neural`: Traducción de audio al español neutro + subtítulos.\n"
                        + "  • `💬 Solo Subtítulos`: Audio original + subtítulos quemados en pantalla.\n\n"
                        + "⌨️ *COMANDOS ADICIONALES:*\n"
                        + "• `/addchannel <url> [nombre]` — Añade un canal al monitoreo continuo.\n"
                        + "• `/delchannel <número o nombre>` — Da de baja una fuente.\n"
                        + "• `/radar` o `/viral` — Ejecuta el Radar Viral de engagement.\n"
                        + "• `/copilot` — Configura la aprobación táctil de publicaciones.\n"
                        + "• `/audit` — Auditoría de directrices anti-strike y Fair Use.\n"
                        + "• `/clean` — Limpieza inmediata de disco en el host.\n"
                        + "• `/guia` — Vuelve a mostrar este manual completo."
                    )
                    send_telegram_alert(help_msg, reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/run", "🚀"] or text == "🚀 Forzar Escaneo":
                    if ACTIVE_TASK:
                        send_telegram_alert(f"⚠️ *Tarea activa en curso:* `{ACTIVE_TASK}`. Por favor espera a que finalice.")
                    else:
                        t = threading.Thread(target=run_scan_in_background, args=(allowed_chat_id,), daemon=True)
                        t.start()

                elif cmd in ["/status", "📊"] or text == "📊 Dashboard":
                    send_telegram_alert(get_dashboard_text(), reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/host", "/telemetry", "🖥️"] or text == "🖥️ Estado Host / GaTDSEQ":
                    send_telegram_alert(get_host_telemetry_report(), reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/stats", "/analytics", "📈"] or text == "📈 Métricas YouTube":
                    send_telegram_alert(get_youtube_analytics_report(), reply_markup=get_persistent_menu_keyboard())

                elif cmd in ["/channels", "⚙️"] or text == "⚙️ Canales":
                    send_telegram_alert(
                        "⚙️ *GESTIÓN DE CANALES MONITOREADOS*\n_Pulsa sobre cualquier canal para activarlo/desactivarlo:_",
                        reply_markup=get_channels_inline_keyboard()
                    )

                elif cmd in ["/radar", "/viral", "🔥"] or text == "🔥 Radar Viral":
                    if ACTIVE_TASK:
                        send_telegram_alert(f"⚠️ *Tarea activa en curso:* `{ACTIVE_TASK}`. Por favor espera a que finalice.")
                    else:
                        t = threading.Thread(target=run_viral_radar_in_background, args=(allowed_chat_id,), daemon=True)
                        t.start()

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

                elif cmd in ["/preview", "🎬"] or text == "🎬 Último Clip":
                    mp4s = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
                    if mp4s:
                        latest = mp4s[0]
                        thumb = latest.with_suffix("").with_name(latest.stem.replace("_ES", "") + "_thumb.jpg")
                        caption = f"🎬 *Último clip disponible:* `{latest.name}`"
                        if thumb.exists():
                            send_telegram_photo(thumb, caption)
                        else:
                            send_telegram_alert(caption, reply_markup=get_persistent_menu_keyboard())
                    else:
                        send_telegram_alert("ℹ️ No hay vídeos locales pendientes en output/.", reply_markup=get_persistent_menu_keyboard())

        except KeyboardInterrupt:
            print("\n[*] Bot detenido por el usuario.")
            break
        except Exception as e:
            print(f"[Telegram Bot] Error en loop: {e}")
            time.sleep(3)

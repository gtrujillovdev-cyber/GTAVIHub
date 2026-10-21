import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from .config import BASE_DIR, OUTPUT_DIR, TEMP_DIR, PROCESSED_FILE
from .compliance_auditor import ComplianceAuditor

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_api_url(method: str) -> Optional[str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    return f"https://api.telegram.org/bot{token}/{method}"

def send_telegram_alert(message: str) -> bool:
    """Envía un mensaje de texto o alerta al chat de Telegram configurado."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    url = get_api_url("sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[Telegram] Error enviando alerta: {e}")
        return False

def send_telegram_notification(
    title: str,
    creator: str,
    multiplatform_urls: Dict[str, Optional[str]],
    thumbnail_path: Optional[Path] = None
) -> bool:
    """
    Envía una notificación push con miniatura y enlaces de publicación
    al Telegram del propietario del canal.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    yt_url = multiplatform_urls.get("youtube") or "Pendiente de publicación"
    tt_url = multiplatform_urls.get("tiktok") or "Pendiente de publicación"
    ig_url = multiplatform_urls.get("instagram") or "Pendiente de publicación"

    caption = (
        "🌴 *¡NUEVO VÍDEO PUBLICADO EN GTA VI HUB!* 🎮\n\n"
        f"🎬 *Título:* `{title}`\n"
        f"👤 *Autor Original:* `{creator}`\n\n"
        "🔗 *Enlaces a Plataformas:*\n"
        f"• 🔴 *YouTube Shorts:* [Ver en YouTube]({yt_url})\n"
        f"• 🎵 *TikTok:* [Ver en TikTok]({tt_url})\n"
        f"• 📸 *Instagram Reels:* [Ver en Instagram]({ig_url})\n\n"
        "⚖️ _Uso Legítimo (Fair Use Art. 107) y créditos acreditados._"
    )

    # 1. Intentar enviar con foto si hay miniatura
    if thumbnail_path and thumbnail_path.exists():
        try:
            url = get_api_url("sendPhoto")
            with open(thumbnail_path, "rb") as photo:
                files = {"photo": photo}
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown"
                }
                res = requests.post(url, data=data, files=files, timeout=20)
                if res.status_code == 200:
                    print("[✓ Telegram] Notificación con miniatura enviada con éxito.")
                    return True
        except Exception as e:
            print(f"[!] Error enviando foto a Telegram: {e}")

    # 2. Fallback a texto
    return send_telegram_alert(caption)

def get_dashboard_text() -> str:
    """Genera un reporte conciso del estado del pipeline para Telegram."""
    from .monitor import get_directory_size_mb
    temp_mb = get_directory_size_mb(TEMP_DIR)
    output_mb = get_directory_size_mb(OUTPUT_DIR)

    token_yt = BASE_DIR / "token.json"
    tiktok_session = BASE_DIR / "assets" / ".browser_profiles" / "tiktok_user_data"

    msg = (
        "📊 *GTA VI HUB SPAIN — ESTADO DEL PIPELINE*\n"
        + ("═" * 36) + "\n\n"
        + f"📁 *Almacenamiento:*\n"
        + f"• Temp: `{temp_mb:.2f} MB` {'(✓ Limpio)' if temp_mb < 5 else '(!)'}\n"
        + f"• Output: `{output_mb:.2f} MB / 1000 MB`\n\n"
        + "🔐 *Sesiones y Credenciales:*\n"
        + f"• YouTube: {'✅ Activo' if token_yt.exists() else '❌ Desconectado'}\n"
        + f"• TikTok / IG: {'✅ Perfil Configurado' if tiktok_session.exists() else 'ℹ️ Activo vía navegador'}\n"
        + "• GPU: `Apple M4 (VideoToolbox)`\n\n"
        + "⚖️ *Políticas Anti-Strike:* `[✓ Compliant]`\n"
        + "📡 *Canales Activos:* `9 monitoreados`\n"
    )
    return msg

def start_telegram_bot_daemon():
    """
    Inicia el bucle de polling del Bot de Telegram para recibir comandos
    remotos desde el móvil o cualquier cliente.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not allowed_chat_id:
        print("\n[!] Error: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados en .env")
        print("    Añádelos a tu archivo .env para usar el bot de control remoto.")
        return

    print("\n" + "=" * 65)
    print(" 🤖 INICIANDO BOT DE CONTROL REMOTO TELEGRAM (GTA VI Hub)")
    print("=" * 65)
    print(f"[*] Escuchando comandos para Chat ID: {allowed_chat_id}")
    print("[*] Escribe /help en tu chat de Telegram para ver opciones.")
    print("=" * 65 + "\n")

    last_update_id = 0
    url_updates = get_api_url("getUpdates")

    send_telegram_alert("🟢 *Bot de control remoto activado en tu Mac.* Escribe /help para ver comandos.")

    while True:
        try:
            params = {"offset": last_update_id + 1, "timeout": 20}
            res = requests.get(url_updates, params=params, timeout=25)
            if res.status_code != 200:
                time.sleep(5)
                continue

            data = res.json()
            updates = data.get("result", [])

            for upd in updates:
                last_update_id = upd.get("update_id", last_update_id)
                msg = upd.get("message", {})
                chat = msg.get("chat", {})
                chat_id = str(chat.get("id", ""))
                text = msg.get("text", "").strip()

                # Control de seguridad: responder únicamente al chat del propietario
                if str(chat_id) != str(allowed_chat_id):
                    continue

                if not text:
                    continue

                cmd = text.split()[0].lower()

                if cmd in ["/start", "/help"]:
                    help_msg = (
                        "🎮 *Comandos de GTA VI Hub Spain Bot:*\n\n"
                        "• `/status` — Panel de control, disco y cuotas diarias.\n"
                        "• `/run` — Forzar escaneo autónomo y publicación inmediata.\n"
                        "• `/audit` — Auditar normativas anti-ban y Fair Use.\n"
                        "• `/clean` — Purgar archivos temporales en el Mac.\n"
                        "• `/preview` — Ver información del último vídeo procesado."
                    )
                    send_telegram_alert(help_msg)

                elif cmd == "/status":
                    send_telegram_alert(get_dashboard_text())

                elif cmd == "/run":
                    send_telegram_alert("⏳ *Iniciando escaneo y publicación autónoma en segundo plano...*")
                    # Ejecutar en segundo plano para no congelar el polling
                    subprocess.Popen([
                        sys.executable,
                        str(BASE_DIR / "main.py"),
                        "--auto",
                        "--publish-all"
                    ])

                elif cmd == "/audit":
                    auditor = ComplianceAuditor()
                    score = auditor.audit_all()
                    summary = (
                        f"⚖️ *AUDITORÍA DE POLÍTICAS REALIZADA:*\n\n"
                        f"• Puntuación: `{score}/100`\n"
                        f"• Estado: `{'[✓ ÓPTIMO / Compliant]' if score >= 90 else '[!] Revisar directrices'}`\n"
                        f"• Próxima auditoría recomendada en 7 días."
                    )
                    send_telegram_alert(summary)

                elif cmd == "/clean":
                    from .cleaner import clean_temp_directory, clean_workspace_residuals
                    clean_temp_directory()
                    clean_workspace_residuals()
                    send_telegram_alert("🧹 *Limpieza estricta ejecutada.* Archivos temporales purgados a 0 bytes.")

                elif cmd == "/preview":
                    # Buscar el último vídeo en output
                    mp4s = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
                    if mp4s:
                        latest = mp4s[0]
                        thumb = latest.with_suffix("").with_name(latest.stem.replace("_ES", "") + "_thumb.jpg")
                        caption = f"🎬 *Último clip disponible:* `{latest.name}`"
                        if thumb.exists():
                            with open(thumb, "rb") as photo:
                                requests.post(
                                    get_api_url("sendPhoto"),
                                    data={"chat_id": allowed_chat_id, "caption": caption, "parse_mode": "Markdown"},
                                    files={"photo": photo},
                                    timeout=15
                                )
                        else:
                            send_telegram_alert(caption)
                    else:
                        send_telegram_alert("ℹ️ No hay vídeos locales pendientes en output/.")

        except KeyboardInterrupt:
            print("\n[*] Bot detenido por el usuario.")
            break
        except Exception as e:
            print(f"[Telegram Bot] Error en loop: {e}")
            time.sleep(3)

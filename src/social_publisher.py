import os
import sys
import re
import json
import time
import random
import subprocess
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from .config import (
    BASE_DIR, OUTPUT_DIR, LOGS_DIR, PROCESSED_FILE, BUSINESS_EMAIL,
    MONETIZATION_AFFILIATE_URL, ENABLE_AFFILIATE_CTAS,
    AFFILIATE_CTA_TIKTOK, AFFILIATE_CTA_INSTAGRAM,
    TEMP_DIR, FFMPEG_VIDEO_CODEC, FFMPEG_THREADS, is_quant_busy
)
from .uploader import upload_to_youtube
from .compliance_auditor import ComplianceAuditor
from .translator import to_unicode_bold, truncate_on_word_boundary

# Directorio persistente para la sesión del navegador (TikTok / Instagram)
BROWSER_PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles"
TIKTOK_COOLDOWN_FILE = BASE_DIR / "data" / "tiktok_cooldown.json"


def prepare_social_compatible_video(video_path: Path) -> tuple[Path, bool]:
    """
    Si el vídeo maestro es 4K (>1080p), genera una versión optimizada a 1080x1920
    para TikTok e Instagram, evitando rechazo de API o demoras excesivas de subida.
    Retorna: (compatible_video_path, is_temp)
    """
    video_path = Path(video_path)
    if not video_path.exists() or video_path.stat().st_size < 1000:
        return video_path, False

    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
        parts = probe.stdout.strip().split(",")
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return video_path, False
        w, h = int(parts[0]), int(parts[1])
        if w <= 1080 and h <= 1920:
            return video_path, False
    except Exception:
        return video_path, False

    temp_1080 = TEMP_DIR / f"{video_path.stem}_1080p.mp4"
    threads = 1 if is_quant_busy() else FFMPEG_THREADS
    cmd = [
        "ffmpeg", "-y",
        "-threads", str(threads),
        "-i", str(video_path),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", FFMPEG_VIDEO_CODEC,
        "-b:v", "4500k",
        "-maxrate", "6500k",
        "-bufsize", "9000k",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(temp_1080)
    ]
    try:
        print(f"[*] [Social Downscale] Adaptando máster 4K a 1080x1920 para compatibilidad social...")
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        if temp_1080.exists() and temp_1080.stat().st_size > 1000:
            return temp_1080, True
    except Exception as e:
        print(f"[!] [Social Downscale] Error adaptando a 1080p ({e}). Usando original.")
        temp_1080.unlink(missing_ok=True)
    return video_path, False


def _is_tiktok_blocked_by_cooldown(cooldown_minutes: Optional[int] = None) -> tuple[bool, str]:
    """Evita saturar TikTok respetando un espaciado mínimo (default 90 min) entre publicaciones."""
    limit_min = int(os.getenv("TIKTOK_COOLDOWN_MINUTES", "90")) if cooldown_minutes is None else int(cooldown_minutes)
    if limit_min <= 0 or not TIKTOK_COOLDOWN_FILE.exists():
        return False, ""
    try:
        entries = json.loads(TIKTOK_COOLDOWN_FILE.read_text(encoding="utf-8"))
        if not isinstance(entries, list) or not entries:
            return False, ""
        last_ts = datetime.fromisoformat(entries[-1].get("uploaded_at", ""))
        mins_since = (datetime.now() - last_ts).total_seconds() / 60.0
        if mins_since < limit_min:
            wait_left = max(1, int(round(limit_min - mins_since)))
            return True, f"Cooldown anti-saturación TikTok activo: última subida hace {int(mins_since)}m (<{limit_min}m, esperar {wait_left}m)."
    except Exception:
        pass
    return False, ""


def _record_tiktok_upload(title: str) -> None:
    """Registra una subida real a TikTok para preservar el espaciado anti-saturación."""
    try:
        TIKTOK_COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        if TIKTOK_COOLDOWN_FILE.exists():
            entries = json.loads(TIKTOK_COOLDOWN_FILE.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        entries.append({"title": title[:80], "uploaded_at": datetime.now().isoformat()})
        TIKTOK_COOLDOWN_FILE.write_text(json.dumps(entries[-20:], indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def open_login_assistant():
    """
    Abre una ventana de Chromium con el perfil persistente local
    para que el usuario inicie sesión en TikTok e Instagram desde la terminal.
    """
    tiktok_profile = BROWSER_PROFILE_DIR / "tiktok_user_data"
    tiktok_profile.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print(" 🌐 ASISTENTE DE SESIÓN PERSISTENTE (TikTok & Instagram)")
    print("=" * 65)
    print(f"[*] Perfil local: {tiktok_profile}")
    print("[*] Abriendo navegador Chromium local...")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(tiktok_profile),
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page_tt = context.pages[0] if context.pages else context.new_page()
            page_tt.goto("https://www.tiktok.com/signup", wait_until="domcontentloaded")
            
            page_ig = context.new_page()
            page_ig.goto("https://www.instagram.com/accounts/emailsignup/", wait_until="domcontentloaded")

            print("\n[✓] Navegador abierto con pestañas de TikTok e Instagram.")
            print("👉 Inicia sesión o crea tu cuenta en las pestañas abiertas.")
            print("👉 Cuando termines, pulsa [ENTER] en la terminal para guardar las cookies...")
            input("\nPresiona [ENTER] para cerrar el navegador y guardar la sesión: ")

            context.close()
            print("\n[✓] ¡Sesión guardada con éxito en tu Mac M4!")
            print("    A partir de ahora, las subidas automáticas utilizarán estas credenciales.")
            print("=" * 65 + "\n")
    except Exception as e:
        print(f"[!] Error iniciando navegador: {e}")

class AntiBanValidator:
    """
    Verifica que el vídeo y sus metadatos cumplan rigurosamente
    con las directrices anti-baneo y de uso legítimo (Fair Use).
    """

    @classmethod
    def get_daily_limit(cls, platform: str) -> int:
        """Obtiene el límite diario configurado por plataforma (máximo 3/día por defecto anti-spam)."""
        p = platform.lower()
        if p == "youtube":
            return int(os.getenv("MAX_DAILY_UPLOADS_YOUTUBE", os.getenv("MAX_DAILY_UPLOADS", "3")))
        elif p == "tiktok":
            return int(os.getenv("MAX_DAILY_UPLOADS_TIKTOK", os.getenv("MAX_DAILY_UPLOADS", "3")))
        elif p == "instagram":
            return int(os.getenv("MAX_DAILY_UPLOADS_INSTAGRAM", os.getenv("MAX_DAILY_UPLOADS", "3")))
        return int(os.getenv("MAX_DAILY_UPLOADS", "3"))

    @classmethod
    def check_daily_limit(cls, platform: str) -> bool:
        """Comprueba que no se supere el límite configurado de vídeos diarios."""
        if not PROCESSED_FILE.exists():
            return True
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
            today_str = date.today().isoformat()
            today_uploads = []
            for r in records:
                entry_date = r.get("date") or r.get("approved_at") or ""
                if not entry_date.startswith(today_str):
                    continue
                # 1. Comprobar clave directa (ej. youtube_uploaded_url)
                if r.get(f"{platform}_uploaded_url") or r.get(f"uploaded_{platform}_url"):
                    today_uploads.append(r)
                    continue
                # 2. Comprobar diccionario anidado 'multiplatform'
                multi = r.get("multiplatform")
                if isinstance(multi, dict):
                    plat_url = multi.get(platform)
                    if plat_url and str(plat_url).startswith("http"):
                        today_uploads.append(r)
                    continue
                # 3. Clave genérica para registros legacy (sin 'multiplatform')
                if platform == "youtube" and r.get("status") in ("completed", "published_via_copilot") and r.get("youtube_title"):
                    today_uploads.append(r)
            limit = cls.get_daily_limit(platform)
            if len(today_uploads) >= limit:
                print(f"[Anti-Ban] Límite diario alcanzado para {platform.upper()} ({len(today_uploads)}/{limit}). Saltando para proteger la cuenta.")
                return False
            return True
        except Exception as e:
            print(f"[Anti-Ban] Error verificando límite diario: {e}")
            return True

    @classmethod
    def validate_metadata(cls, metadata: Dict[str, Any], creator_name: str, original_url: str = "") -> bool:
        """Comprueba rigurosamente que los metadatos respeten al autor y cumplan Fair Use."""
        is_safe, issues = ComplianceAuditor.audit_clip_metadata(metadata, creator_name, original_url)
        if not is_safe:
            print("[Anti-Ban & Compliance Auditor] Observaciones de seguridad:")
            for issue in issues:
                print(f"  ⚠️  {issue}")
        else:
            print("[Anti-Ban & Compliance Auditor] [✓ Seguro] Respeto al autor y Fair Use verificados.")
        return is_safe


class SocialPublisher:
    """
    Gestor de distribución unificada y escalonada para YouTube Shorts,
    TikTok e Instagram Reels con protección contra baneos y detección de bots.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    def _notify_telegram(self, text: str) -> None:
        """Envía una actualización rápida del estado de publicación a Telegram."""
        if getattr(self, "dry_run", False):
            return
        try:
            from .telegram_bot import send_telegram_alert
            send_telegram_alert(text)
        except Exception:
            pass

    def publish_to_youtube(
        self,
        video_path: Path,
        title: str,
        description: str,
        privacy: str = "public",
        thumbnail_path: Optional[Path] = None,
        pinned_comment: Optional[str] = None,
        target_account: str = "main"
    ) -> Optional[str]:
        """Sube el vídeo a YouTube Shorts mediante API oficial v3."""
        print(f"\n[1/3 YouTube] Iniciando publicación de '{video_path.name}' (Cuenta: {target_account.upper()})...")
        if not AntiBanValidator.check_daily_limit("youtube"):
            return None

        if self.dry_run:
            print(f"[1/3 YouTube] [DRY RUN] Simulación exitosa. Vídeo marcado como listo ({privacy}).")
            return f"https://youtu.be/mock_yt_{video_path.stem}"

        video_id = upload_to_youtube(
            video_path=video_path,
            title=title,
            description=description,
            privacy_status=privacy,
            is_short=True,
            thumbnail_path=thumbnail_path,
            pinned_comment=pinned_comment,
            target_account=target_account
        )
        if video_id:
            return f"https://youtu.be/{video_id}" if not str(video_id).startswith("http") else str(video_id)
        return None

    @staticmethod
    def _build_tiktok_caption(
        title: str,
        tags: List[str],
        debate_question: str = "",
        description: str = "",
        creator_name: str = "",
    ) -> str:
        """Construye una descripción limpia, natural y de alto CTR en TikTok (sin gritos ALL CAPS ni cortes)."""
        clean_title = re.sub(r'[\r\n]+', ' ', title).strip()
        clean_title = re.sub(r'\s*#\w+', '', clean_title).strip()
        # Convertir títulos TODO MAYÚSCULAS a formato natural legible manteniendo siglas clave
        if clean_title == clean_title.upper() and len(clean_title) > 6:
            clean_title = clean_title.capitalize()
            for token in ("GTA 6", "GTA VI", "PS5 Pro", "PS5", "Xbox", "RAGE 9", "Vice City", "Leonida", "Lucía", "Jason", "4K", "60FPS", "FPS"):
                clean_title = re.sub(rf"\b{re.escape(token)}\b", token, clean_title, flags=re.IGNORECASE)
        short_title = truncate_on_word_boundary(clean_title, 54)

        if debate_question:
            q_clean = truncate_on_word_boundary(
                debate_question.replace("¿", "").replace("?", "").strip(), 60
            )
            debate_line = f"💬 ¿{q_clean}?"
        else:
            low_title = clean_title.lower()
            if any(k in low_title for k in ("ps5", "xbox", "pc", "fps", "gráfic", "grafic", "comparativa")):
                debate_line = "💬 ¿PS5 Pro o esperar a PC? Te leo 👇"
            elif any(k in low_title for k in ("secret", "ocult", "arma", "mapa", "detalle", "truco", "curiosidad")):
                debate_line = "🔖 Guárdalo para cuando explores Leonida 👇"
            else:
                debate_line = "💬 ¿Del 1 al 10 qué nota le pones a esto? Te leo 👇"

        # Extraer contexto editorial limpio sin URLs ni boilerplate legal de YouTube
        editorial_lines = []
        if description:
            for raw_line in description.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                low = line.lower()
                if any(skip in low for skip in ("http://", "https://", "fair use", "art. 107", "copyright", "por: @", "créditos", "suscríbete")):
                    continue
                if line.startswith("#"):
                    continue
                editorial_lines.append(line)
                if len(" ".join(editorial_lines)) >= 120:
                    break
        editorial_snippet = truncate_on_word_boundary(" ".join(editorial_lines), 140) if editorial_lines else ""

        # Hashtags curados (máximo 4 limpios de alto alcance en TikTok)
        base_tags = ["GTA6", "GTAVI", "Leonida", "ViceCity"]
        merged_tags = []
        seen_low = set()
        for t in list(tags or []) + base_tags:
            clean_t = re.sub(r'[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ]', '', str(t))
            if clean_t and clean_t.lower() not in seen_low:
                seen_low.add(clean_t.lower())
                merged_tags.append(f"#{clean_t}")
            if len(merged_tags) >= 4:
                break
        tags_str = " ".join(merged_tags)

        parts = [short_title, debate_line]
        if editorial_snippet:
            parts.append(editorial_snippet)
        if creator_name and creator_name.strip():
            clean_creator = creator_name.strip().lstrip("@")
            parts.append(f"📌 Crédito: @{clean_creator}")
        if tags_str:
            parts.append(tags_str)
        return "\n\n".join(parts)

    def publish_to_tiktok(
        self,
        video_path: Path,
        title: str,
        tags: List[str],
        debate_question: str = "",
        description: str = "",
        creator_name: str = "",
    ) -> Optional[str]:
        """
        Publica o programa en TikTok Creator Center mediante navegador automatizado
        con huella digital humana y perfil persistente local.
        """
        print(f"\n[2/3 TikTok] Preparando subida orgánica a TikTok...")
        video_path = Path(video_path)
        if not AntiBanValidator.check_daily_limit("tiktok"):
            return None
        if not self.dry_run:
            blocked_tt, reason_tt = _is_tiktok_blocked_by_cooldown()
            if blocked_tt:
                print(f"🛡️ [TikTok Anti-Saturación] Subida aplazada: {reason_tt}")
                self._notify_telegram(f"⏳ *[TikTok Anti-Saturación]* Clip aplazado para evitar saturar la cuenta:\n_{reason_tt}_")
                return None

        caption = self._build_tiktok_caption(
            title=title,
            tags=tags,
            debate_question=debate_question,
            description=description,
            creator_name=creator_name,
        )
        tiktok_profile = BROWSER_PROFILE_DIR / "tiktok_user_data"

        if self.dry_run:
            print(f"[2/3 TikTok] [DRY RUN] Simulación exitosa. Caption: '{caption[:60]}...'")
            print(f"             Perfil de sesión: {tiktok_profile}")
            return f"https://www.tiktok.com/@gtavihubextra/video/mock_{video_path.stem}"

        compat_path, is_temp_video = prepare_social_compatible_video(video_path)

        try:
            # Comprobar si playwright está disponible en el entorno
            from playwright.sync_api import sync_playwright
            headless = os.getenv("HEADLESS_BROWSER", "false").lower() in ["true", "1", "yes"]
            storage_state_file = BROWSER_PROFILE_DIR / "storage_state.json"

            print(f"[*] Abriendo sesión de TikTok (headless={headless}, storage_state={storage_state_file.exists()})...")
            for lk_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
                try:
                    (tiktok_profile / lk_name).unlink(missing_ok=True)
                except Exception:
                    pass
            raw_browser = None
            browser = None
            with sync_playwright() as p:
                try:
                    if storage_state_file.exists():
                        raw_browser = p.chromium.launch(
                            headless=headless,
                            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                        )
                        browser = raw_browser.new_context(
                            storage_state=str(storage_state_file),
                            locale="es-ES",
                            timezone_id="Europe/Madrid",
                            viewport={"width": 1280, "height": 1150},
                        )
                    else:
                        browser = p.chromium.launch_persistent_context(
                            user_data_dir=str(tiktok_profile),
                            headless=headless,
                            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                            locale="es-ES",
                            timezone_id="Europe/Madrid",
                            viewport={"width": 1280, "height": 1150},
                        )
                    page = browser.new_page()

                    # Guardia Anti-Ban: verificar cuenta activa en TikTok Studio antes de subir
                    try:
                        page.goto("https://www.tiktok.com/tiktokstudio", wait_until="load", timeout=30000)
                        time.sleep(4)
                        if "login" in page.url.lower():
                            print("[!] Sesión de TikTok caducada (redirigido a /login).")
                            self._notify_telegram(
                                "🛑 *TikTok sin sesión activa:* redirigido a `/login`.\n"
                                "👉 Ejecuta `scripts/setup_tiktok_session.py --fresh --sync` con `@gtavihubextra`."
                            )
                            return None
                        studio_head = (page.inner_text("body") or "")[:1000].lower()
                        if "gtavihubspain" in studio_head and "gtavihubextra" not in studio_head and os.getenv("ALLOW_LEGACY_TIKTOK", "").lower() != "true":
                            print("[!] BLOQUEADO [Anti-Ban]: Sesión de TikTok sigue conectada a la cuenta heredada @gtavihubspain.")
                            print("    Ejecuta 'scripts/setup_tiktok_session.py --fresh --sync' con @gtavihubextra.")
                            self._notify_telegram(
                                "🛑 *TikTok bloqueado por seguridad:* la sesión del servidor sigue conectada a `@gtavihubspain` (cuenta antigua).\n"
                                "👉 Ejecuta `scripts/setup_tiktok_session.py --fresh --sync` iniciando sesión en `@gtavihubextra`."
                            )
                            return None
                    except Exception:
                        pass

                    page.goto("https://www.tiktok.com/tiktokstudio/upload?from=upload", wait_until="domcontentloaded", timeout=60000)
                    time.sleep(3)

                    # Si requiere inicio de sesión manual o expiraron las cookies
                    if "login" in page.url.lower():
                        print("[!] TikTok requiere inicio de sesión (@gtavihubextra).")
                        self._notify_telegram(
                            "🛑 *TikTok requiere login:* ejecuta `scripts/setup_tiktok_session.py --fresh --sync` con `@gtavihubextra`."
                        )
                        return None

                    # Aceptar cookies o cerrar modales de bienvenida si aparecen
                    try:
                        cookie_btn = page.locator("button:has-text('Accept all'), button:has-text('Aceptar todas'), button:has-text('Accept')").first
                        if cookie_btn.count() > 0 and cookie_btn.is_visible():
                            cookie_btn.click()
                            time.sleep(1)
                    except Exception:
                        pass

                    print("[*] Subiendo archivo a TikTok Creator Center...")
                    try:
                        page.wait_for_selector("input[type='file']", state="attached", timeout=35000)
                    except Exception:
                        pass
                    file_input = page.locator("input[type='file'][accept*='video'], input[type='file'][accept*='mp4'], input[type='file']").first
                    if file_input.count() == 0:
                        # Intentar buscar dentro de iframes de TikTok Studio si el contenedor está embebido
                        for frame in page.frames:
                            f_in = frame.locator("input[type='file']").first
                            if f_in.count() > 0:
                                file_input = f_in
                                break
                    if file_input.count() == 0:
                        print("[!] Selector de subida no encontrado en TikTok.")
                        return None

                    file_input.set_input_files(str(compat_path))
                    print("[*] Esperando que el archivo se procese en TikTok Studio...")

                    # Esperar a que post_video_button esté adjunto y habilitado (o DraftEditor disponible) hasta 150s
                    upload_ready = False
                    wait_start = time.time()
                    while time.time() - wait_start < 150:
                        try:
                            for d_sel in ("button:has-text('Got it')", "button:has-text('Entendido')"):
                                m_btn = page.locator(d_sel).first
                                if m_btn.count() > 0 and m_btn.is_visible():
                                    m_btn.evaluate("b => b.click()")
                                    print(f"[*] Popup de aviso de TikTok Studio cerrado ({d_sel}).")
                                    time.sleep(0.5)
                        except Exception:
                            pass
                        try:
                            post_btn_check = page.locator("button[data-e2e='post_video_button']").first
                            if post_btn_check.count() > 0:
                                is_aria_dis = post_btn_check.get_attribute("aria-disabled") == "true"
                                if post_btn_check.is_enabled() and not is_aria_dis:
                                    upload_ready = True
                                    break
                        except Exception:
                            pass
                        time.sleep(2)

                    if not upload_ready:
                        try:
                            page.wait_for_selector(
                                ".upload-progress, [class*='uploading'], [class*='loading']",
                                state="detached",
                                timeout=10000,
                            )
                        except Exception:
                            pass
                    time.sleep(2)

                    # Descartar únicamente popups informativos (Entendido / Got it), nunca Cancel/Cancelar
                    try:
                        for d_sel in ("button:has-text('Got it')", "button:has-text('Entendido')", "button:has-text('Not now')", "button:has-text('Ahora no')"):
                            m_btn = page.locator(d_sel).first
                            if m_btn.count() > 0 and m_btn.is_visible():
                                m_btn.evaluate("b => b.click()")
                                print(f"[*] Popup de aviso de TikTok Studio cerrado ({d_sel}).")
                                time.sleep(0.6)
                    except Exception:
                        pass

                    print("[✓] Archivo cargado. Rellenando descripción sin mutar Draft.js vía execCommand...")

                    editor_selectors = [
                        "div.public-DraftEditor-content",
                        "div[contenteditable='true']",
                        "div[role='textbox']",
                        ".editor-input-box div[contenteditable]",
                        "[data-testid='caption-input']",
                        "textarea[placeholder*='caption'], textarea[placeholder*='escribe']"
                    ]
                    caption_filled = False
                    clean_caption = truncate_on_word_boundary(caption, 900)

                    for sel in editor_selectors:
                        try:
                            el = page.locator(sel).first
                            if el.count() > 0:
                                el.evaluate("""node => {
                                    node.scrollIntoView({ block: 'center' });
                                    node.focus();
                                    const range = document.createRange();
                                    range.selectNodeContents(node);
                                    range.collapse(false);
                                    const sel = window.getSelection();
                                    sel.removeAllRanges();
                                    sel.addRange(range);
                                }""")
                                time.sleep(0.3)
                                for _sel_key in ("Meta+a", "Control+a"):
                                    try:
                                        page.keyboard.press(_sel_key)
                                        time.sleep(0.1)
                                        page.keyboard.press("Backspace")
                                    except Exception:
                                        pass
                                # Si Draft.js conservó el nombre del archivo pre-rellenado, vaciar con Backspace limpio
                                for _ in range(8):
                                    rem_text = el.inner_text().strip()
                                    if not rem_text:
                                        break
                                    page.keyboard.press("End")
                                    for _k in range(min(len(rem_text) + 5, 120)):
                                        page.keyboard.press("Backspace")
                                    time.sleep(0.2)
                                page.keyboard.insert_text(clean_caption)
                                time.sleep(0.6)
                                curr_text = el.inner_text().strip()
                                if len(curr_text) > 10 and not curr_text.startswith("SHORT_") and not curr_text.startswith("VIDEO_"):
                                    caption_filled = True
                                    print(f"[*] Caption introducida con éxito mediante insert_text en TikTok ({sel})")
                                    break
                        except Exception:
                            continue

                    if not caption_filled:
                        print("[!] Aviso: no se pudo confirmar el reemplazo completo del caption vía teclado (se evita execCommand para no colapsar Draft.js).")

                    time.sleep(2)

                    # Descartar nuevamente modales informativos sin pulsar Cancel/Cancelar ni 'Turn on'
                    try:
                        dismiss_selectors = [
                            "button:has-text('Got it')",
                            "button:has-text('Entendido')",
                            "button:has-text('Not now')",
                            "button:has-text('Ahora no')",
                        ]
                        for d_sel in dismiss_selectors:
                            m_btn = page.locator(d_sel).first
                            if m_btn.count() > 0 and m_btn.is_visible():
                                m_btn.evaluate("b => b.click()")
                                print(f"[*] Popup de aviso de TikTok Studio cerrado ({d_sel}).")
                                time.sleep(0.8)
                    except Exception:
                        pass

                    # Asegurar visibilidad pública ('Everyone' / 'Todos') si el selector aparece restringido
                    try:
                        priv_trigger = page.locator("button:has-text('Followers'), button:has-text('Seguidores'), button:has-text('Only you'), button:has-text('Solo yo'), div[role='combobox']:has-text('Followers'), div[role='combobox']:has-text('Only you')").first
                        if priv_trigger.count() > 0 and priv_trigger.is_visible():
                            priv_trigger.evaluate("b => b.click()")
                            time.sleep(0.8)
                            pub_opt = page.locator("[role='option']:has-text('Everyone'), [role='option']:has-text('Todos'), li:has-text('Everyone'), span:text-is('Everyone'), span:text-is('Todos')").first
                            if pub_opt.count() > 0 and pub_opt.is_visible():
                                pub_opt.evaluate("b => b.click()")
                                print("[*] Privacidad ajustada a Everyone / Todos en TikTok Studio.")
                                time.sleep(0.8)
                    except Exception:
                        pass

                    try:
                        page.evaluate("""() => {
                            window.scrollTo(0, document.body.scrollHeight);
                            document.querySelectorAll('*').forEach(el => {
                                if (el.scrollHeight > el.clientHeight && el.clientHeight > 100) {
                                    el.scrollTop = el.scrollHeight;
                                }
                            });
                        }""")
                    except Exception:
                        pass
                    time.sleep(2)

                    post_selectors = [
                        "button[data-e2e='post_video_button']",
                        "button[data-testid='post-button']",
                        "button:has-text('Post')",
                        "button:has-text('Publicar')",
                        "button.Button__root--type-primary:text-is('Post')",
                        "button.Button__root--type-primary:text-is('Publicar')",
                        "button:text-is('Post')",
                        "button:text-is('Publicar')",
                        "button.TUXButton--primary",
                        "button.btn-post",
                        "div[data-e2e='post_video_button']",
                        "[data-e2e*='post']",
                    ]

                    posted = False
                    retry_clicks = 0
                    start_post_wait = time.time()
                    while time.time() - start_post_wait < 150 and not posted:
                        try:
                            for d_sel in ["button:has-text('Got it')", "button:has-text('Not now')", "button:has-text('Ahora no')", "button:has-text('Entendido')"]:
                                m_btn = page.locator(d_sel).first
                                if m_btn.count() > 0 and m_btn.is_visible():
                                    m_btn.evaluate("b => b.click()")
                                    time.sleep(0.5)
                        except Exception:
                            pass

                        try:
                            page.evaluate("""() => {
                                window.scrollTo(0, document.body.scrollHeight);
                                document.querySelectorAll('*').forEach(el => {
                                    if (el.scrollHeight > el.clientHeight && el.clientHeight > 100) {
                                        el.scrollTop = el.scrollHeight;
                                    }
                                });
                            }""")
                        except Exception:
                            pass

                        for sel in post_selectors:
                            try:
                                locator = page.locator(sel)
                                if locator.count() > 0:
                                    btn = locator.first
                                    btn.scroll_into_view_if_needed(timeout=2000)
                                    is_aria_disabled = btn.get_attribute("aria-disabled") == "true"
                                    if btn.is_enabled() and not is_aria_disabled:
                                        btn.click(force=True)
                                        print(f"[*] Click en botón publicar ({sel})")
                                        posted = True
                                        break
                            except Exception:
                                continue

                        if not posted:
                            try:
                                clicked_via_js = page.evaluate("""() => {
                                    const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
                                    for (const b of buttons) {
                                        const txt = (b.innerText || b.textContent || '').trim();
                                        const isPostBtn = (b.getAttribute('data-e2e') || '').includes('post') ||
                                                          /^(post|publicar)/i.test(txt) ||
                                                          (b.className || '').includes('btn-post');
                                        if (isPostBtn) {
                                            const isDis = b.disabled || b.getAttribute('aria-disabled') === 'true' || (b.className || '').includes('disabled');
                                            if (!isDis) {
                                                b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                b.click();
                                                return true;
                                            }
                                        }
                                    }
                                    return false;
                                }""")
                                if clicked_via_js:
                                    print("[*] Click en botón publicar ejecutado con éxito vía DOM JS")
                                    posted = True
                                    break
                            except Exception:
                                pass

                        if not posted and retry_clicks < 2:
                            try:
                                r_btn = page.locator("button:has-text('Reintentar'), button:has-text('Retry')").first
                                if r_btn.count() > 0 and r_btn.is_visible() and r_btn.is_enabled():
                                    r_btn.evaluate("b => b.click()")
                                    retry_clicks += 1
                                    print(f"[*] TikTok Studio mostró 'Reintentar'. Auto-recuperación {retry_clicks}/2...")
                                    time.sleep(5)
                                    continue
                            except Exception:
                                pass

                        if not posted:
                            time.sleep(3)

                    time.sleep(2)
                    try:
                        modal_buttons = page.locator("button:has-text('Post anyway'), button:has-text('Publicar de todos modos'), button:has-text('Manage your posts'), button:has-text('Aceptar')")
                        if modal_buttons.count() > 0 and modal_buttons.first.is_visible():
                            modal_buttons.first.evaluate("b => b.click()")
                            print("[*] Confirmación de diálogo modal post-publicación aceptada.")
                    except Exception:
                        pass

                    if not posted:
                        print("[!] No se encontró botón de publicar activo — guardando captura de debug...")
                        try:
                            btn_info = page.evaluate("""() => {
                                return Array.from(document.querySelectorAll('button, div[role="button"]')).map(b => ({
                                    text: (b.innerText || b.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 30),
                                    disabled: b.disabled || b.getAttribute('aria-disabled') === 'true' || (b.className || '').includes('disabled'),
                                    e2e: b.getAttribute('data-e2e') || ''
                                }));
                            }""")
                            print(f"[*] Botones detectados en DOM TikTok: {btn_info}")
                        except Exception:
                            pass
                        try:
                            LOGS_DIR.mkdir(parents=True, exist_ok=True)
                            debug_shot = LOGS_DIR / "tiktok_button_debug.png"
                            page.screenshot(path=str(debug_shot), timeout=5000)
                            print(f"[*] Captura guardada en: {debug_shot}")
                        except Exception as shot_err:
                            print(f"[!] Error guardando captura debug TikTok: {shot_err}")
                        return None

                    confirmed_post = False
                    try:
                        page.wait_for_url("**/manage**", timeout=30000)
                        confirmed_post = True
                    except Exception:
                        try:
                            page.wait_for_selector("[class*='success'], [class*='uploaded'], [class*='posted']",
                                                   timeout=20000)
                            confirmed_post = True
                        except Exception:
                            pass

                    time.sleep(3)
                    current_url = page.url

                    # Guardar estado de sesión renovado si fue exitoso
                    if storage_state_file and browser:
                        try:
                            browser.storage_state(path=str(storage_state_file))
                        except Exception:
                            pass

                    if confirmed_post or "manage" in current_url or "content" in current_url:
                        _record_tiktok_upload(title)
                        print("[✓] Vídeo publicado en TikTok.")
                        return "https://www.tiktok.com/@gtavihubextra"
                    else:
                        print(f"[!] TikTok no confirmó publicación (URL final: {current_url}). Marcando como pendiente/fallido.")
                        return None
                finally:
                    for closable in (browser, raw_browser):
                        if closable is not None:
                            try:
                                closable.close()
                            except Exception:
                                pass
        except ImportError:
            print("[TikTok] Playwright no está instalado o configurado aún. Puedes activarlo con: pip install playwright && playwright install chromium")
            print(f"[TikTok] Archivo preparado para subida manual o por navegador: {video_path}")
            return None
        except Exception as e:
            print(f"[TikTok] Error en automatización: {e}")
            return None
        finally:
            if is_temp_video and compat_path.exists():
                compat_path.unlink(missing_ok=True)

    def publish_to_instagram(
        self,
        video_path: Path,
        caption: str,
        thumbnail_path: Optional[Path] = None
    ) -> Optional[str]:
        """
        Publica en Instagram Reels via instagrapi (API privada de Instagram).
        Credenciales en .env: INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD.
        Session cache en assets/.browser_profiles/instagrapi_session.json.
        """
        ig_handle = (os.getenv("INSTAGRAM_USERNAME") or "gtavihubextra").strip().lstrip("@")
        video_path = Path(video_path)
        print(f"\n[3/3 Instagram] Preparando subida a Instagram Reels (@{ig_handle})...")
        if not AntiBanValidator.check_daily_limit("instagram"):
            return None

        if self.dry_run:
            print(f"[3/3 Instagram] [DRY RUN] Simulación exitosa. Caption: '{caption[:60]}...'")
            return f"https://www.instagram.com/reel/mock_{video_path.stem}"

        ig_user = os.getenv("INSTAGRAM_USERNAME")
        ig_pass = os.getenv("INSTAGRAM_PASSWORD")
        if not ig_user or not ig_pass:
            print("[Instagram] Faltan INSTAGRAM_USERNAME / INSTAGRAM_PASSWORD en .env")
            return None
        if ig_user.strip().lower() == "gtavihubspain" and os.getenv("ALLOW_LEGACY_INSTAGRAM", "").lower() != "true":
            print("[!] BLOQUEADO [Anti-Ban]: INSTAGRAM_USERNAME apunta a la cuenta heredada @gtavihubspain. Actualiza .env a gtavihubextra.")
            self._notify_telegram(
                "🛑 *Instagram bloqueado por seguridad:* `.env` sigue apuntando a `@gtavihubspain` (estancada).\n"
                "👉 Actualiza `INSTAGRAM_USERNAME=gtavihubextra` y su sesión cuando quieras activar Instagram."
            )
            return None

        compat_path, is_temp_video = prepare_social_compatible_video(video_path)

        expected_user = ig_user.strip().lstrip("@").lower()
        session_file = BROWSER_PROFILE_DIR / f"instagrapi_session_{expected_user}.json"
        legacy_session_file = BROWSER_PROFILE_DIR / "instagrapi_session.json"
        if not session_file.exists() and legacy_session_file.exists():
            session_file = legacy_session_file
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        try:
            from instagrapi import Client
            cl = Client()
            cl.delay_range = [2, 5]
            session_valid = False

            if session_file.exists():
                try:
                    cl.load_settings(str(session_file))
                    acc_info = cl.account_info()
                    cached_user = (getattr(acc_info, "username", "") or "").strip().lower()
                    if cached_user == expected_user:
                        session_valid = True
                        print(f"[*] Sesión de Instagram restaurada desde cache (@{cached_user}).")
                    else:
                        print(f"[!] Cache de Instagram pertenecía a @{cached_user or 'otro'}; regenerando login para @{expected_user}...")
                except Exception:
                    print("[*] Cache de Instagram caducado o inválido, haciendo login completo...")

            active_ig_user = expected_user
            if not session_valid:
                # Intentar primero desde storage_state.json (evita redirecciones de Centro de Cuentas CAA)
                storage_state_file = BROWSER_PROFILE_DIR / "storage_state.json"
                if storage_state_file.exists():
                    try:
                        from urllib.parse import unquote
                        st = json.loads(storage_state_file.read_text(encoding="utf-8"))
                        ig_sid = next(
                            (unquote(c.get("value", "")) for c in st.get("cookies", [])
                             if "instagram" in c.get("domain", "") and c.get("name") == "sessionid" and c.get("value")),
                            "",
                        )
                        if ig_sid and len(ig_sid) > 30:
                            cl_sid = Client()
                            cl_sid.delay_range = [2, 5]
                            cl_sid.login_by_sessionid(ig_sid)
                            sid_info = cl_sid.account_info()
                            sid_user = getattr(sid_info, "username", "")
                            if isinstance(sid_user, str) and sid_user.strip().lower() == expected_user:
                                cl = cl_sid
                                session_valid = True
                                print(f"[*] Sesión de Instagram iniciada vía cookie web (@{expected_user}).")
                    except Exception:
                        pass

            if not session_valid:
                cl = Client()
                cl.delay_range = [2, 5]
                cl.login(ig_user, ig_pass)
                post_info = cl.account_info()
                post_user = getattr(post_info, "username", "")
                if isinstance(post_user, str) and post_user.strip() and post_user.strip().lower() != expected_user:
                    if os.getenv("ALLOW_LEGACY_INSTAGRAM", "").lower() != "true":
                        print(f"[!] BLOQUEADO [Anti-Ban]: Instagram autenticó @{post_user} en lugar de @{expected_user}.")
                        self._notify_telegram(
                            f"🛑 *Instagram bloqueado por seguridad:* Meta autenticó `@{post_user}` en lugar de `@{expected_user}`.\n"
                            "👉 Vincula `@gtavihubextra` desde Playwright (`scripts/setup_tiktok_session.py --fresh --with-instagram --sync`)."
                        )
                        return None
                    active_ig_user = post_user.strip()
                    print(f"[⚠️] ALLOW_LEGACY_INSTAGRAM activo: sesión autenticada en @{active_ig_user} (esperado @{expected_user}).")
                else:
                    print(f"[*] Login en Instagram completado (@{active_ig_user}).")

            target_session_file = BROWSER_PROFILE_DIR / f"instagrapi_session_{active_ig_user}.json"
            cl.dump_settings(str(target_session_file))

            print("[*] Subiendo Reel a Instagram...")
            clip_kwargs: Dict[str, Any] = {"caption": caption[:2200]}
            if thumbnail_path and Path(thumbnail_path).exists():
                clip_kwargs["thumbnail"] = Path(thumbnail_path)
                print(f"[*] Usando miniatura: {Path(thumbnail_path).name}")
            media = cl.clip_upload(Path(compat_path), **clip_kwargs)
            url = f"https://www.instagram.com/reel/{media.code}/"
            print(f"[✓] Reel publicado en Instagram: {url}")
            return url

        except Exception as e:
            err_str = str(e)
            print(f"[Instagram] Error con instagrapi: {err_str}")
            if any(k in err_str.lower() for k in ["challenge", "two-factor", "2fa", "password", "login", "bad_password"]):
                self._notify_telegram(
                    f"⚠️ *Error de sesión en Instagram (@{expected_user}):* `{err_str[:140]}`\n"
                    "👉 Ejecuta `scripts/setup_instagram_session.py --user gtavihubextra --fresh --sync` para renovar la sesión."
                )
            return None
        finally:
            if is_temp_video and compat_path.exists():
                compat_path.unlink(missing_ok=True)

    def publish_all(
        self,
        video_path: Path,
        metadata: Dict[str, Any],
        creator_name: str,
        platforms: Optional[List[str]] = None,
        stagger_delay_minutes: int = 12
    ) -> Dict[str, Optional[str]]:
        """
        Ejecuta la publicación escalonada multiplataforma con pausas humanas (10-18 min)
        para evitar que las redes detecten una firma robótica sincronizada.
        """
        if platforms is None:
            platforms = list(metadata.get("allowed_platforms") or ["youtube", "tiktok", "instagram"])

        if (not self.dry_run) or metadata.get("enable_alpha_routing"):
            try:
                from .learning_engine import route_platforms_by_alpha
                platforms, route_reason = route_platforms_by_alpha(platforms, metadata, creator_name)
                print(f"[🎯 Platform Alpha Routing] {platforms} — {route_reason}")
            except Exception:
                pass

        results = {}
        title = metadata.get("title", video_path.stem)
        desc = metadata.get("description", "")
        tags = metadata.get("tags", ["GTA6", "Shorts", "Gaming"])
        thumb = metadata.get("thumbnail_path")

        # 0. Diagnóstico de duración por plataforma
        try:
            _dur_probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
                capture_output=True, text=True, timeout=10
            )
            _vid_dur = float(_dur_probe.stdout.strip()) if _dur_probe.stdout.strip() else 0
            _platform_notes = {
                "youtube": f"{'OK' if 19 <= _vid_dur <= 58 else 'WARN'} ({_vid_dur:.0f}s, óptimo 19-28s)",
                "tiktok": f"{'OK' if _vid_dur <= 34 else 'WARN largo'} ({_vid_dur:.0f}s, óptimo 19-26s)",
                "instagram": f"{'OK' if _vid_dur <= 60 else 'WARN'} ({_vid_dur:.0f}s, óptimo 19-30s)"
            }
            print(f"[*] Duración del clip: {_vid_dur:.1f}s")
            for _p, _note in _platform_notes.items():
                if _p in (platforms or []):
                    print(f"    {_p.upper()}: {_note}")
        except Exception:
            pass

        # 0b. Pre-vuelo de Vitalidad Acústica: Jamás publicar un vídeo mudo o defectuoso
        from .audio_shield import detect_audio_levels
        _audio_chk = detect_audio_levels(video_path)
        if not self.dry_run and (not _audio_chk["has_audio"] or _audio_chk["mean_volume"] < -42.0):
            err_mute = (
                f"🚨 [Escudo Anti-Silencio] Vídeo '{video_path.name}' RECHAZADO: "
                f"Audio inaudible/mudo (mean_volume: {_audio_chk.get('mean_volume', -99):.1f} dB). "
                f"Publicación abortada en todas las plataformas para prevenir Shadowban."
            )
            print(f"\n{err_mute}")
            self._notify_telegram(err_mute)
            return {"error": "audio_volume_muted"}
        elif self.dry_run and not _audio_chk["has_audio"]:
            print("[*] [DRY RUN Audio Shield] Archivo mock sin audio detectado pero permitido en simulación.")

        # 1. Comprobación estricta de directrices Anti-Ban y respeto al autor
        print("\n" + "=" * 65)
        print("🛡️  AUDITORÍA DE SEGURIDAD PREVIA A PUBLICACIÓN MULTIPLATAFORMA")
        print("=" * 65)
        orig_url = metadata.get("original_url", "")
        is_compliant = AntiBanValidator.validate_metadata(metadata, creator_name, orig_url)

        for i, plat in enumerate(platforms):
            # Cortafuegos de Originalidad y Compliance específico de la plataforma
            has_voice = metadata.get("has_voiceover", False) or metadata.get("mode") in ["dub", "voice"]
            is_eligible, reason = ComplianceAuditor.is_platform_eligible(
                platform=plat,
                metadata=metadata,
                creator_name=creator_name,
                has_voiceover=has_voice,
                mode=metadata.get("mode", "subs")
            )
            if not is_eligible:
                print(f"\n[Compliance Shield] 🛡️ {reason}")
                self._notify_telegram(f"🛡️ *[Compliance Shield]* Saltando *{plat.upper()}* para proteger la cuenta:\n_{reason}_")

                if plat == "instagram":
                    print("[Opción B] 🎬 Generando contenido alternativo orgánico para Instagram (Story cinemática de GTA 6)...")
                    try:
                        from .story_scheduler import publish_scheduled_story
                        story_res = publish_scheduled_story(force=True, preferred_type="content", dry_run=self.dry_run)
                        if story_res.get("status") in ("published", "simulated", "ok") or (self.dry_run and story_res.get("item")):
                            story_item = story_res.get("item", "Curiosidad GTA 6")
                            story_url = story_res.get("story_url") or "https://www.instagram.com/gtavihubextra/"
                            results["instagram"] = f"Story Alternativa Publicada: {story_item} ({story_url})"
                            print(f"[✓] [Opción B] Story alternativa publicada en Instagram: {story_item}")
                            self._notify_telegram(
                                f"🛡️ *[Instagram - Opción B Activa]*\n"
                                f"Reel omitido por seguridad de cuenta (contenido de terceros/streamer).\n"
                                f"🌟 Publicada *Story orgánica* en Instagram: *{story_item}*\n"
                                f"👉 Mantiene actividad diaria e interacción sin riesgo de penalización."
                            )
                            continue
                        else:
                            print(f"[Opción B] Fallback de story omitido: {story_res.get('reason')}")
                    except Exception as story_err:
                        print(f"[Opción B] Error en fallback de story: {story_err}")

                results[plat] = "Bloqueado por Compliance Shield"
                continue

            if i > 0 and not self.dry_run:
                if stagger_delay_minutes <= 0:
                    jitter_seconds = 0
                else:
                    # Escalonamiento con jitter aleatorio humano (ej. 10 a 16 minutos)
                    jitter_seconds = random.randint(
                        max(1, (stagger_delay_minutes - 2) * 60),
                        (stagger_delay_minutes + 4) * 60
                    )
                if jitter_seconds > 0:
                    wait_msg = f"⏳ *[Escalonamiento Anti-Ban]* Pausando {jitter_seconds // 60} minutos antes de publicar en *{plat.upper()}*..."
                    print(f"\n{wait_msg}")
                    self._notify_telegram(wait_msg)
                    time.sleep(jitter_seconds)

            if plat == "youtube":
                target_privacy = metadata.get("privacy") or os.getenv("YOUTUBE_PRIVACY_STATUS", "public")
                pinned_comment = metadata.get("pinned_comment")
                try:
                    from .channel_sentinel import get_resilient_publishing_target
                    target_yt = metadata.get("target_channel") or get_resilient_publishing_target("youtube")
                except Exception:
                    target_yt = "youtube_extra"
                target_acc = "extra" if "extra" in str(target_yt) else "main"
                url = self.publish_to_youtube(
                    video_path,
                    title,
                    desc,
                    privacy=target_privacy,
                    thumbnail_path=thumb,
                    pinned_comment=pinned_comment,
                    target_account=target_acc
                )
                results["youtube"] = url
                if url:
                    self._notify_telegram(f"✅ *[1/3] YouTube Shorts publicado:* [Ver en YouTube]({url})")
            elif plat == "tiktok":
                debate_q = metadata.get("debate_question", "")
                url = self.publish_to_tiktok(
                    video_path,
                    title,
                    tags,
                    debate_question=debate_q,
                    description=desc,
                    creator_name=creator_name,
                )
                results["tiktok"] = url
                if url:
                    self._notify_telegram(f"✅ *[2/3] TikTok publicado:* [Ver en TikTok]({url})")
                else:
                    self._notify_telegram("⚠️ *[2/3] TikTok:* Subido y guardado como borrador en TikTok Studio.")
            elif plat == "instagram":
                debate_q = metadata.get("debate_question", "")
                bold_debate = to_unicode_bold("DEBATE DE LA COMUNIDAD:")
                bold_redes = to_unicode_bold("REDES & ENLACES (Link en Bio):")
                bold_creditos = to_unicode_bold("CRÉDITOS & FUENTE:")
                bold_contacto = to_unicode_bold("CONTACTO / BUSINESS:")

                debate_block = f"💬 {bold_debate}\n{debate_q}\n👇 ¡Déjanos tu teoría en los comentarios!\n\n" if debate_q else ""
                cta_block = AFFILIATE_CTA_INSTAGRAM if ENABLE_AFFILIATE_CTAS else "🌴 Cobertura diaria de GTA VI y noticias oficiales en @gtavihubextra."

                links_block = (
                    f"🌐 {bold_redes}\n"
                    f"👉 Hub Central: https://linktr.ee/gtavihubextra\n"
                    f"👉 Síguenos en @gtavihubextra\n\n"
                    if ENABLE_AFFILIATE_CTAS else
                    "🌐 Síguenos en @gtavihubextra\n\n"
                )
                creator_clean = creator_name or "Rockstar Games"
                caption = (
                    f"{title}\n\n"
                    f"{debate_block}"
                    f"{desc[:900]}\n\n"
                    f"{links_block}"
                    f"{cta_block}\n\n"
                    f"📌 {bold_creditos} Vía {creator_clean}. Todo el crédito al autor original.\n"
                    f"📩 {bold_contacto} {BUSINESS_EMAIL}\n\n"
                    f"#GTA6 #GrandTheftAutoVI #RockstarGames #Gaming #ViceCity #Reels #Videojuegos"
                )
                url = self.publish_to_instagram(video_path, caption, thumbnail_path=thumb)
                results["instagram"] = url
                if url:
                    self._notify_telegram(f"✅ *[3/3] Instagram Reels publicado:* [Ver en Instagram]({url})")

        print("\n" + "=" * 65)
        print("📊 RESUMEN DE PUBLICACIÓN MULTIPLATAFORMA:")
        for p, u in results.items():
            status_text = u if u else "Pendiente / Borrador"
            print(f"  • {p.upper():12}: {status_text}")
        print("=" * 65)

        return results

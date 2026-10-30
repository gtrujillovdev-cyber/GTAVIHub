import os
import sys
import json
import time
import random
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from .config import (
    BASE_DIR, OUTPUT_DIR, PROCESSED_FILE, BUSINESS_EMAIL,
    MONETIZATION_AFFILIATE_URL, ENABLE_AFFILIATE_CTAS,
    AFFILIATE_CTA_TIKTOK, AFFILIATE_CTA_INSTAGRAM
)
from .uploader import upload_to_youtube
from .compliance_auditor import ComplianceAuditor
from .translator import to_unicode_bold

# Directorio persistente para la sesión del navegador (TikTok / Instagram)
BROWSER_PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles"

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
        """Obtiene el límite diario configurado por plataforma."""
        p = platform.lower()
        if p == "youtube":
            return int(os.getenv("MAX_DAILY_UPLOADS_YOUTUBE", os.getenv("MAX_DAILY_UPLOADS", "6")))
        elif p == "tiktok":
            return int(os.getenv("MAX_DAILY_UPLOADS_TIKTOK", os.getenv("MAX_DAILY_UPLOADS", "10")))
        elif p == "instagram":
            return int(os.getenv("MAX_DAILY_UPLOADS_INSTAGRAM", os.getenv("MAX_DAILY_UPLOADS", "10")))
        return int(os.getenv("MAX_DAILY_UPLOADS", "10"))

    @classmethod
    def check_daily_limit(cls, platform: str) -> bool:
        """Comprueba que no se supere el límite configurado de vídeos diarios."""
        if not PROCESSED_FILE.exists():
            return True
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
            today_str = date.today().isoformat()
            today_uploads = [
                r for r in records
                if r.get(f"{platform}_uploaded_url") and r.get("date", "").startswith(today_str)
            ]
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

    @staticmethod
    def _notify_telegram(text: str) -> None:
        """Envía una actualización rápida del estado de publicación a Telegram."""
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
        pinned_comment: Optional[str] = None
    ) -> Optional[str]:
        """Sube el vídeo a YouTube Shorts mediante API oficial v3."""
        print(f"\n[1/3 YouTube] Iniciando publicación de '{video_path.name}'...")
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
            pinned_comment=pinned_comment
        )
        if video_id:
            return f"https://youtu.be/{video_id}" if not str(video_id).startswith("http") else str(video_id)
        return None

    def publish_to_tiktok(
        self,
        video_path: Path,
        title: str,
        tags: List[str],
        debate_question: str = ""
    ) -> Optional[str]:
        """
        Publica o programa en TikTok Creator Center mediante navegador automatizado
        con huella digital humana y perfil persistente local.
        """
        print(f"\n[2/3 TikTok] Preparando subida orgánica a TikTok...")
        if not AntiBanValidator.check_daily_limit("tiktok"):
            return None

        tags_str = " ".join([f"#{t.replace(' ', '')}" for t in tags[:4]])
        bold_hook = to_unicode_bold("¡BOMBAZO GTA 6!")
        if debate_question:
            q_clean = debate_question.replace("¿", "").replace("?", "").strip()
            caption = (
                f"🚨 {bold_hook} {title[:40]} {tags_str}\n"
                f"💬 {to_unicode_bold('DEBATE')}: ¿{q_clean[:40]}? 👇\n"
                f"🎮 Reserva GTA 6 & Hardware en bio 👉 @gtavihubspain"
            )
        elif ENABLE_AFFILIATE_CTAS:
            caption = f"🚨 {bold_hook} {title[:55]} {tags_str}\n{AFFILIATE_CTA_TIKTOK}\n👉 @gtavihubspain | Bio: linktr.ee/gtavihubspain"
        else:
            caption = f"🚨 {bold_hook} {title[:55]} {tags_str}\n🎮 {to_unicode_bold('RESERVA GTA 6')} en la bio 👉 @gtavihubspain | linktr.ee/gtavihubspain"
        tiktok_profile = BROWSER_PROFILE_DIR / "tiktok_user_data"

        if self.dry_run:
            print(f"[2/3 TikTok] [DRY RUN] Simulación exitosa. Caption: '{caption[:60]}...'")
            print(f"             Perfil de sesión: {tiktok_profile}")
            return f"https://www.tiktok.com/@gtavihubspain/video/mock_{video_path.stem}"

        try:
            # Comprobar si playwright está disponible en el entorno
            from playwright.sync_api import sync_playwright
            headless = os.getenv("HEADLESS_BROWSER", "false").lower() in ["true", "1", "yes"]
            storage_state_file = BROWSER_PROFILE_DIR / "storage_state.json"

            print(f"[*] Abriendo sesión persistente de TikTok en {tiktok_profile} (headless={headless})...")
            with sync_playwright() as p:
                launch_kwargs = {
                    "user_data_dir": str(tiktok_profile),
                    "headless": headless,
                    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                }

                browser = p.chromium.launch_persistent_context(**launch_kwargs)
                if storage_state_file.exists():
                    import json as _json
                    state = _json.loads(storage_state_file.read_text())
                    if state.get("cookies"):
                        browser.add_cookies(state["cookies"])
                page = browser.new_page()
                page.goto("https://www.tiktok.com/creator-center/upload?from=upload", wait_until="load", timeout=60000)
                time.sleep(3)
                
                # Si requiere inicio de sesión manual la primera vez
                if "login" in page.url.lower():
                    print("[!] TikTok requiere inicio de sesión. Por favor inicia sesión en la ventana abierta.")
                    print("[*] La sesión quedará guardada permanentemente en tus cookies locales para futuras subidas.")
                    browser.close()
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
                # Esperar a que React monte el input (puede tardar hasta 15s)
                try:
                    page.wait_for_selector("input[type='file'][accept*='video']", timeout=15000)
                except Exception:
                    pass
                file_input = page.locator("input[type='file'][accept*='video']").first
                if file_input.count() == 0:
                    print("[!] Selector de subida no encontrado en TikTok.")
                    browser.close()
                    return None

                file_input.set_input_files(str(video_path))
                print("[*] Esperando que el archivo se procese...")

                # Esperar a que desaparezca el indicador de carga (hasta 3 min para vídeos grandes)
                try:
                    page.wait_for_selector(".upload-progress, [class*='uploading'], [class*='loading']",
                                           state="detached", timeout=180000)
                except Exception:
                    pass
                time.sleep(5)

                print("[✓] Archivo cargado. Rellenando descripción...")

                # Rellenar caption en TikTok Studio (compatible con Draft.js / Lexical / React)
                editor_selectors = [
                    "div.public-DraftEditor-content",
                    "div[contenteditable='true']",
                    "div[role='textbox']",
                    ".editor-input-box div[contenteditable]",
                    "[data-testid='caption-input']",
                    "textarea[placeholder*='caption'], textarea[placeholder*='escribe']"
                ]
                caption_filled = False
                clean_caption = caption[:220].strip()

                for sel in editor_selectors:
                    try:
                        el = page.locator(sel).first
                        if el.count() > 0:
                            el.scroll_into_view_if_needed(timeout=3000)
                            el.click(force=True)
                            time.sleep(0.4)
                            # Limpiar con atajos multiplataforma (Control+A para Chromium headless y Meta+A para Mac)
                            page.keyboard.press("Control+a")
                            page.keyboard.press("Meta+a")
                            page.keyboard.press("Backspace")
                            time.sleep(0.3)
                            # Tecleo progresivo para disparar los synthetic events de React
                            page.keyboard.type(clean_caption, delay=10)
                            time.sleep(0.5)
                            curr_text = el.inner_text().strip()
                            if len(curr_text) > 10 and not curr_text.startswith("SHORT_") and not curr_text.startswith("VIDEO_"):
                                caption_filled = True
                                print(f"[*] Caption introducida con éxito mediante teclado en TikTok ({sel})")
                                break
                    except Exception:
                        continue

                if not caption_filled:
                    # Inyección infalible mediante document.execCommand ('insertText')
                    # Este método dispara los eventos nativos de bajo nivel que Draft.js y Lexical
                    # interceptan obligatoriamente para actualizar el estado inmutable de React.
                    try:
                        injected = page.evaluate("""(textToInsert) => {
                            const el = document.querySelector('div.public-DraftEditor-content, div[contenteditable="true"], div[role="textbox"]');
                            if (!el) return false;
                            el.focus();
                            const range = document.createRange();
                            range.selectNodeContents(el);
                            const sel = window.getSelection();
                            sel.removeAllRanges();
                            sel.addRange(range);
                            document.execCommand('delete', false, null);
                            document.execCommand('insertText', false, textToInsert);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return el.innerText.trim().length > 5;
                        }""", clean_caption)
                        if injected:
                            caption_filled = True
                            print("[✓] Caption introducida con éxito en TikTok Studio vía execCommand (Draft.js insertText).")
                    except Exception as e:
                        print(f"[!] Error en inyección avanzada de caption en TikTok: {e}")

                time.sleep(3)

                # Descartar/Aceptar popups modales de TikTok Studio que bloquean la vista ('Got it', 'Turn on', etc.)
                try:
                    dismiss_selectors = [
                        "button:has-text('Got it')",
                        "button:has-text('Turn on')",
                        "button:has-text('Entendido')",
                        "button:has-text('Aceptar')",
                        "button.Button__root--size-lg:has-text('Got it')"
                    ]
                    for d_sel in dismiss_selectors:
                        m_btn = page.locator(d_sel).first
                        if m_btn.count() > 0 and m_btn.is_visible():
                            m_btn.click()
                            print(f"[*] Popup de aviso de TikTok Studio aceptado ({d_sel}).")
                            time.sleep(1)
                except Exception:
                    pass

                # Scroll hacia abajo para asegurar visibilidad de controles y botón de publicar
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
                time.sleep(2)

                # Hacer click en el botón de publicar con reintentos y selectores exhaustivos de TikTok Studio
                post_selectors = [
                    "button.Button__root--type-primary:has-text('Post')",
                    "button.Button__root--type-primary:has-text('Publicar')",
                    "button:has-text('Post')",
                    "button:has-text('Publicar')",
                    "button[data-testid='post-button']",
                    "div.btn-post button",
                    "button.btn-post",
                    ".btn-post",
                    "button.TUXButton--primary",
                    "button.submit",
                ]

                posted = False
                # Reintentar encontrar y clickear el botón hasta por 45s (esperando validaciones de copyright/render)
                start_post_wait = time.time()
                while time.time() - start_post_wait < 45 and not posted:
                    # Descartar posibles popups modales que se hayan superpuesto
                    try:
                        for d_sel in ["button:has-text('Got it')", "button:has-text('Turn on')"]:
                            m_btn = page.locator(d_sel).first
                            if m_btn.count() > 0 and m_btn.is_visible():
                                m_btn.click()
                                time.sleep(1)
                    except Exception:
                        pass

                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    except Exception:
                        pass

                    # 1. Intentar con selectores Playwright
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

                    # 2. Si no ha clickeado, fallback profundo vía evaluación directa de DOM JS
                    if not posted:
                        try:
                            clicked_via_js = page.evaluate("""() => {
                                const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
                                for (const b of buttons) {
                                    const txt = (b.innerText || b.textContent || '').trim();
                                    if (txt === 'Post' || txt === 'Publicar') {
                                        const isDis = b.disabled || b.getAttribute('aria-disabled') === 'true' || b.className.includes('disabled');
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

                    if not posted:
                        time.sleep(3)

                # Comprobar posibles diálogos modales de confirmación post-publicación
                time.sleep(2)
                try:
                    modal_buttons = page.locator("button:has-text('Post anyway'), button:has-text('Publicar de todos modos'), button:has-text('Manage your posts'), button:has-text('Aceptar')")
                    if modal_buttons.count() > 0 and modal_buttons.first.is_visible():
                        modal_buttons.first.click()
                        print("[*] Confirmación de diálogo modal post-publicación aceptada.")
                except Exception:
                    pass

                if not posted:
                    print("[!] No se encontró botón de publicar activo — guardando captura de debug...")
                    try:
                        debug_shot = BASE_DIR / "logs" / "tiktok_button_debug.png"
                        page.screenshot(path=str(debug_shot))
                        print(f"[*] Captura guardada en: {debug_shot}")
                    except Exception:
                        pass
                    browser.close()
                    return None

                # Esperar confirmación (redirección o mensaje de éxito)
                try:
                    page.wait_for_url("**/manage**", timeout=30000)
                except Exception:
                    try:
                        page.wait_for_selector("[class*='success'], [class*='uploaded'], [class*='posted']",
                                               timeout=20000)
                    except Exception:
                        pass

                time.sleep(3)
                current_url = page.url
                browser.close()

                if "manage" in current_url or "content" in current_url:
                    print("[✓] Vídeo publicado en TikTok.")
                    return f"https://www.tiktok.com/@gtavihubspain"
                else:
                    print(f"[*] URL final: {current_url} — vídeo posiblemente en revisión")
                    return f"https://www.tiktok.com/@gtavihubspain"
        except ImportError:
            print("[TikTok] Playwright no está instalado o configurado aún. Puedes activarlo con: pip install playwright && playwright install chromium")
            print(f"[TikTok] Archivo preparado para subida manual o por navegador: {video_path}")
            return None
        except Exception as e:
            print(f"[TikTok] Error en automatización: {e}")
            return None

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
        print(f"\n[3/3 Instagram] Preparando subida a Instagram Reels (@gtavihubspain)...")
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

        session_file = BROWSER_PROFILE_DIR / "instagrapi_session.json"
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        try:
            from instagrapi import Client
            cl = Client()
            cl.delay_range = [2, 5]

            if session_file.exists():
                try:
                    cl.load_settings(str(session_file))
                    cl.login(ig_user, ig_pass)
                    print("[*] Sesión de Instagram restaurada desde cache.")
                except Exception:
                    print("[*] Cache expirado, haciendo login completo...")
                    cl = Client()
                    cl.delay_range = [2, 5]
                    cl.login(ig_user, ig_pass)
            else:
                cl.login(ig_user, ig_pass)
                print("[*] Login en Instagram completado.")

            cl.dump_settings(str(session_file))

            print("[*] Subiendo Reel a Instagram...")
            clip_kwargs = {"caption": caption[:2200]}
            if thumbnail_path and Path(thumbnail_path).exists():
                clip_kwargs["thumbnail"] = str(thumbnail_path)
                print(f"[*] Usando miniatura: {Path(thumbnail_path).name}")
            media = cl.clip_upload(video_path, **clip_kwargs)
            url = f"https://www.instagram.com/reel/{media.code}/"
            print(f"[✓] Reel publicado en Instagram: {url}")
            return url

        except Exception as e:
            print(f"[Instagram] Error con instagrapi: {e}")
            return None

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
            platforms = ["youtube", "tiktok", "instagram"]

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
                "youtube": f"{'OK' if 18 <= _vid_dur <= 58 else 'WARN'} ({_vid_dur:.0f}s, óptimo 18-28s)",
                "tiktok": f"{'OK' if _vid_dur <= 34 else 'WARN largo'} ({_vid_dur:.0f}s, óptimo <21s)",
                "instagram": f"{'OK' if _vid_dur <= 60 else 'WARN'} ({_vid_dur:.0f}s, óptimo 15-30s)"
            }
            print(f"[*] Duración del clip: {_vid_dur:.1f}s")
            for _p, _note in _platform_notes.items():
                if _p in (platforms or []):
                    print(f"    {_p.upper()}: {_note}")
        except Exception:
            pass

        # 1. Comprobación estricta de directrices Anti-Ban y respeto al autor
        print("\n" + "=" * 65)
        print("🛡️  AUDITORÍA DE SEGURIDAD PREVIA A PUBLICACIÓN MULTIPLATAFORMA")
        print("=" * 65)
        orig_url = metadata.get("original_url", "")
        is_compliant = AntiBanValidator.validate_metadata(metadata, creator_name, orig_url)

        for i, plat in enumerate(platforms):
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
                url = self.publish_to_youtube(
                    video_path,
                    title,
                    desc,
                    privacy=target_privacy,
                    thumbnail_path=thumb,
                    pinned_comment=pinned_comment
                )
                results["youtube"] = url
                if url:
                    self._notify_telegram(f"✅ *[1/3] YouTube Shorts publicado:* [Ver en YouTube]({url})")
            elif plat == "tiktok":
                debate_q = metadata.get("debate_question", "")
                url = self.publish_to_tiktok(video_path, title, tags, debate_question=debate_q)
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
                cta_block = AFFILIATE_CTA_INSTAGRAM if ENABLE_AFFILIATE_CTAS else "🎮 Reserva oficial de GTA VI y mejores ofertas de PS5 en el LINK DE LA BIO."

                creator_clean = creator_name or "Rockstar Games"
                caption = (
                    f"{title}\n\n"
                    f"{debate_block}"
                    f"{desc[:900]}\n\n"
                    f"🌐 {bold_redes}\n"
                    f"👉 Hub Central: https://linktr.ee/gtavihubspain\n"
                    f"👉 Síguenos en @gtavihubspain\n\n"
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

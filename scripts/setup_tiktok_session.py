"""
Script de login interactivo para TikTok e Instagram (@gtavihubextra).

Usa Google Chrome real (channel='chrome') cuando está disponible para permitir
el inicio de sesión con Google ('Continue with Google') sin bloqueos de Chromium.
Al detectar cookies activas de @gtavihubextra fuera de /login (o al pulsar Enter),
exporta storage_state.json, convierte Instagram sessionid si aplica (--with-instagram),
actualiza .env y sincroniza con mbp1 (--sync).

Uso:
    cd GTA6Channel/
    .venv/bin/python3 -u scripts/setup_tiktok_session.py --fresh --with-instagram --auto-wait --sync
"""

import os
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles" / "tiktok_user_data"
STORAGE_STATE = BASE_DIR / "assets" / ".browser_profiles" / "storage_state.json"
REMOTE_HOST = os.getenv("GTA_HOST", "gabrieltrujillovallejo@100.108.212.124")
REMOTE_DIR = os.getenv("GTA_REMOTE_DIR", "~/GTAVIHub")
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

FRESH = "--fresh" in sys.argv
SYNC = "--sync" in sys.argv
AUTO_WAIT = "--auto-wait" in sys.argv
WITH_IG = "--with-instagram" in sys.argv

if FRESH:
    shutil.rmtree(PROFILE_DIR, ignore_errors=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if STORAGE_STATE.exists():
        STORAGE_STATE.unlink()
    print("[*] Sesión anterior borrada (--fresh) para iniciar limpio en @gtavihubextra.", flush=True)

for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
    lock_file = PROFILE_DIR / lock
    if lock_file.exists():
        lock_file.unlink()

print("=" * 60, flush=True)
print(" SETUP SESION @gtavihubextra — TikTok" + (" + Instagram" if WITH_IG else ""), flush=True)
print("=" * 60, flush=True)
print(f"\n[*] Perfil: {PROFILE_DIR}", flush=True)
print("[*] Abriendo Google Chrome en modo visible (compatible con Google Sign-In)...", flush=True)

with sync_playwright() as p:
    launch_opts = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        "viewport": {"width": 1280, "height": 800},
        "locale": "es-ES",
        "timezone_id": "Europe/Madrid",
    }
    try:
        context = p.chromium.launch_persistent_context(channel="chrome", **launch_opts)
        print("[✓] Google Chrome nativo abierto.", flush=True)
    except Exception as e_chrome:
        print(f"[!] Chrome nativo no disponible ({e_chrome}); usando Chromium Playwright...", flush=True)
        context = p.chromium.launch_persistent_context(**launch_opts)

    page = context.pages[0] if context.pages else context.new_page()
    try:
        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=25000)
    except Exception as e_tt:
        print(f"[!] Aviso cargando TikTok: {e_tt}", flush=True)

    ig_page = None
    if WITH_IG:
        ig_page = context.new_page()
        try:
            ig_page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=25000)
        except Exception as e_ig:
            print(f"[!] Aviso cargando Instagram: {e_ig}", flush=True)

    print("\nINSTRUCCIONES:", flush=True)
    print("  1. Pestana 1 (TikTok): inicia sesion con @gtavihubextra (Google / usuario)", flush=True)
    if WITH_IG:
        print("  2. Pestana 2 (Instagram): inicia sesion con Google / cuenta @gtavihubextra", flush=True)
    if AUTO_WAIT:
        print("  3. Esperando automaticamente hasta 10 min a que completes ambos logins...\n", flush=True)
        deadline = time.time() + 600
        while time.time() < deadline:
            if not context.pages:
                break
            cur_url = (page.url or "").lower()
            tt_cookies = context.cookies("https://www.tiktok.com")
            has_tt_sid = any(c.get("name") in ("sessionid", "sid_tt", "sessionid_ss") and c.get("value") for c in tt_cookies)
            tt_ok = (
                has_tt_sid
                and cur_url
                and "login" not in cur_url
                and "signup" not in cur_url
                and "accounts.google.com" not in cur_url
            )

            ig_ok = True
            if WITH_IG:
                ig_cookies = context.cookies("https://www.instagram.com")
                ig_uid = next((c.get("value", "") for c in ig_cookies if c.get("name") == "ds_user_id"), "")
                ig_sid = next((c.get("value", "") for c in ig_cookies if c.get("name") == "sessionid"), "")
                ig_url = (ig_page.url or "").lower() if ig_page and not ig_page.is_closed() else ""
                # Rechaza silenciosamente ds_user_id antiguo 80769743562 (@gtavihubspain)
                ig_ok = bool(
                    ig_sid
                    and ig_uid
                    and ig_uid != "80769743562"
                    and "accounts/login" not in ig_url
                    and "accounts.google.com" not in ig_url
                )

            if tt_ok and ig_ok:
                print("[*] Sesion(es) detectadas — esperando estabilizacion (4s)...", flush=True)
                page.wait_for_timeout(4000)
                break

            try:
                ready, _, _ = select.select([sys.stdin], [], [], 0.0)
                if ready:
                    sys.stdin.readline()
                    break
            except Exception:
                pass
            page.wait_for_timeout(1500)
    else:
        print("  3. Vuelve aqui y pulsa ENTER para validar y guardar las cookies\n", flush=True)
        print("  >>> NO CIERRES EL NAVEGADOR — pulsa ENTER aqui cuando termines <<<", flush=True)
        input()

    try:
        page.goto("https://www.tiktok.com/tiktokstudio", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3500)
        studio_txt = (page.inner_text("body") or "").lower()
        if "gtavihubspain" in studio_txt and "gtavihubextra" not in studio_txt:
            print("\n[!] ADVERTENCIA: parece que iniciaste sesion en @gtavihubspain (antigua), no en @gtavihubextra.")
            if AUTO_WAIT:
                print("[!] Guardado abortado automaticamente por proteccion de @gtavihubextra.")
                context.close()
                sys.exit(1)
            confirm = input("¿Guardar igualmente? (escribe 'si' para confirmar, Enter para abortar): ").strip().lower()
            if confirm != "si":
                print("[!] Guardado cancelado para proteger @gtavihubextra.")
                context.close()
                sys.exit(1)
        elif "gtavihubextra" in studio_txt:
            print("\n[✓] Cuenta verificada en TikTok Studio: @gtavihubextra.")
    except Exception:
        pass

    context.storage_state(path=str(STORAGE_STATE))
    print(f"\n[OK] storage_state.json exportado en:\n     {STORAGE_STATE}")

    context.close()

if SYNC:
    print(f"\n→ Sincronizando storage_state.json a {REMOTE_HOST} ...")
    subprocess.run(
        ["scp", "-q", str(STORAGE_STATE), f"{REMOTE_HOST}:{REMOTE_DIR}/assets/.browser_profiles/storage_state.json"],
        check=True,
    )
    print("[✓] storage_state.json sincronizado en mbp1.")

if WITH_IG:
    print("\n→ Convirtiendo cookie web de Instagram a instagrapi_session.json (@gtavihubextra)...")
    ig_cmd = [
        sys.executable,
        "-u",
        str(BASE_DIR / "scripts" / "setup_instagram_session.py"),
        "--user",
        "gtavihubextra",
        "--from-browser-state",
    ]
    if SYNC:
        remote_cmd = (
            f"cd {REMOTE_DIR} && .venv/bin/python3 -u scripts/setup_instagram_session.py "
            "--user gtavihubextra --from-browser-state"
        )
        res = subprocess.run(["ssh", REMOTE_HOST, remote_cmd], check=False)
        if res.returncode == 0:
            subprocess.run(
                ["scp", "-q", f"{REMOTE_HOST}:{REMOTE_DIR}/assets/.browser_profiles/instagrapi_session.json",
                 str(BASE_DIR / "assets" / ".browser_profiles" / "instagrapi_session.json")],
                check=False,
            )
            env_local = BASE_DIR / ".env"
            if env_local.exists():
                lines = env_local.read_text(encoding="utf-8").splitlines()
                out = [
                    "INSTAGRAM_USERNAME=gtavihubextra" if ln.split("=", 1)[0].strip() == "INSTAGRAM_USERNAME" else ln
                    for ln in lines
                ]
                if not any(ln.split("=", 1)[0].strip() == "INSTAGRAM_USERNAME" for ln in lines):
                    out.append("INSTAGRAM_USERNAME=gtavihubextra")
                env_local.write_text("\n".join(out) + "\n", encoding="utf-8")
            print("[✓] Instagram @gtavihubextra configurado en mbp1 y copiado a local.")
        else:
            subprocess.run(ig_cmd, check=False)
    else:
        subprocess.run(ig_cmd, check=False)
elif not SYNC:
    print(
        "\nAhora ejecuta en terminal para sincronizar:\n"
        f"  scp \"assets/.browser_profiles/storage_state.json\" "
        f"{REMOTE_HOST}:{REMOTE_DIR}/assets/.browser_profiles/storage_state.json"
    )

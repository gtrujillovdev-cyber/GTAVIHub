"""
Setup de sesión persistente de X (Twitter) para x_scout.py.

Abre Chrome en modo visible para que inicies sesión manualmente.
Guarda el perfil en assets/.browser_profiles/x_user_data/ y lo sincroniza al Mac remoto.

Uso:
    cd GTA6Channel/
    .venv/bin/python3 scripts/setup_x_session.py [--fresh] [--sync]

Flags:
    --fresh   Borra el perfil anterior antes de autenticar
    --sync    Sincroniza el perfil al Mac remoto tras guardar
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles" / "x_user_data"
REMOTE_HOST = os.getenv("GTA_HOST", "gabrieltrujillovallejo@100.108.212.124")
REMOTE_DIR = os.getenv("GTA_REMOTE_DIR", "~/GTAVIHub")

FRESH = "--fresh" in sys.argv
SYNC = "--sync" in sys.argv

if FRESH:
    shutil.rmtree(PROFILE_DIR, ignore_errors=True)
    print("[*] Perfil anterior borrado (--fresh).")

PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Limpiar locks residuales de Chrome
for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
    lf = PROFILE_DIR / lock
    if lf.exists():
        lf.unlink()

print("=" * 55)
print(" SETUP SESION X (Twitter) — Scout GTA6")
print("=" * 55)
print(f"\n[*] Perfil: {PROFILE_DIR}")
print("[*] Abriendo Chrome visible para login en X...\n")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[ERROR] playwright no instalado. Ejecuta: pip install playwright && playwright install chromium")
    sys.exit(1)

with sync_playwright() as p:
    launch_opts = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
        "viewport": {"width": 1280, "height": 800},
        "locale": "es-ES",
        "timezone_id": "Europe/Madrid",
    }

    try:
        context = p.chromium.launch_persistent_context(channel="chrome", **launch_opts)
        print("[OK] Google Chrome nativo abierto.")
    except Exception:
        context = p.chromium.launch_persistent_context(**launch_opts)
        print("[OK] Chromium abierto.")

    page = context.pages[0] if context.pages else context.new_page()

    try:
        page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=25000)
    except Exception as e:
        print(f"[!] Aviso cargando X: {e}")

    print("\nINSTRUCCIONES:")
    print("  1. Inicia sesión en X en la ventana de Chrome que se ha abierto")
    print("  2. Esperando detección automática de sesión (hasta 10 minutos)...")
    print("  (También puedes pulsar ENTER en esta terminal cuando estés dentro del feed)\n")

    import select
    start_wait = time.time() if "time" in dir() else 0
    import time
    start_wait = time.time()

    logged_in = False
    while time.time() - start_wait < 600:
        # 1. Comprobar si el usuario pulsó ENTER
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.readline()
            logged_in = True
            break

        # 2. Comprobar si la URL o cookies ya indican login completado
        try:
            cur_url = page.url.lower()
            if "home" in cur_url or "explore" in cur_url or "notifications" in cur_url:
                logged_in = True
                print("\n[✓] ¡Navegación al Feed de X detectada!")
                break
            # Detección por cookies de sesión de X ('auth_token' o 'twid')
            cookies = context.cookies()
            auth_cookies = [c for c in cookies if c.get("name") in ["auth_token", "twid"]]
            if auth_cookies:
                logged_in = True
                print(f"\n[✓] ¡Cookie de autenticación '{auth_cookies[0]['name']}' detectada con éxito!")
                break
        except Exception:
            pass

        time.sleep(2)

    if not logged_in:
        cur_url = page.url.lower()
        if "login" in cur_url or "signin" in cur_url:
            print("[!] No parece que el login se haya completado. Revisa el navegador.")
            context.close()
            sys.exit(1)

    print(f"\n[OK] Sesión de X guardada en: {PROFILE_DIR}")
    storage_state_file = BASE_DIR / "assets" / ".browser_profiles" / "x_storage_state.json"
    try:
        context.storage_state(path=str(storage_state_file))
        print(f"[OK] Storage state exportado en: {storage_state_file}")
    except Exception as e:
        print(f"[!] Aviso exportando storage_state: {e}")
    context.close()

if SYNC:
    print(f"\n[*] Sincronizando perfil X al Mac remoto ({REMOTE_HOST})...")
    try:
        subprocess.run(
            [
                "rsync", "-avz", "--delete",
                str(PROFILE_DIR) + "/",
                f"{REMOTE_HOST}:{REMOTE_DIR}/assets/.browser_profiles/x_user_data/",
            ],
            check=True,
        )
        print("[OK] Perfil X sincronizado al Mac remoto.")
    except subprocess.CalledProcessError as e:
        print(f"[!] Error sincronizando: {e}")
        sys.exit(1)
else:
    print(f"\nPara sincronizar al remoto manualmente:")
    print(f"  rsync -avz {PROFILE_DIR}/ {REMOTE_HOST}:{REMOTE_DIR}/assets/.browser_profiles/x_user_data/")

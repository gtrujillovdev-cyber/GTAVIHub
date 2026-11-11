"""
Script de login interactivo para TikTok e Instagram.

Abre Chromium en modo VISIBLE. El usuario inicia sesion manualmente.
Cuando pulsa Enter en terminal, el script exporta storage_state.json
(formato portátil, sin cifrado de Keychain) ANTES de cerrar el navegador.

Uso:
    cd GTA6Channel/
    .venv/bin/python3 scripts/setup_tiktok_session.py
"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "assets" / ".browser_profiles" / "tiktok_user_data"
STORAGE_STATE = BASE_DIR / "assets" / ".browser_profiles" / "storage_state.json"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

FRESH = "--fresh" in sys.argv
if FRESH:
    import shutil
    shutil.rmtree(PROFILE_DIR, ignore_errors=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if STORAGE_STATE.exists():
        STORAGE_STATE.unlink()
    print("[*] Sesión anterior borrada (--fresh) para iniciar limpio en @gtavihubextra.")

# Eliminar locks de sesiones anteriores
for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
    lock_file = PROFILE_DIR / lock
    if lock_file.exists():
        lock_file.unlink()

print("=" * 60)
print(" SETUP DE SESION TIKTOK — GTA VI Hub (@gtavihubextra)")
print("=" * 60)
print(f"\n[*] Perfil: {PROFILE_DIR}")
print("[*] Abriendo Chromium en modo visible...\n")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        viewport={"width": 1280, "height": 800},
        locale="es-ES",
        timezone_id="Europe/Madrid",
    )

    page = context.new_page()
    page.goto("https://www.tiktok.com/login")

    print("INSTRUCCIONES:")
    print("  1. Inicia sesion en TikTok con la cuenta limpia (@gtavihubextra)")
    print("  2. Comprueba que aparece el panel de @gtavihubextra (NO @gtavihubspain)")
    print("  3. Vuelve aqui y pulsa ENTER para guardar las cookies\n")
    print("  >>> NO CIERRES EL NAVEGADOR — pulsa ENTER aqui cuando termines <<<")

    input()  # Espera Enter con el navegador aún abierto

    # Exportar cookies ANTES de cerrar (contexto aún activo)
    context.storage_state(path=str(STORAGE_STATE))
    print(f"\n[OK] storage_state.json exportado en:\n     {STORAGE_STATE}")

    context.close()

print("\nAhora ejecuta en terminal para sincronizar:")
print(
    "  rsync -avz "
    "\"assets/.browser_profiles/storage_state.json\" "
    "gabrieltrujillovallejo@100.108.212.124:"
    "~/GTAVIHub/assets/.browser_profiles/storage_state.json"
)

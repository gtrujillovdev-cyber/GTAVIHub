"""
Actualiza el perfil de Instagram (@gtavihubspain) via instagrapi:
  - Bio / descripcion
  - Foto de perfil (avatar)

Requiere sesion activa en assets/.browser_profiles/instagrapi_session.json.
Si no existe, ejecuta primero: scripts/setup_instagram_session.py

Uso:
    cd GTA6Channel/
    .venv/bin/python3 scripts/setup_instagram_branding.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SESSION_FILE = BASE_DIR / "assets" / ".browser_profiles" / "instagrapi_session.json"
AVATAR_FILE = BASE_DIR / "assets" / "avatar.jpg"

USERNAME = os.getenv("INSTAGRAM_USERNAME", "gtavihubspain")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")

INSTAGRAM_BIO = (
    "GTA VI Hub Espana\n"
    "Filtraciones, clips y reacciones en espanol\n"
    "YouTube & TikTok: @GTAVIHubSpain\n"
    "#GTA6 #GrandTheftAutoVI"
)


def get_client():
    from instagrapi import Client

    cl = Client()
    cl.delay_range = [2, 5]

    if not SESSION_FILE.exists():
        print(f"[!] No existe sesion en {SESSION_FILE}")
        print("    Ejecuta primero: .venv/bin/python3 scripts/setup_instagram_session.py")
        sys.exit(1)

    try:
        cl.load_settings(str(SESSION_FILE))
        cl.login(USERNAME, PASSWORD)
        print("[*] Sesion de Instagram restaurada.")
    except Exception as e:
        print(f"[!] Error restaurando sesion: {e}")
        print("[*] Intentando login completo...")
        cl = Client()
        cl.delay_range = [2, 5]
        if not PASSWORD:
            raise RuntimeError("Falta INSTAGRAM_PASSWORD en .env")
        cl.login(USERNAME, PASSWORD)

    cl.dump_settings(str(SESSION_FILE))
    return cl


def update_bio(cl):
    print(f"[*] Actualizando bio de @{USERNAME}...")
    try:
        cl.account_edit(biography=INSTAGRAM_BIO)
        print("[OK] Bio actualizada.")
    except Exception as e:
        print(f"[!] Error actualizando bio: {e}")


def update_avatar(cl):
    if not AVATAR_FILE.exists():
        print(f"[!] No se encontro el avatar: {AVATAR_FILE}")
        return
    print(f"[*] Subiendo foto de perfil ({AVATAR_FILE.name})...")
    try:
        cl.account_change_picture(str(AVATAR_FILE))
        print("[OK] Foto de perfil actualizada.")
    except Exception as e:
        print(f"[!] Error actualizando foto de perfil: {e}")


def main():
    print("=" * 60)
    print(" SETUP BRANDING INSTAGRAM — GTA VI Hub Espana")
    print("=" * 60)

    try:
        cl = get_client()
        update_bio(cl)
        update_avatar(cl)
        print("\n[OK] Perfil de Instagram actualizado.")
    except ImportError:
        print("[ERROR] instagrapi no instalado. Ejecuta: pip install instagrapi")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

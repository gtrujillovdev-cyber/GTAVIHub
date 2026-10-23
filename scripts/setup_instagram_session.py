"""
Login interactivo de Instagram con instagrapi.
Resuelve el challenge 2FA y guarda la sesión en disco para
que el Mac remoto no necesite volver a autenticarse.

Uso:
    cd GTA6Channel/
    .venv/bin/python3 scripts/setup_instagram_session.py
"""

import os, sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SESSION_FILE = BASE_DIR / "assets" / ".browser_profiles" / "instagrapi_session.json"
SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

USERNAME = os.getenv("INSTAGRAM_USERNAME", "gtavihubspain")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")

if not PASSWORD:
    PASSWORD = input("Contraseña de Instagram: ").strip()

print(f"\n[*] Iniciando sesión como @{USERNAME}...")

try:
    from instagrapi import Client
    from instagrapi.exceptions import ChallengeRequired

    cl = Client()
    cl.delay_range = [2, 5]

    def challenge_handler(username: str, choice: int = 0) -> str:
        print(f"\n[!] Instagram ha enviado un código de verificación.")
        print(f"    Revisa el email o SMS asociado a @{username}")
        return input("    Introduce el código de 6 dígitos: ").strip()

    cl.challenge_code_handler = challenge_handler

    try:
        cl.login(USERNAME, PASSWORD)
    except Exception as e:
        err = str(e)
        # Error 572 = timeline fetch falla tras login exitoso — sesión válida igualmente
        if any(x in err for x in ["572", "timeline", "feed"]):
            print(f"[!] Advertencia post-login (ignorada): {err[:80]}")
        else:
            raise

    cl.dump_settings(str(SESSION_FILE))
    print(f"\n[OK] Sesión guardada en:\n     {SESSION_FILE}")
    print("\nAhora sincroniza al Mac remoto:")
    print(
        f"  rsync -avz assets/.browser_profiles/instagrapi_session.json "
        f"gabrieltrujillovallejo@100.108.212.124:"
        f"~/GTAVIHub/assets/.browser_profiles/instagrapi_session.json"
    )

except Exception as e:
    print(f"\n[ERROR] {e}")
    sys.exit(1)

#!/usr/bin/env python3
"""
scripts/archive_instagram_posts.py — Archiva todos los Reels/Posts de la cuenta de Instagram
antigua para congelar el historial algorítmico y empezar limpio.
"""

import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import dotenv_values
from instagrapi import Client

SESSION_FILE = BASE_DIR / "assets" / ".browser_profiles" / "instagrapi_session.json"
ENV_FILE = BASE_DIR / ".env"

def archive_all_instagram_posts():
    env_vars = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    ig_user = os.getenv("INSTAGRAM_USERNAME") or env_vars.get("INSTAGRAM_USERNAME")
    ig_pass = os.getenv("INSTAGRAM_PASSWORD") or env_vars.get("INSTAGRAM_PASSWORD")

    cl = Client()
    cl.delay_range = [2, 4]

    logged_in = False
    if SESSION_FILE.exists():
        try:
            print("[*] Intentando conectar con sesión guardada en instagrapi_session.json...")
            cl.load_settings(str(SESSION_FILE))
            if ig_user and ig_pass:
                cl.login(ig_user, ig_pass)
            logged_in = True
            print("[✓] Conectado a Instagram.")
        except Exception as e:
            print(f"[*] Sesión expirada o no válida ({e}).")

    if not logged_in:
        if not ig_user or not ig_pass:
            print("[!] Error: No hay credenciales de Instagram en .env (INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD).")
            return
        print(f"[*] Iniciando sesión para @{ig_user}...")
        cl.login(ig_user, ig_pass)
        cl.dump_settings(str(SESSION_FILE))
        print("[✓] Login exitoso.")

    # Obtener el usuario autenticado
    try:
        user_info = cl.account_info()
        print(f"[*] Cuenta autenticada: @{user_info.username} (ID: {user_info.pk})")
        
        # Obtener publicaciones (medias)
        medias = cl.user_medias(user_info.pk, amount=50)
        print(f"[*] Total de publicaciones/Reels detectados: {len(medias)}")
        
        if not medias:
            print("[✓] No hay publicaciones activas en la cuenta.")
            return

        archived_count = 0
        for m in medias:
            try:
                # cl.media_archive archiva el post o reel
                print(f"  • Archivando: {m.pk} (Código: {m.code})...")
                res = cl.media_archive(m.id)
                if res:
                    archived_count += 1
                    print(f"    ✓ [Archivado]")
            except Exception as e:
                print(f"    [!] Error archivando {m.id}: {e}")

        print(f"\n[✓] Operación completada: {archived_count} de {len(medias)} publicaciones archivadas con éxito.")
    except Exception as e:
        print(f"[!] Error consultando posts: {e}")

if __name__ == "__main__":
    archive_all_instagram_posts()

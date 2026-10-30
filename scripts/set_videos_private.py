#!/usr/bin/env python3
import sys
import os
import json
import requests
from pathlib import Path

os.environ["NO_GCE_CHECK"] = "True"
os.environ["GCE_METADATA_HOST"] = "disabled"

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"
TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube"
]

TARGET_VIDEOS = [
    ("0gKWC0a-9NA", "GTA Online - Biohazard Outbreak"),
    ("VZ_o_cAnmuc", "¿Casas de GTA 6 ya en GTA Online?!"),
    ("zKU4k9E7QNs", "Encontraron casas de GTA 6 en GTA Online"),
    ("_0RV5NCQveo", "La bestia está en GTA 6 en GTA Online"),
    ("HcEAD7gR0mA", "¿Adiós a GTA 6 en PS5?")
]

def get_valid_token():
    creds = None
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                t_data = json.load(f)
            stored_scopes = t_data.get("scopes", [])
            has_manage_scope = any(
                "auth/youtube" in s and not s.endswith(".readonly") and not s.endswith(".upload")
                for s in stored_scopes
            )
            if has_manage_scope:
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            else:
                print("[*] El token actual no tiene el permiso 'auth/youtube'. Se requiere autorizar en navegador...", flush=True)
                creds = None
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("[*] Generando enlace de autorización de Google...", flush=True)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), scopes=SCOPES)
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
            print("\n" + "=" * 70, flush=True)
            print("🔑 ABRE ESTE ENLACE EN TU NAVEGADOR PARA AUTORIZAR (1 CLICK):", flush=True)
            print(auth_url, flush=True)
            print("=" * 70 + "\n", flush=True)
            try:
                import subprocess
                subprocess.run(["open", auth_url], check=False)
            except Exception:
                pass
            creds = flow.run_local_server(port=8080, prompt='consent', open_browser=False)

        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"[✓] Token guardado en {TOKEN_FILE.name}", flush=True)

        # Sincronizar hacia el MacBook Pro
        try:
            import subprocess
            subprocess.run(["scp", str(TOKEN_FILE), "gabrieltrujillovallejo@100.108.212.124:~/GTAVIHub/token.json"], check=False)
            print("[✓] Token sincronizado con el MacBook Pro de producción.", flush=True)
        except Exception:
            pass

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds.token

def main():
    print("=" * 65)
    print("🔒 GESTOR DE PRIVACIDAD DE YOUTUBE (VIA REST API DIRECTA)")
    print("=" * 65)

    token = get_valid_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    success_count = 0
    for vid_id, desc in TARGET_VIDEOS:
        print(f"\n[*] Procesando: {vid_id} ({desc})...")
        # 1. Obtener snippet y status
        get_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet,status&id={vid_id}"
        r_get = requests.get(get_url, headers=headers)
        if r_get.status_code != 200:
            print(f"  [!] Error consultando vídeo: {r_get.status_code} {r_get.text}")
            continue

        items = r_get.json().get("items", [])
        if not items:
            print(f"  [!] Vídeo {vid_id} no encontrado en el canal.")
            continue

        snippet = items[0]["snippet"]
        status = items[0]["status"]

        if status.get("privacyStatus") == "private":
            print(f"  [✓] Ya estaba en PRIVADO.")
            success_count += 1
            continue

        status["privacyStatus"] = "private"

        put_body = {
            "id": vid_id,
            "snippet": {
                "title": snippet.get("title"),
                "description": snippet.get("description", ""),
                "categoryId": snippet.get("categoryId", "20")
            },
            "status": status
        }

        put_url = "https://youtube.googleapis.com/youtube/v3/videos?part=snippet,status"
        r_put = requests.put(put_url, headers=headers, json=put_body)
        if r_put.status_code == 200:
            new_status = r_put.json().get("status", {}).get("privacyStatus")
            print(f"  [✓✓] ¡Estado cambiado con éxito a {new_status.upper()}!")
            success_count += 1
        else:
            print(f"  [!] Error actualizando estado: {r_put.status_code} {r_put.text}")

    print("\n" + "=" * 65)
    print(f"🎉 COMPLETADO: {success_count}/{len(TARGET_VIDEOS)} vídeos pasados a PRIVADO.")
    print("=" * 65)

if __name__ == "__main__":
    main()

"""
Configura el branding visual del canal de YouTube:
  - Sube el banner (assets/banner.jpg)
  - Actualiza la descripcion del canal

NOTA: El avatar de YouTube NO se puede cambiar via API — hay que hacerlo desde
      Google Account > Cambiar foto de perfil (usa assets/avatar.jpg).

Uso:
    cd GTA6Channel/
    .venv/bin/python3 scripts/setup_youtube_branding.py
"""

import sys
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"
# Token separado para no invalidar el token de upload
BRANDING_TOKEN_FILE = BASE_DIR / "branding_token.json"
BANNER_FILE = BASE_DIR / "assets" / "banner.jpg"

# Scope completo necesario para channelBanners.insert y channels.update
SCOPES = ["https://www.googleapis.com/auth/youtube"]

CHANNEL_DESCRIPTION = """\
GTA VI Hub Espana - El canal en espanol dedicado a Grand Theft Auto VI.

Publicamos cada dia los mejores clips, filtraciones, reacciones y novedades de GTA 6 comentadas en espanol.

Lo que encontraras aqui:
  Filtraciones y rumores verificados de Rockstar Games
  Gameplay, trailers y escenas ineditas comentadas en espanol
  Reacciones de la comunidad gaming hispanohablante
  Los mejores clips cortos en formato Short para no perderte nada

Activa la campanita para recibir cada nuevo clip al instante.
Siguenos tambien como @GTAVIHubSpain en TikTok e Instagram.

---
Canal de caracter informativo y editorial. El material original pertenece a sus respectivos autores.
Uso conforme a la doctrina Fair Use / Art. 107 Copyright Act.
"""


def get_youtube_service():
    creds = None
    if BRANDING_TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(BRANDING_TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[*] Renovando token de branding...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_FILE.exists():
                print(f"[ERROR] Falta {CLIENT_SECRETS_FILE.name}")
                sys.exit(1)
            print("[*] Iniciando autorizacion OAuth (scope youtube completo)...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
            try:
                creds = flow.run_local_server(port=8081, prompt="consent")
            except Exception:
                creds = flow.run_console()

        with open(BRANDING_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"[OK] Token guardado en {BRANDING_TOKEN_FILE.name}")

    return build("youtube", "v3", credentials=creds)


def get_my_channel_id(youtube):
    resp = youtube.channels().list(mine=True, part="id,snippet").execute()
    items = resp.get("items", [])
    if not items:
        print("[ERROR] No se encontro un canal asociado a esta cuenta.")
        sys.exit(1)
    ch = items[0]
    print(f"[*] Canal: {ch['snippet']['title']} (ID: {ch['id']})")
    return ch["id"]


def upload_banner_and_description(youtube, channel_id):
    banner_url = None

    if BANNER_FILE.exists():
        print(f"[*] Subiendo banner ({BANNER_FILE.name})...")
        try:
            media = MediaFileUpload(str(BANNER_FILE), mimetype="image/jpeg", resumable=True)
            resp = youtube.channelBanners().insert(body={}, media_body=media).execute()
            banner_url = resp.get("url", "")
            print(f"[OK] Banner subido: {banner_url}")
        except Exception as e:
            print(f"[!] Error subiendo banner: {e}")
    else:
        print(f"[!] No se encontro el banner: {BANNER_FILE}")

    # La descripcion va en brandingSettings.channel (snippet es readonly en channels.update)
    branding_channel = {
        "description": CHANNEL_DESCRIPTION,
        "country": "ES",
        "keywords": "GTA6 GTA VI GrandTheftAutoVI Rockstar Gaming Videojuegos Espana Shorts"
    }

    branding_image = {}
    if banner_url:
        branding_image["bannerExternalUrl"] = banner_url

    body = {
        "id": channel_id,
        "brandingSettings": {
            "channel": branding_channel
        }
    }
    if branding_image:
        body["brandingSettings"]["image"] = branding_image

    print("[*] Actualizando descripcion y banner del canal...")
    try:
        youtube.channels().update(part="brandingSettings", body=body).execute()
        print("[OK] Descripcion y banner actualizados.")
    except Exception as e:
        print(f"[!] Error actualizando canal: {e}")


def main():
    print("=" * 60)
    print(" SETUP BRANDING YOUTUBE — GTA VI Hub Espana")
    print("=" * 60)

    youtube = get_youtube_service()
    channel_id = get_my_channel_id(youtube)

    upload_banner_and_description(youtube, channel_id)

    print("\n" + "=" * 60)
    print("[IMPORTANTE] El avatar (foto de perfil) NO se puede")
    print("  cambiar via API de YouTube. Hazlo manualmente:")
    print("  1. Ve a studio.youtube.com")
    print("  2. Personalizar canal > Imagen de perfil")
    print(f"  3. Sube: {BASE_DIR / 'assets' / 'avatar.jpg'}")
    print("=" * 60)


if __name__ == "__main__":
    main()

import os
import sys
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

# Si el script está en scripts/, el root del proyecto es el padre del directorio scripts
BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "scripts" else Path(__file__).resolve().parent
CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"
TOKEN_FILE = BASE_DIR / "token.json"

def authenticate_youtube():
    print("=" * 60)
    print("🔐 AUTENTICACIÓN DE YOUTUBE PARA GTA6CHANNEL")
    print("=" * 60)

    if not CLIENT_SECRETS_FILE.exists():
        # Comprobar automáticamente si está en la carpeta Downloads
        downloads_dir = Path.home() / "Downloads"
        candidates = list(downloads_dir.glob("*client_secret*.json")) + list(downloads_dir.glob("client_secret*.json"))
        if candidates:
            # Seleccionar el más reciente
            latest_file = max(candidates, key=os.path.getctime)
            import shutil
            shutil.copyfile(latest_file, CLIENT_SECRETS_FILE)
            print(f"[✓] Archivo de credenciales detectado y copiado automáticamente desde Downloads:")
            print(f"    {latest_file.name} -> client_secrets.json")
        else:
            print(f"\n[!] Falta el archivo: {CLIENT_SECRETS_FILE.name}")
            print("\nPara obtener este archivo:")
            print("1. Ve a Google Cloud Console (https://console.cloud.google.com/)")
            print("2. Activa la 'YouTube Data API v3'")
            print("3. En 'Credenciales', crea un 'ID de cliente de OAuth' de tipo 'Aplicación de escritorio' (Desktop App)")
            print("4. Descarga el JSON (se guardará en Descargas y lo detectaremos solo).\n")
            sys.exit(1)

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[*] Renovando token existente...")
            creds.refresh(Request())
        else:
            print("[*] Iniciando nuevo flujo de autorización...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_FILE),
                scopes=SCOPES
            )
            # Intentar abrir el navegador local en macOS
            try:
                creds = flow.run_local_server(port=8080, prompt='consent')
            except Exception as e:
                print(f"[!] Error con servidor local: {e}. Intentando modo consola...")
                creds = flow.run_console()

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
        print(f"[✓] Token guardado con éxito en {TOKEN_FILE.name}")

    # Verificar canal conectado
    youtube = build("youtube", "v3", credentials=creds)
    channels_response = youtube.channels().list(
        mine=True,
        part="snippet,statistics"
    ).execute()

    items = channels_response.get("items", [])
    if items:
        ch = items[0]
        title = ch["snippet"]["title"]
        subs = ch["statistics"].get("subscriberCount", "Oculto")
        vids = ch["statistics"].get("videoCount", "0")
        print("\n" + "=" * 60)
        print(f"🎉 ¡CANAL CONECTADO CON ÉXITO!")
        print(f"  • Canal: {title}")
        print(f"  • Suscriptores: {subs}")
        print(f"  • Vídeos actuales: {vids}")
        print("=" * 60 + "\n")
    else:
        print("[!] Conexión establecida pero no se encontró un canal de YouTube asociado a esta cuenta.")

if __name__ == "__main__":
    authenticate_youtube()

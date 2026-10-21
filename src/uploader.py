import os
import sys
from pathlib import Path
from typing import Optional, Dict, List
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import BASE_DIR

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

TOKEN_FILE = BASE_DIR / "token.json"

def get_authenticated_youtube_service():
    """Obtiene el cliente autenticado de YouTube usando token.json."""
    if not TOKEN_FILE.exists():
        print(f"[!] No se encontró {TOKEN_FILE.name}. Ejecuta primero: python3 auth_youtube.py")
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[!] Error cargando credenciales de YouTube: {e}")
        return None

def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
    privacy_status: str = "private",
    is_short: bool = False,
    thumbnail_path: Optional[Path] = None
) -> Optional[str]:
    """
    Sube un vídeo a YouTube mediante la API v3.
    Retorna el ID del vídeo subido o None si falla.
    """
    youtube = get_authenticated_youtube_service()
    if not youtube:
        return None

    if not video_path.exists():
        print(f"[!] Archivo de vídeo no encontrado: {video_path}")
        return None

    if tags is None:
        tags = [
            "GTA 6", "Grand Theft Auto VI", "Rockstar Games",
            "GTA VI", "Vice City", "GTA 6 español", "Gaming", "Videojuegos"
        ]
        if is_short:
            tags.extend(["Shorts", "GTAShorts"])

    body = {
        "snippet": {
            "title": title[:100],  # YouTube limita títulos a 100 caracteres
            "description": description[:5000],
            "tags": tags,
            "categoryId": "20"  # Categoría 20 = Gaming
        },
        "status": {
            "privacyStatus": privacy_status,  # "private", "public", o "unlisted"
            "selfDeclaredMadeForKids": False
        }
    }

    print(f"[*] Subiendo '{video_path.name}' a YouTube ({privacy_status.upper()})...")
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024*1024*4  # 4MB chunks para estabilidad
    )

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"  -> Progreso de subida: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        yt_url = f"https://youtu.be/{video_id}"
        print(f"[✓✓] ¡VÍDEO SUBIDO A YOUTUBE CON ÉXITO!")
        print(f"    ID: {video_id}")
        print(f"    Enlace: {yt_url}")

        if thumbnail_path and thumbnail_path.exists():
            try:
                print(f"[*] Subiendo miniatura personalizada para {video_id}...")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
                ).execute()
                print(f"[✓] Miniatura asignada con éxito.")
            except Exception as e:
                print(f"[Info] Miniatura personalizada no asignada (requiere verificación telefónica del canal): {e}")

        return video_id
    except Exception as e:
        print(f"[!] Error subiendo a YouTube: {e}")
        return None

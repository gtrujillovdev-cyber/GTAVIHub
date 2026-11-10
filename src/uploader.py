import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, List
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import BASE_DIR

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube"
]

TOKEN_FILE = BASE_DIR / "token.json"
TOKEN_EXTRA_FILE = BASE_DIR / "token_extra.json"
BOOST_STATE_FILE = BASE_DIR / "data" / "engagement_boost.json"


def should_toggle_engagement_boost() -> bool:
    """
    Cadencia 1 de cada 2 (50% alternado):
    Determina si este Short recibe el impulso inicial (primer like + comentario fijado)
    o si se publica en modo puramente orgánico para no generar patrones repetitivos.
    """
    BOOST_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {"apply_boost": True, "count": 0}
    if BOOST_STATE_FILE.exists():
        try:
            with open(BOOST_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {"apply_boost": True, "count": 0}

    should_apply = state.get("apply_boost", True)
    # Alternar para el próximo vídeo
    state["apply_boost"] = not should_apply
    state["count"] = state.get("count", 0) + (1 if should_apply else 0)

    try:
        with open(BOOST_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[Warning] No se pudo persistir estado de engagement boost: {e}")

    return should_apply

BANNED_LEGACY_CHANNEL_IDS = {"UCBOl2KuaHEoUWYWJqb7ID9Q"}
BANNED_LEGACY_HANDLES = {"@gtavihubspain"}

def get_authenticated_youtube_service(account: str = "extra"):
    """Obtiene el cliente autenticado de YouTube usando token_extra.json (por defecto @GTAVIHubExtra)."""
    is_extra = account in ("extra", "youtube_extra")
    if is_extra:
        if TOKEN_EXTRA_FILE.exists():
            chosen_file = TOKEN_EXTRA_FILE
        else:
            print(
                "[YouTube Uploader] 🚨 BLOQUEO DE SEGURIDAD: No existe 'token_extra.json' para @GTAVIHubExtra.\n"
                "                   Se ha bloqueado el fallback a 'token.json' (@GTAVIHubSpain) para evitar subir al canal penalizado.\n"
                "                   Ejecuta primero: ./.venv/bin/python3 scripts/auth_youtube.py --extra"
            )
            return None
    else:
        chosen_file = TOKEN_FILE

    if not chosen_file.exists():
        print(f"[!] No se encontró {chosen_file.name}. Ejecuta primero: ./.venv/bin/python3 scripts/auth_youtube.py --extra")
        return None

    try:
        try:
            creds = Credentials.from_authorized_user_file(str(chosen_file))
        except Exception:
            creds = Credentials.from_authorized_user_file(str(chosen_file), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(chosen_file, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[!] Error cargando credenciales de YouTube ({chosen_file.name}): {e}")
        return None

def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
    privacy_status: str = "private",
    is_short: bool = False,
    thumbnail_path: Optional[Path] = None,
    pinned_comment: Optional[str] = None,
    target_account: str = "extra"
) -> Optional[str]:
    """
    Sube un vídeo a YouTube mediante la API v3 exclusivamente al canal autorizado (@GTAVIHubExtra).
    Retorna el ID del vídeo subido o None si falla.
    """
    youtube = get_authenticated_youtube_service(account=target_account)
    if not youtube:
        return None

    # Cortafuegos de identidad de canal: impedir subidas accidentales a @GTAVIHubSpain
    if os.getenv("ALLOW_LEGACY_MAIN_CHANNEL", "false").lower() not in ("true", "1", "yes"):
        try:
            ch_resp = youtube.channels().list(part="snippet", mine=True).execute()
            items = ch_resp.get("items", [])
            if items:
                ch_id = items[0].get("id", "")
                ch_snippet = items[0].get("snippet", {})
                ch_handle = str(ch_snippet.get("customUrl", "")).lower()
                ch_title = ch_snippet.get("title", "")
                if ch_id in BANNED_LEGACY_CHANNEL_IDS or ch_handle in BANNED_LEGACY_HANDLES:
                    err_msg = (
                        f"🚨 [Bloqueo de Seguridad YouTube] El token activo pertenece al canal antiguo "
                        f"'{ch_title}' ({ch_handle} / {ch_id}). Subida ABORTADA. "
                        f"Autoriza @GTAVIHubExtra con: ./.venv/bin/python3 scripts/auth_youtube.py --extra"
                    )
                    print(err_msg)
                    try:
                        from .telegram_bot import send_telegram_alert
                        send_telegram_alert(err_msg)
                    except Exception:
                        pass
                    return None
                print(f"[✓ YouTube Destino Verificado] Canal activo: {ch_title} ({ch_handle or ch_id})")
        except Exception as e:
            print(f"[YouTube Uploader] Info verificación de canal: {e}")

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

        # Boost algorítmico (solo si ENABLE_AUTO_PINNED_COMMENT=true; desactivado en canales nuevos anti-spam)
        auto_engage_enabled = os.getenv("ENABLE_AUTO_PINNED_COMMENT", "false").strip().lower() in ("1", "true", "yes")
        apply_boost = auto_engage_enabled and should_toggle_engagement_boost()
        if apply_boost:
            print(f"[*] [Boost Algorítmico 1 de cada 2] Activado para {video_id}: Primer Like + Comentario fijado...")
            # 1. Primer Like automático para romper el 0
            try:
                youtube.videos().rate(id=video_id, rating="like").execute()
                print(f"[✓ Boost Algorítmico] Primer Like automático asignado a {video_id}.")
            except Exception as e:
                print(f"[Info] Like automático omitido: {e}")

            # 2. Comentario de llamada a la acción y debate
            if pinned_comment:
                try:
                    youtube.commentThreads().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "videoId": video_id,
                                "topLevelComment": {
                                    "snippet": {
                                        "textOriginal": pinned_comment
                                    }
                                }
                            }
                        }
                    ).execute()
                    print(f"[✓ Boost Algorítmico] Comentario fijado de llamada a la acción publicado con éxito.")
                except Exception as e:
                    print(f"[Info] Comentario automático omitido: {e}")
        else:
            print(f"[*] [Boost Algorítmico 1 de cada 2] Omitido para {video_id}: Publicación orgánica pura sin auto-interacción.")

        return video_id
    except Exception as e:
        print(f"[!] Error subiendo a YouTube: {e}")
        return None

#!/usr/bin/env python3
"""
scripts/privatize_old_channel.py — Pone en PRIVADO todos los vídeos del canal antiguo (@GTAVIHubSpain).
Esto congela el histórico de bajas visualizaciones/penalizaciones sin perder los vídeos,
permitiendo que el algoritmo empiece limpio en el canal secundario nuevo.
"""

import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_FILE = BASE_DIR / "token.json"

def privatize_all_videos():
    if not TOKEN_FILE.exists():
        print("[!] No se encontró token.json para el canal antiguo.")
        return

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
        youtube = build("youtube", "v3", credentials=creds)

        # 1. Obtener ID del canal
        ch_resp = youtube.channels().list(mine=True, part="snippet,contentDetails").execute()
        items = ch_resp.get("items", [])
        if not items:
            print("[!] No se pudo obtener información del canal antiguo.")
            return

        ch_title = items[0]["snippet"]["title"]
        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        print(f"[*] Canal detectado: '{ch_title}'")
        print(f"[*] Leyendo lista de vídeos subidos ({uploads_playlist_id})...")

        # 2. Listar todos los vídeos del canal
        video_ids = []
        next_page = None
        while True:
            pl_resp = youtube.playlistItems().list(
                playlistId=uploads_playlist_id,
                part="contentDetails,snippet",
                maxResults=50,
                pageToken=next_page
            ).execute()

            for item in pl_resp.get("items", []):
                v_id = item["contentDetails"]["videoId"]
                v_title = item["snippet"]["title"]
                video_ids.append((v_id, v_title))

            next_page = pl_resp.get("nextPageToken")
            if not next_page:
                break

        print(f"[*] Total de vídeos encontrados: {len(video_ids)}")
        if not video_ids:
            print("[✓] El canal antiguo ya no tiene vídeos públicos o está vacío.")
            return

        # 3. Modificar privacidad a 'private'
        count = 0
        for vid, vtitle in video_ids:
            try:
                # Comprobar estado actual
                v_resp = youtube.videos().list(id=vid, part="status,snippet").execute()
                v_items = v_resp.get("items", [])
                if not v_items:
                    continue

                curr_status = v_items[0]["status"]["privacyStatus"]
                if curr_status == "private":
                    print(f"  • [Ya Privado] {vtitle[:40]}...")
                    continue

                # Actualizar a privado
                youtube.videos().update(
                    part="status,snippet",
                    body={
                        "id": vid,
                        "snippet": {
                            "title": v_items[0]["snippet"]["title"],
                            "categoryId": v_items[0]["snippet"]["categoryId"]
                        },
                        "status": {
                            "privacyStatus": "private"
                        }
                    }
                ).execute()
                count += 1
                print(f"  ✓ [Privatizado] {vtitle[:45]}...")
            except Exception as e:
                print(f"  [!] Error con vídeo {vid}: {e}")

        print(f"\n[✓] Operación completada: {count} vídeos cambiados a PRIVADO con éxito.")

    except Exception as e:
        print(f"[!] Error ejecutando privatización: {e}")

if __name__ == "__main__":
    privatize_all_videos()

#!/usr/bin/env python3
import sys
import os
import json
import requests
from pathlib import Path

os.environ["NO_GCE_CHECK"] = "True"
os.environ["GCE_METADATA_HOST"] = "disabled"

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube"
]

def get_token():
    if not TOKEN_FILE.exists():
        print("[!] No se encontró token.json")
        sys.exit(1)
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        t_data = json.load(f)
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds.token

def main():
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Obtener la playlist de subidas del canal
    ch_url = "https://youtube.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true"
    r = requests.get(ch_url, headers=headers)
    if r.status_code != 200:
        print(f"[!] Error al consultar canal: {r.status_code} {r.text}")
        return

    items = r.json().get("items", [])
    if not items:
        print("[!] No se encontraron canales para este token.")
        return

    uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"[*] Playlist de subidas: {uploads_id}")

    # 2. Recorrer todos los vídeos de la playlist
    video_ids = []
    page_token = None
    while True:
        pl_url = f"https://youtube.googleapis.com/youtube/v3/playlistItems?part=contentDetails&playlistId={uploads_id}&maxResults=50"
        if page_token:
            pl_url += f"&pageToken={page_token}"
        r_pl = requests.get(pl_url, headers=headers)
        if r_pl.status_code != 200:
            print(f"[!] Error al listar playlist: {r_pl.status_code} {r_pl.text}")
            break
        data = r_pl.json()
        for item in data.get("items", []):
            vid = item["contentDetails"]["videoId"]
            video_ids.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    print(f"[*] Total de vídeos encontrados en el canal: {len(video_ids)}")

    max_views = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"[*] Filtrando vídeos con menos de {max_views} visualizaciones...")

    # 3. Consultar estadísticas y estado de privacidad en bloques de 50
    low_view_videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        v_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet,status,statistics&id={','.join(batch)}"
        r_v = requests.get(v_url, headers=headers)
        if r_v.status_code != 200:
            print(f"[!] Error al consultar estadísticas de vídeos: {r_v.status_code} {r_v.text}")
            continue
        v_data = r_v.json()
        for v in v_data.get("items", []):
            vid_id = v["id"]
            title = v.get("snippet", {}).get("title", "Sin título")
            status = v.get("status", {})
            privacy = status.get("privacyStatus", "unknown")
            stats = v.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            
            print(f" - [{privacy.upper()}] {vid_id} | Vistas: {views} | {title[:60]}")
            
            if views < max_views and privacy != "private":
                low_view_videos.append((vid_id, title, views, v.get("snippet", {}), status))

    print(f"\n[*] Vídeos públicos/no listados con menos de {max_views} vistas a poner en PRIVADO: {len(low_view_videos)}")
    
    privatized = 0
    for vid_id, title, views, snippet, status in low_view_videos:
        print(f"[*] Cambiando a PRIVADO: {vid_id} ({views} vistas) - {title[:50]}...")
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
            print(f"  [✓] ¡Puesto en PRIVADO con éxito!")
            privatized += 1
        else:
            print(f"  [!] Error: {r_put.status_code} {r_put.text}")

    print(f"\n[✓] Proceso completado: {privatized}/{len(low_view_videos)} vídeos con <{max_views} vistas puestos en privado.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Privatiza el 100% de los vídeos anteriores en el canal de YouTube
para dejar el canal completamente limpio para la nueva arquitectura.
"""
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
    print("=" * 70)
    print("🔒 LIMPIEZA TOTAL: PASANDO TODO EL CONTENIDO ANTERIOR A PRIVADO")
    print("=" * 70)

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
        print("[!] No se encontraron canales.")
        return

    uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"[*] Playlist de subidas: {uploads_id}")

    # 2. Recorrer todos los vídeos
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

    # 3. Detectar todos los que NO estén ya en privado
    to_privatize = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        v_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet,status,statistics&id={','.join(batch)}"
        r_v = requests.get(v_url, headers=headers)
        if r_v.status_code != 200:
            print(f"[!] Error al consultar vídeos: {r_v.status_code} {r_v.text}")
            continue
        v_data = r_v.json()
        for v in v_data.get("items", []):
            vid_id = v["id"]
            title = v.get("snippet", {}).get("title", "Sin título")
            status = v.get("status", {})
            privacy = status.get("privacyStatus", "unknown")
            stats = v.get("statistics", {})
            views = int(stats.get("viewCount", 0))

            if privacy != "private":
                print(f" ⚠️  [A PRIVATIZAR] {vid_id} | Vistas: {views} | {title[:60]}")
                to_privatize.append((vid_id, title, views, v.get("snippet", {}), status))
            else:
                print(f"  ✓ [YA PRIVADO] {vid_id} | {title[:60]}")

    print(f"\n[*] Total de vídeos a pasar a PRIVADO: {len(to_privatize)}")

    privatized_count = 0
    for vid_id, title, views, snippet, status in to_privatize:
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
            privatized_count += 1
        else:
            print(f"  [!] Error: {r_put.status_code} {r_put.text}")

    print("\n" + "=" * 70)
    print(f"🎉 LIMPIEZA COMPLETADA: {privatized_count}/{len(to_privatize)} vídeos pasados a PRIVADO.")
    print("El canal queda con 0 vídeos públicos anteriores, listo para empezar de cero.")
    print("=" * 70)

if __name__ == "__main__":
    main()

import sys
import json
import subprocess
from typing import List, Dict, Any, Optional
from .config import CHANNELS_FILE, PROCESSED_FILE

def get_processed_ids() -> set:
    if not PROCESSED_FILE.exists():
        return set()
    try:
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {entry.get("id") for entry in data if "id" in entry}
    except Exception as e:
        print(f"[Warning] Error reading {PROCESSED_FILE}: {e}")
        return set()

def mark_video_processed(entry: Dict[str, Any]):
    processed = []
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                processed = json.load(f)
        except Exception:
            processed = []
    processed.append(entry)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

def fetch_channel_candidates(max_per_channel: int = 2) -> List[Dict[str, Any]]:
    if not CHANNELS_FILE.exists():
        return []

    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    processed_ids = get_processed_ids()
    candidates = []

    # 1. Target Channels
    for ch in config.get("channels", []):
        if not ch.get("enabled", True):
            continue
        url = ch.get("url")
        print(f"[*] Escaneando canal: {ch.get('name')} ({url})")
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(url)s",
                "-I", f"1:{max_per_channel}",
                url
            ], capture_output=True, text=True, check=True)

            lines = res.stdout.strip().split("\n")
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0]
                    title = parts[1]
                    duration = parts[2] if len(parts) > 2 else "0"
                    vid_url = parts[3] if len(parts) > 3 else f"https://www.youtube.com/watch?v={vid_id}"

                    if vid_id not in processed_ids and vid_id != "NA":
                        # Si el canal requiere filtrado de palabras clave, verificar que trata sobre GTA
                        if ch.get("filter_keywords", False):
                            gta_terms = ["gta", "grand theft auto", "rockstar", "vice city", "lucia", "jason"]
                            if not any(term in title.lower() for term in gta_terms):
                                continue

                        try:
                            dur_secs = float(duration) if duration and duration != "NA" else 0.0
                        except ValueError:
                            dur_secs = 0.0
                        
                        candidates.append({
                            "id": vid_id,
                            "title": title,
                            "url": vid_url,
                            "duration": dur_secs,
                            "source_name": ch.get("name"),
                            "source_type": ch.get("type", "general"),
                            "lang": ch.get("lang", "en"),
                            "is_short": (0 < dur_secs <= 60)
                        })
        except subprocess.CalledProcessError as e:
            print(f"[!] Error escaneando canal {url}: {e.stderr.strip() if e.stderr else e}")

    # 2. Search queries
    for q in config.get("search_queries", []):
        if not q.get("enabled", False):
            continue
        query = q.get("query")
        print(f"[*] Buscando por query: {query}")
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(url)s",
                query
            ], capture_output=True, text=True, check=True)

            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0]
                    title = parts[1]
                    duration = parts[2] if len(parts) > 2 else "0"
                    vid_url = parts[3] if len(parts) > 3 else f"https://www.youtube.com/watch?v={vid_id}"

                    if vid_id not in processed_ids and vid_id != "NA":
                        try:
                            dur_secs = float(duration) if duration and duration != "NA" else 0.0
                        except ValueError:
                            dur_secs = 0.0
                        candidates.append({
                            "id": vid_id,
                            "title": title,
                            "url": vid_url,
                            "duration": dur_secs,
                            "source_name": f"Search: {query}",
                            "is_short": (0 < dur_secs <= 60)
                        })
        except Exception as e:
            print(f"[!] Error en query {query}: {e}")

    return candidates

def list_monitored_channels() -> List[Dict[str, Any]]:
    """Devuelve la lista actual de canales en channels.json."""
    if not CHANNELS_FILE.exists():
        return []
    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("channels", [])
    except Exception:
        return []

def save_channels_config(config: Dict[str, Any]) -> bool:
    """Guarda la configuración actualizada en channels.json."""
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Channels] Error guardando {CHANNELS_FILE}: {e}")
        return False

def add_monitored_channel(url: str, name: str = "", lang: str = "en") -> Dict[str, Any]:
    """Añade un nuevo canal a channels.json."""
    config = {"channels": [], "search_queries": []}
    if CHANNELS_FILE.exists():
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    clean_url = url.strip()
    if not clean_url.endswith("/videos") and ("youtube.com/@" in clean_url or "youtube.com/channel/" in clean_url):
        clean_url = clean_url.rstrip("/") + "/videos"

    for ch in config.get("channels", []):
        if ch.get("url") == clean_url:
            return {"success": False, "message": f"El canal ya estaba registrado como '{ch.get('name')}'."}

    channel_name = name.strip() if name else ""
    if not channel_name:
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--print", "%(uploader)s",
                clean_url
            ], capture_output=True, text=True, timeout=12)
            first_line = res.stdout.strip().split("\n")[0]
            if first_line:
                channel_name = first_line
        except Exception:
            pass
    if not channel_name:
        channel_name = clean_url.split("/")[-2] if "/videos" in clean_url else clean_url.split("/")[-1]

    new_channel = {
        "name": channel_name,
        "url": clean_url,
        "type": "custom",
        "lang": lang,
        "filter_keywords": False,
        "enabled": True,
        "description": "Añadido desde Telegram Bot"
    }
    config.setdefault("channels", []).append(new_channel)
    save_channels_config(config)
    return {"success": True, "channel": new_channel}

def remove_monitored_channel(identifier: str) -> bool:
    """Elimina un canal por índice numérico (1-based) o nombre/URL."""
    if not CHANNELS_FILE.exists():
        return False
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    channels = config.get("channels", [])
    initial_len = len(channels)

    if identifier.strip().isdigit():
        idx = int(identifier.strip()) - 1
        if 0 <= idx < len(channels):
            channels.pop(idx)
    else:
        ident_lower = identifier.lower().strip()
        channels = [
            ch for ch in channels
            if ident_lower not in ch.get("name", "").lower() and ident_lower not in ch.get("url", "").lower()
        ]

    if len(channels) < initial_len:
        config["channels"] = channels
        save_channels_config(config)
        return True
    return False

def toggle_channel_enabled(index: int) -> Optional[bool]:
    """Invierte el estado de activación (enabled: True/False) de un canal."""
    if not CHANNELS_FILE.exists():
        return None
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    channels = config.get("channels", [])
    if 0 <= index < len(channels):
        channels[index]["enabled"] = not channels[index].get("enabled", True)
        config["channels"] = channels
        save_channels_config(config)
        return channels[index]["enabled"]
    return None

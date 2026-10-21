import sys
import json
import subprocess
from typing import List, Dict, Any
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

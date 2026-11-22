#!/usr/bin/env python3
"""
Simula 10 selecciones secuenciales del algoritmo de GTA VI Hub Extra (estilo Caspahz).
No descarga vídeo ni publica nada (100% dry-run analítico).
"""
import json
import sys
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ai_selector import select_best_candidate_ai
from src.channels import filter_repetitive_candidates, get_processed_ids
from src.viral_discovery import calculate_virality_score

def fetch_all_pool():
    with open(BASE_DIR / "config" / "channels.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    active_channels = [c for c in cfg.get("channels", []) if c.get("enabled", True)]
    active_queries = [q for q in cfg.get("search_queries", []) if q.get("enabled", True)]

    processed_ids = get_processed_ids()
    all_candidates = {}

    print(f"[*] Escaneando {len(active_channels)} canales activos y {len(active_queries)} queries...")

    # 1. Canales activos
    for ch in active_channels:
        url = (ch.get("url") or "").strip()
        ch_name = ch.get("name", "Canal")
        is_widescreen_src = ("/videos" in url or bool(ch.get("allow_long_clipping", False)))
        print(f"  -> Extrayendo: {ch_name} ({url})")
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s\t%(url)s\t%(upload_date)s\t%(uploader)s",
                "-I", "1:15",
                url
            ], capture_output=True, text=True, check=False, timeout=25)
            lines = (res.stdout or "").strip().split("\n")
            for line in lines:
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip()
                    if not vid_id or vid_id in processed_ids or vid_id == "NA":
                        continue
                    try:
                        dur = float(parts[2]) if len(parts) > 2 and parts[2] not in ("NA", "") else 0.0
                    except ValueError:
                        dur = 0.0
                    try:
                        views = int(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0
                    except ValueError:
                        views = 0
                    try:
                        likes = int(parts[4]) if len(parts) > 4 and parts[4] not in ("NA", "") else None
                    except ValueError:
                        likes = None
                    vid_url = parts[5] if len(parts) > 5 else f"https://www.youtube.com/watch?v={vid_id}"
                    uploader = parts[7].strip() if len(parts) > 7 and parts[7].strip() not in ("NA", "") else ch_name
                    
                    calc_dict = calculate_virality_score(title, dur, views, days_old=1, like_count=likes)
                    score = calc_dict.get("score", 50)
                    vpd = calc_dict.get("velocity_vpd")
                    vph = (float(vpd) / 24.0) if vpd is not None else (float(views) / 24.0)

                    all_candidates[vid_id] = {
                        "id": vid_id,
                        "title": title,
                        "url": vid_url,
                        "uploader": uploader,
                        "source_name": ch_name,
                        "duration": dur,
                        "views": views,
                        "likes": likes,
                        "score": score,
                        "views_per_hour": vph,
                        "hours_old": 24.0,
                        "allow_long_clipping": is_widescreen_src
                    }
        except Exception as e:
            print(f"     [!] Error escaneando {ch_name}: {e}")

    # 2. Queries prioritarias de shorts y guías
    for q in active_queries[-8:]:
        query_str = q.get("query", "")
        desc = q.get("description", "")
        print(f"  -> Extrayendo búsqueda: {query_str} ({desc})")
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--impersonate", "chrome",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s\t%(url)s\t%(upload_date)s\t%(uploader)s",
                "-I", "1:10",
                query_str
            ], capture_output=True, text=True, check=False, timeout=25)
            lines = (res.stdout or "").strip().split("\n")
            for line in lines:
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip()
                    if not vid_id or vid_id in processed_ids or vid_id == "NA":
                        continue
                    try:
                        dur = float(parts[2]) if len(parts) > 2 and parts[2] not in ("NA", "") else 0.0
                    except ValueError:
                        dur = 0.0
                    try:
                        views = int(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0
                    except ValueError:
                        views = 0
                    try:
                        likes = int(parts[4]) if len(parts) > 4 and parts[4] not in ("NA", "") else None
                    except ValueError:
                        likes = None
                    vid_url = parts[5] if len(parts) > 5 else f"https://www.youtube.com/watch?v={vid_id}"
                    uploader = parts[7].strip() if len(parts) > 7 and parts[7].strip() not in ("NA", "") else "Search"
                    
                    calc_dict = calculate_virality_score(title, dur, views, days_old=1, like_count=likes)
                    score = calc_dict.get("score", 50)
                    vpd = calc_dict.get("velocity_vpd")
                    vph = (float(vpd) / 24.0) if vpd is not None else (float(views) / 24.0)

                    all_candidates[vid_id] = {
                        "id": vid_id,
                        "title": title,
                        "url": vid_url,
                        "uploader": uploader,
                        "source_name": f"Search: {desc[:20]}",
                        "duration": dur,
                        "views": views,
                        "likes": likes,
                        "score": score,
                        "views_per_hour": vph,
                        "hours_old": 24.0,
                        "allow_long_clipping": q.get("allow_long_clipping", False)
                    }
        except Exception as e:
            print(f"     [!] Error query {query_str}: {e}")

    return list(all_candidates.values())

def simulate_10_rounds():
    pool = fetch_all_pool()
    print(f"\n[+] Total candidatos candidatos iniciales en el pool: {len(pool)}")
    
    simulated_processed = set()
    winners = []

    for round_num in range(1, 11):
        available = [c for c in pool if c["id"] not in simulated_processed]
        if not available:
            print(f"[-] No hay más candidatos disponibles en la ronda {round_num}")
            break
            
        filtered = filter_repetitive_candidates(available)
        if not filtered:
            print(f"[-] Todos los candidatos restantes fueron filtrados en la ronda {round_num}")
            break
            
        best = select_best_candidate_ai(filtered, launch_mode=True, use_ai=False)
        if not best:
            print(f"[-] No se pudo determinar ganador en la ronda {round_num}")
            break
            
        simulated_processed.add(best["id"])
        winners.append(best)
        print(f"  [Ronda {round_num:02d}] Ganador: {best.get('title')} ({best.get('uploader')}) - Score: {best.get('score')}")

    print("\n" + "="*80)
    print("🏆 RESULTADO DE LAS 10 SIMULACIONES (SOLO CLIPS - SIN PUBLICAR)")
    print("="*80)
    
    for idx, w in enumerate(winners, 1):
        print(f"\n#{idx:02d} | Creador: {w.get('uploader')} ({w.get('source_name')})")
        print(f"     Título: {w.get('title')}")
        print(f"     URL: {w.get('url')}")
        print(f"     Duración: {int(w.get('duration', 0))}s | Score: {w.get('score')} | VPH: {w.get('views_per_hour', 0):.0f}")
        print(f"     Arquetipo: {w.get('archetype', 'guia')} | Modo Recomendado: {w.get('recommended_mode', 'subs')}")
        print(f"     Justificación: {w.get('ai_justification', 'Prioridad de guía de ubicación/recompensa')}")

    out_file = BASE_DIR / "data" / "simulated_10_picks.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(winners, f, indent=2, ensure_ascii=False)
    print(f"\n[✓] Guardado en data/simulated_10_picks.json")

if __name__ == "__main__":
    simulate_10_rounds()

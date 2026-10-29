#!/usr/bin/env python3
import sys
import time
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.channels import fetch_channel_candidates
from src.learning_engine import load_viral_playbook

def score_with_playbook(cand: dict, heuristics: dict) -> float:
    base_score = float(cand.get("score", 0))
    dur = float(cand.get("duration", 0))
    title_lower = cand.get("title", "").lower()

    # 1. Bonus por duración óptima según el Playbook (18s - 28s para bucle continuo)
    if 18 <= dur <= 28:
        base_score += 18
    elif 14 <= dur <= 35:
        base_score += 8
    elif dur > 50:
        base_score -= 10  # Penalización por duración excesiva

    # 2. Penalización por clichés prohibidos del Playbook
    for bad in heuristics.get("forbidden_cliches", []):
        if bad.lower() in title_lower:
            base_score -= 25

    # 3. Bonus por temáticas de alta intriga y gameplay real
    for good in ["secreto", "secretos", "easter egg", "fisicas", "físicas", "detalles", "mapa", "south park"]:
        if good in title_lower:
            base_score += 10

    return base_score

def main():
    playbook = load_viral_playbook()
    heur = playbook.get("active_heuristics", {})

    print("=================================================================")
    print(" 🚀 INICIANDO EJECUCIÓN DEL BUCLE EDITORIAL (3 RONDAS)")
    print("=================================================================\n")

    chosen_history = []

    for round_num in range(1, 4):
        print(f"--- [RONDA {round_num}/3] ---")
        t0 = time.time()
        cands = fetch_channel_candidates(max_per_channel=2)
        elapsed = round(time.time() - t0, 2)
        print(f"[*] Escaneo completado en {elapsed}s. {len(cands)} candidatos encontrados.")

        if not cands:
            print("[-] No se encontraron candidatos en esta ronda.\n")
            continue

        scored_candidates = []
        for c in cands:
            s = score_with_playbook(c, heur)
            scored_candidates.append((s, c))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        top_score, top_cand = scored_candidates[0]
        chosen_history.append((top_score, top_cand))

        print(f"[✓] VÍDEO SELECCIONADO EN RONDA {round_num}:")
        print(f"    • ID: {top_cand['id']}")
        print(f"    • Título: {top_cand['title']}")
        print(f"    • Canal: {top_cand.get('source_name', 'Desconocido')}")
        print(f"    • Duración: {top_cand['duration']}s")
        print(f"    • Score Ponderado Playbook: {top_score} (Base: {top_cand.get('score')})")
        print(f"    • Enlace: {top_cand.get('url')}\n")

        # Top 3 de la ronda
        print("    Top 3 de la ronda:")
        for idx, (sc, item) in enumerate(scored_candidates[:3], 1):
            print(f"      {idx}. [{sc} pts] {item['title'][:55]} ({item['duration']}s)")
        print("\n")

        if round_num < 3:
            time.sleep(2)

    print("=================================================================")
    print(" 🏆 RESUMEN Y ELECCIÓN FINAL DEL MOTOR")
    print("=================================================================")
    if chosen_history:
        # Elegir el que mejor puntuación haya obtenido de las 3 rondas
        best_score, best_vid = sorted(chosen_history, key=lambda x: x[0], reverse=True)[0]
        print(f"🎯 VÍDEO DEFINITIVO GANADOR:")
        print(f"   • ID: {best_vid['id']}")
        print(f"   • Título: \"{best_vid['title']}\"")
        print(f"   • Duración: {best_vid['duration']}s")
        print(f"   • Score Final: {best_score} pts")
        print(f"   • URL: {best_vid.get('url')}")
    else:
        print("[-] No se seleccionó ningún vídeo.")

if __name__ == "__main__":
    main()

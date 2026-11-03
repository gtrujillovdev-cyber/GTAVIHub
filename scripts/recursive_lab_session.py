#!/usr/bin/env python3
"""
=============================================================================
🔄 SESIÓN RECURSIVA DE LABORATORIO (1 HORA) — GTA VI Hub Spain
=============================================================================
Ejecuta ciclos continuos de prueba durante 1 hora:
1. Aplica el algoritmo de virality score y Gemini AI para extraer los clips más
   virales y relevantes de GTA 6 en los canales monitorizados (<= 72h).
2. Genera variantes de diseño de cada clip en sandbox (Cinema, 9:16 Crop, Split-Screen).
3. Envía las variantes a Telegram con ficha técnica de puntuación para que el
   usuario evalúe el encuadre y ritmo en su teléfono móvil.
4. Mantiene HIGIENE ESTRICTA DE DISCO (Regla 0 Bytes): purga archivos temporales
   tras cada ciclo para no asfixiar el SSD ni degradar a GaTDSEQ.
5. CERO SUBIDAS PÚBLICAS: Ningún vídeo se publica en redes sociales.
=============================================================================
"""

import os
import sys
import time
import json
import shutil
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Set

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.config import BASE_DIR, DATA_DIR, is_quant_busy
from src.channels import fetch_channel_candidates
from src.ai_selector import select_best_candidate_ai
from src.learning_engine import load_viral_playbook
from scripts.clip_lab import (
    LAB_DIR, VARIANTS_DIR, TEMP_LAB_DIR,
    download_lab_clip, render_lab_variants,
    create_lab_html_viewer, send_lab_preview_to_telegram
)

LAB_STATE_FILE = DATA_DIR / "lab_session_state.json"


def load_lab_tested_ids() -> Set[str]:
    if LAB_STATE_FILE.exists():
        try:
            with open(LAB_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("tested_ids", []))
        except Exception:
            return set()
    return set()


def record_lab_tested_id(vid_id: str, title: str, score: float):
    tested = load_lab_tested_ids()
    tested.add(vid_id)
    history = []
    if LAB_STATE_FILE.exists():
        try:
            with open(LAB_STATE_FILE, "r", encoding="utf-8") as f:
                history = json.load(f).get("history", [])
        except Exception:
            history = []
    
    history.append({
        "id": vid_id,
        "title": title,
        "score": score,
        "tested_at": datetime.now().isoformat()
    })

    with open(LAB_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"tested_ids": list(tested), "history": history[-50:]}, f, indent=2, ensure_ascii=False)


def purge_lab_temporary_files():
    """Higiene estricta de disco (Regla 0 Bytes): purga buffers temporales tras cada prueba."""
    print("[🧹 Higiene SSD] Purgando archivos pesados temporales de descarga...")
    if TEMP_LAB_DIR.exists():
        for item in TEMP_LAB_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                print(f"  [!] No se pudo eliminar {item.name}: {e}")
    print("[✓] Espacio de trabajo temporal limpio (0 bytes).")


def run_single_lab_cycle(cycle_num: int, candidates_pool: List[Dict[str, Any]]) -> bool:
    """Ejecuta una iteración completa del laboratorio."""
    tested_ids = load_lab_tested_ids()
    available = [c for c in candidates_pool if c.get("id") not in tested_ids]

    if not available:
        print("[!] No hay candidatos nuevos sin probar en este ciclo.")
        return False

    print(f"\n" + "=" * 70)
    print(f"🧪 [CICLO {cycle_num}] SELECCIONANDO EL MEJOR CLIP DISPONIBLE")
    print("=" * 70)

    # Evaluar con IA
    playbook = load_viral_playbook()
    winner = select_best_candidate_ai(available, launch_mode=False, playbook=playbook)
    vid_id = winner.get("id")
    title = winner.get("title", "")
    url = winner.get("url", "")
    score = winner.get("score", 0)

    print(f"[*] Ganador del Ciclo {cycle_num}: '{title}'")
    print(f"    Canal/Autor: {winner.get('source_name')} | Score: {score} pts | Vistas: {winner.get('views', 0)}")
    print(f"    Justificación IA: {winner.get('ai_justification')}")

    # 1. Descargar clip
    raw_video = download_lab_clip(url)
    if not raw_video or not raw_video.exists():
        print(f"[!] Error descargando '{vid_id}'. Saltando a siguiente candidato.")
        record_lab_tested_id(vid_id, title, score)
        purge_lab_temporary_files()
        return False

    # 2. Renderizar las 3 variantes
    meta = {
        "title": title,
        "creator": winner.get("source_name", "Desconocido"),
        "hook": f"{winner.get('hook_line1', '')} {winner.get('hook_line2', '')}".strip() or "¡BOMBAZO GTA 6!"
    }
    variants = render_lab_variants(raw_video, hook_text=meta["hook"])

    # 3. Generar visor web HTML5 local
    create_lab_html_viewer(variants, meta)

    # 4. Enviar a Telegram para inspección móvil
    print(f"[*] Enviando variantes del Ciclo {cycle_num} a Telegram...")
    send_lab_preview_to_telegram(variants, meta)

    # 5. Registrar como probado
    record_lab_tested_id(vid_id, title, score)

    # 6. Higiene Estricta: Purgar archivos temporales pesados de descarga
    purge_lab_temporary_files()

    print(f"[✓] Ciclo {cycle_num} completado. Revisa Telegram para evaluar el formato.\n")
    return True


def run_recursive_lab(duration_minutes: int = 60, interval_seconds: int = 180):
    """Bucle principal de ejecución del laboratorio durante la duración especificada."""
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)

    print("=" * 70)
    print(f"🚀 INICIANDO SESIÓN RECURSIVA DE LABORATORIO ({duration_minutes} MINUTOS)")
    print(f"   Hora de inicio : {start_time.strftime('%H:%M:%S')}")
    print(f"   Hora de fin    : {end_time.strftime('%H:%M:%S')}")
    print(f"   Intervalo ciclo: Cada {interval_seconds // 60} minutos")
    print("=" * 70)

    cycle_count = 1
    while datetime.now() < end_time:
        now_str = datetime.now().strftime("%H:%M:%S")
        remaining_mins = max(0, int((end_time - datetime.now()).total_seconds() / 60))
        print(f"\n>>> [{now_str}] Iniciando Ciclo #{cycle_count} (Tiempo restante: {remaining_mins} min) <<<")

        # Comprobar cortesía con GaTDSEQ
        if is_quant_busy():
            print("[*] Modo Cortesía: GaTDSEQ está ejecutando modelos de cálculo. Pausando 60s...")
            time.sleep(60)
            continue

        # Escanear candidatos frescos
        candidates = fetch_channel_candidates(max_per_channel=2)
        if not candidates:
            print("[*] No se encontraron candidatos en este momento. Esperando próximo sondeo...")
        else:
            success = run_single_lab_cycle(cycle_count, candidates)
            if success:
                cycle_count += 1

        if datetime.now() >= end_time:
            break

        print(f"[*] Esperando {interval_seconds}s antes del próximo ciclo de laboratorio...")
        print("[*] Puedes escribir por Telegram qué variante va mejor o peor.")
        time.sleep(interval_seconds)

    print("\n" + "=" * 70)
    print(f"🎉 SESIÓN DE LABORATORIO DE 1 HORA FINALIZADA CON ÉXITO")
    print(f"   Total de ciclos ejecutados: {cycle_count - 1}")
    print(f"   Registro de pruebas guardado en: {LAB_STATE_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sesión recursiva de 1 hora del Laboratorio de Clips")
    parser.add_argument("--duration", type=int, default=60, help="Duración de la sesión en minutos (por defecto: 60)")
    parser.add_argument("--interval", type=int, default=180, help="Segundos entre ciclos (por defecto: 180s)")
    args = parser.parse_args()

    run_recursive_lab(duration_minutes=args.duration, interval_seconds=args.interval)

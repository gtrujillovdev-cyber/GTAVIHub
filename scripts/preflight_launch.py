#!/usr/bin/env python3
"""
scripts/preflight_launch.py
===========================
Verificación integral previa al lanzamiento de GTA VI (2026-11-19 00:00 CET).
Comprueba en modo solo lectura: rutas, disco (Regla 0 bytes), relojes/fases,
planificador nocturno, acceso API a gemini-4-hydrogen (con fallback), sesiones
sociales (YouTube / TikTok / Instagram) y daemon de Telegram.
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.adaptive_scheduler import generate_daily_schedule
from src.channel_sentinel import load_sentinel_state
from src.config import (
    BASE_DIR as CFG_BASE_DIR,
    CHANNELS_FILE,
    DATA_DIR,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LAUNCH_AUTOPILOT,
    OUTPUT_DIR,
    TEMP_DIR,
    is_gameplay_enabled,
)
from src.copilot import PENDING_DIR, is_copilot_enabled
from src.knowledge_recycler import determine_current_phase
from src.translator import FALLBACK_GEMINI_MODELS, generate_content_with_retry, get_gemini_client


def main() -> int:
    print("=================================================================")
    print("🚀 PREFLIGHT DE LANZAMIENTO — GTA VI HUB (NOCHE 19-N)")
    print("=================================================================")
    warnings = 0
    errors = 0

    # 1. Rutas y limpieza de disco
    temp_files = [p for p in TEMP_DIR.glob("*") if p.name != ".gitkeep"] if TEMP_DIR.exists() else []
    orphan_mp4s = list(OUTPUT_DIR.glob("*.mp4")) if OUTPUT_DIR.exists() else []
    pending_files = list(PENDING_DIR.glob("*.json")) if PENDING_DIR.exists() else []
    print(f"[1] Rutas & Disco:")
    print(f"    • BASE_DIR           : {CFG_BASE_DIR}")
    print(f"    • temp/ archivos     : {len(temp_files)} {'(OK)' if not temp_files else '(LIMPIAR)'}")
    print(f"    • output/*.mp4       : {len(orphan_mp4s)} {'(OK)' if not orphan_mp4s else '(HUÉRFANOS)'}")
    print(f"    • pending_approvals  : {len(pending_files)}")
    if temp_files or orphan_mp4s:
        warnings += 1

    # 2. Reloj de lanzamiento, fases y calendario nocturno
    now_local = datetime.now()
    now_utc = datetime.now(timezone.utc)
    launch_sched = generate_daily_schedule(target_date=date(2026, 11, 19))
    launch_ids = [w.get("id") for w in launch_sched.get("windows", [])]
    has_midnight = "midnight_drop" in launch_ids and "late_night_wave" in launch_ids
    print(f"[2] Reloj, Fases & Calendario Nocturno:")
    print(f"    • Hora local         : {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    • Fase UTC actual    : {determine_current_phase(now_utc)}")
    print(f"    • Fase 00:05 CET     : {determine_current_phase(datetime(2026, 11, 18, 23, 5, tzinfo=timezone.utc))}")
    print(f"    • Gameplay habilitado: {is_gameplay_enabled()}")
    print(f"    • Ventanas 19-N      : {launch_ids}")
    if not has_midnight:
        print("    [!] ERROR: Faltan ventanas midnight_drop/late_night_wave para 2026-11-19.")
        errors += 1

    # 3. Fuentes y queries de lanzamiento
    cfg = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    enabled_ch = [c for c in cfg.get("channels", []) if c.get("enabled", True)]
    launch_qs = [q for q in cfg.get("search_queries", []) if q.get("active_after") == "2026-11-19"]
    print(f"[3] Fuentes y Queries:")
    print(f"    • Canales activos    : {len(enabled_ch)}")
    print(f"    • Queries 19-N       : {len(launch_qs)} (sp={sorted({q.get('sp', '') for q in launch_qs})})")
    if not launch_qs:
        warnings += 1

    # 4. Política nocturna & IA (Hydrogen / Fallback)
    print(f"[4] IA (Hydrogen) & Co-Pilot:")
    print(f"    • GEMINI_MODEL       : {GEMINI_MODEL}")
    print(f"    • Fallback chain     : {FALLBACK_GEMINI_MODELS}")
    print(f"    • Co-Pilot           : {'ACTIVO' if is_copilot_enabled() else 'DESACTIVADO'}")
    print(f"    • LAUNCH_AUTOPILOT   : {'ACTIVO' if LAUNCH_AUTOPILOT else 'DESACTIVADO'}")
    if not GEMINI_API_KEY:
        print("    [!] ERROR: GEMINI_API_KEY vacía.")
        errors += 1
    else:
        try:
            client = get_gemini_client()
            resp = generate_content_with_retry(
                client=client,
                contents='Responde exactamente con JSON válido: {"status": "ok"}',
                config={"response_mime_type": "application/json"},
            )
            print(f"    • Prueba API en vivo : OK -> {(resp.text or '').strip()[:60]}")
        except Exception as exc:
            print(f"    [!] ERROR prueba API : {exc}")
            errors += 1

    # 5. Sesiones sociales & Sentinel
    profiles_dir = CFG_BASE_DIR / "assets" / ".browser_profiles"
    yt_tok = (CFG_BASE_DIR / "token_extra.json").exists() or (CFG_BASE_DIR / "token.json").exists()
    tk_state = profiles_dir / "storage_state.json"
    tk_ok = tk_state.exists() and "tiktok.com" in tk_state.read_text(encoding="utf-8", errors="ignore")
    ig_legacy = os.getenv("ALLOW_LEGACY_INSTAGRAM", "false").lower()
    ig_sess = (profiles_dir / f"instagrapi_session_{os.getenv('INSTAGRAM_USERNAME', 'gtavihubextra').strip().lstrip('@')}.json").exists()
    sentinel = load_sentinel_state().get("channels", {})
    yt_health = (sentinel.get("youtube_extra") or {}).get("status", "unknown")
    tk_health = (sentinel.get("tiktok_extra") or {}).get("status", "unknown")
    print(f"[5] Canales & Sesiones:")
    print(f"    • YouTube OAuth2     : {'OK' if yt_tok else 'FALTA'} (sentinel={yt_health})")
    print(f"    • TikTok session     : {'OK' if tk_ok else 'FALTA'} (sentinel={tk_health})")
    print(f"    • Instagram session  : {'OK' if ig_sess else 'FALTA REAUTH'} (ALLOW_LEGACY_INSTAGRAM={ig_legacy})")
    if not yt_tok or not tk_ok:
        errors += 1
    if not ig_sess:
        warnings += 1

    # 6. Daemon Telegram en ejecución
    try:
        pg = subprocess.run(["pgrep", "-fl", "main.py --telegram"], capture_output=True, text=True, timeout=5)
        daemon_lines = [ln for ln in pg.stdout.strip().splitlines() if ln.strip()]
    except Exception:
        daemon_lines = []
    print(f"[6] Daemon Telegram:")
    print(f"    • Procesos activos   : {len(daemon_lines)}")
    for ln in daemon_lines:
        print(f"      - {ln}")
    if not daemon_lines:
        warnings += 1

    print("=================================================================")
    print(f"RESULTADO PREFLIGHT: {errors} error(es), {warnings} aviso(s).")
    print("=================================================================")
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

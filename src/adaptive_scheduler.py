"""
src/adaptive_scheduler.py
=========================
Planificador adaptativo con mapeo inteligente de franjas horarias y
variabilidad estocástica (anti-detección / human jitter).

Evita que los algoritmos de YouTube, TikTok e Instagram identifiquen
patrones rígidos de bots (publicaciones repetitivas a la misma hora exacta).

Distribución por Franjas Horarias (CET):
  1. MAÑANA (Pico 11:00)         : Franja 10:15 - 11:20 CET (Aleatorio)
  2. ALMUERZO/LATAM (Pico 14:30)  : Franja 13:45 - 14:50 CET (Aleatorio)
  3. TARDE (Pico 18:00)          : Franja 17:15 - 18:25 CET (Aleatorio)
  4. PRIME TIME (Pico 21:00)     : Franja 20:15 - 21:30 CET (Aleatorio)
  5. SLOTS EXTRA (Opcionales)    : 08:30 - 09:15 / 15:30 - 16:15
"""

import os
import json
import random
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import DATA_DIR

SCHEDULE_FILE = DATA_DIR / "adaptive_schedule.json"

# Definición de ventanas objetivo con margen previo de 25-45 min para render 4K + GaTDSEQ
TARGET_WINDOWS = [
    {
        "id": "morning",
        "name": "🌅 Mañana (Pico España 11:00)",
        "start_hour": 10,
        "start_minute": 15,
        "end_hour": 10,
        "end_minute": 35,
        "target_label": "10:15 - 10:35 CET"
    },
    {
        "id": "lunch_latam",
        "name": "🍲 Almuerzo ES / Amanecer LatAm (14:30)",
        "start_hour": 13,
        "start_minute": 45,
        "end_hour": 14,
        "end_minute": 5,
        "target_label": "13:45 - 14:05 CET"
    },
    {
        "id": "afternoon",
        "name": "🌇 Tarde / Salida Laboral (18:00)",
        "start_hour": 17,
        "start_minute": 15,
        "end_hour": 17,
        "end_minute": 35,
        "target_label": "17:15 - 17:35 CET"
    },
    {
        "id": "prime_time",
        "name": "🌙 Prime Time ES / Tarde LatAm (21:00)",
        "start_hour": 20,
        "start_minute": 15,
        "end_hour": 20,
        "end_minute": 35,
        "target_label": "20:15 - 20:35 CET"
    }
]

# Ventana extraordinaria activada únicamente en la noche de estreno (19 nov);
# desde el 20 nov se reservan los 4 disparos diarios para las franjas punta ES/LatAm.
LAUNCH_NIGHT_DATES = (date(2026, 11, 19),)
LAUNCH_NIGHT_WINDOWS = [
    {
        "id": "midnight_drop",
        "name": "🚀 Estreno Mundial GTA 6 (00:00 CET)",
        "start_hour": 0,
        "start_minute": 10,
        "end_hour": 0,
        "end_minute": 40,
        "target_label": "00:10 - 00:40 CET"
    },
    {
        "id": "late_night_wave",
        "name": "🔥 Oleada Gameplay Madrugada",
        "start_hour": 1,
        "start_minute": 30,
        "end_hour": 2,
        "end_minute": 20,
        "target_label": "01:30 - 02:20 CET"
    },
]

# Ventana de captura inmediata para los primeros gameplays reales (18 nov tarde)
EARLY_GAMEPLAY_DATE = date(2026, 11, 18)
EARLY_GAMEPLAY_WINDOWS = [
    {
        "id": "early_gameplay_wave",
        "name": "🎮 Oleada Primer Gameplay GTA 6",
        "start_hour": 15,
        "start_minute": 50,
        "end_hour": 16,
        "end_minute": 35,
        "target_label": "15:50 - 16:35 CET"
    },
]


def _generate_random_time_in_range(start_h: int, start_m: int, end_h: int, end_m: int) -> tuple[int, int]:
    """Genera una hora y minuto pseudoaleatorios uniformes dentro de una franja."""
    total_start = start_h * 60 + start_m
    total_end = end_h * 60 + end_m
    random_minute = random.randint(total_start, total_end)
    return (random_minute // 60, random_minute % 60)


def _build_window_plan(win: Dict[str, Any]) -> Dict[str, Any]:
    """Construye una entrada estocástica de ventana a partir de su definición."""
    h, m = _generate_random_time_in_range(
        win["start_hour"], win["start_minute"],
        win["end_hour"], win["end_minute"]
    )
    return {
        "id": win["id"],
        "name": win["name"],
        "scheduled_time": f"{h:02d}:{m:02d}",
        "hour": h,
        "minute": m,
        "jitter_sec": random.randint(-180, 180),
        "window_start": f"{win['start_hour']:02d}:{win['start_minute']:02d}",
        "window_end": f"{win['end_hour']:02d}:{win['end_minute']:02d}",
        "completed": False,
        "completed_at": None,
        "published_url": None,
    }


def generate_daily_schedule(target_date: Optional[date] = None, force_regenerate: bool = False) -> Dict[str, Any]:
    """
    Genera el itinerario aleatorio del día si aún no existe para la fecha indicada.
    Si ya existe y no se fuerza regeneración, retorna el actual.
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()

    existing = load_all_schedules()
    if not force_regenerate and date_str in existing:
        return existing[date_str]

    if target_date in LAUNCH_NIGHT_DATES:
        source_windows = LAUNCH_NIGHT_WINDOWS + TARGET_WINDOWS
    elif target_date == EARLY_GAMEPLAY_DATE:
        source_windows = TARGET_WINDOWS + EARLY_GAMEPLAY_WINDOWS
    else:
        source_windows = TARGET_WINDOWS
    windows_plan = [_build_window_plan(win) for win in source_windows]

    day_schedule = {
        "date": date_str,
        "created_at": datetime.now().isoformat(),
        "windows": windows_plan
    }

    existing[date_str] = day_schedule
    save_all_schedules(existing)
    return day_schedule


def load_all_schedules() -> Dict[str, Any]:
    """Carga el historial completo de planificaciones del disco."""
    if not SCHEDULE_FILE.exists():
        return {}
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_all_schedules(data: Dict[str, Any]):
    """Guarda las planificaciones en disco."""
    try:
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[AdaptiveScheduler] Error guardando schedule: {e}")


def get_daily_schedule(target_date: Optional[date] = None) -> Dict[str, Any]:
    """Obtiene la planificación para el día, inyectando ventanas de estreno si faltasen."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    existing = load_all_schedules()
    if date_str in existing:
        day_sched = existing[date_str]
        if target_date in LAUNCH_NIGHT_DATES:
            present_ids = {w.get("id") for w in day_sched.get("windows", [])}
            added = [_build_window_plan(w) for w in LAUNCH_NIGHT_WINDOWS if w["id"] not in present_ids]
            if added:
                day_sched["windows"] = added + day_sched.get("windows", [])
                existing[date_str] = day_sched
                save_all_schedules(existing)
        elif target_date == EARLY_GAMEPLAY_DATE:
            present_ids = {w.get("id") for w in day_sched.get("windows", [])}
            added = [_build_window_plan(w) for w in EARLY_GAMEPLAY_WINDOWS if w["id"] not in present_ids]
            if added:
                day_sched["windows"] = day_sched.get("windows", []) + added
                existing[date_str] = day_sched
                save_all_schedules(existing)
        return day_sched
    return generate_daily_schedule(target_date)


def get_due_window(now_dt: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """
    Evalúa si en el momento actual `now_dt` toca disparar alguna de las ventanas aleatorias.
    Una ventana se considera lista si:
      - Pertenece a la fecha de hoy.
      - No está marcada como 'completed'.
      - La hora actual ha alcanzado o superado `scheduled_time`, y no ha pasado más de 45 minutos del horario programado.
    """
    if now_dt is None:
        now_dt = datetime.now()

    today_sched = get_daily_schedule(now_dt.date())
    now_minutes = now_dt.hour * 60 + now_dt.minute

    for window in today_sched.get("windows", []):
        if window.get("completed", False):
            continue

        sched_h = window["hour"]
        sched_m = window["minute"]
        sched_total = sched_h * 60 + sched_m

        # Si ya llegamos a la hora programada y estamos en el margen de 45 min
        if sched_total <= now_minutes <= (sched_total + 45):
            return window

    return None


def mark_window_completed(window_id: str, published_url: Optional[str] = None, target_date: Optional[date] = None):
    """Marca una franja como completada para no volver a ejecutarla hoy."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()

    all_sched = load_all_schedules()
    if date_str not in all_sched:
        return

    day_plan = all_sched[date_str]
    for w in day_plan.get("windows", []):
        if w["id"] == window_id:
            w["completed"] = True
            w["completed_at"] = datetime.now().isoformat()
            if published_url:
                w["published_url"] = published_url
            break

    save_all_schedules(all_sched)


def get_window_performance_stats() -> Dict[str, Dict[str, float]]:
    """
    Analiza el rendimiento historico por franja horaria.
    Retorna: { "morning": {"avg_views": 1200, "count": 5}, ... }
    """
    try:
        from .performance_tracker import _load_records
        records = _load_records()
    except Exception:
        return {}

    # Mapear hora de publicacion a window_id
    stats: Dict[str, list] = {}
    for rec in records:
        views = rec.get("views_24h")
        pub_at = rec.get("published_at", "")
        if views is None or not pub_at:
            continue
        try:
            pub_hour = datetime.fromisoformat(pub_at).hour
        except Exception:
            continue
        # Mapear hora a window_id
        if 9 <= pub_hour <= 11:
            wid = "morning"
        elif 13 <= pub_hour <= 15:
            wid = "lunch_latam"
        elif 16 <= pub_hour <= 18:
            wid = "afternoon"
        elif 19 <= pub_hour <= 22:
            wid = "prime_time"
        else:
            continue
        stats.setdefault(wid, []).append(views)

    result = {}
    for wid, views_list in stats.items():
        result[wid] = {
            "avg_views": round(sum(views_list) / len(views_list), 1),
            "count": len(views_list),
            "best": max(views_list),
        }
    return result


def format_schedule_summary(target_date: Optional[date] = None) -> str:
    """Devuelve un resumen amigable en formato texto para Telegram o logs."""
    sched = get_daily_schedule(target_date)
    lines = [f"📅 *Planificador Adaptativo ({sched.get('date')})*"]
    lines.append("🛡️ _Horarios aleatorizados anti-detección:_\n")

    perf = get_window_performance_stats()

    for w in sched.get("windows", []):
        status = "✅ Hecho" if w.get("completed") else "⏳ Pendiente"
        perf_str = ""
        wid = w.get("id", "")
        if wid in perf:
            p = perf[wid]
            perf_str = f"\n   📊 _Histórico: {p['avg_views']:.0f} vistas/24h promedio ({p['count']} clips, mejor: {p['best']})_"
        lines.append(
            f"• *{w['name']}*: `{w['scheduled_time']} CET` ({status})\n"
            f"   _Rango orgánico: {w['window_start']} - {w['window_end']}_{perf_str}"
        )
    return "\n".join(lines)

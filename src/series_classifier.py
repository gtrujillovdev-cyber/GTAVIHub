"""
Series Classifier — Detecta si un clip encaja en una serie recurrente
y asigna numero de episodio automaticamente.

Persiste el estado en data/series_state.json para mantener la numeracion
continua entre ejecuciones.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .config import DATA_DIR

SERIES_STATE_FILE = DATA_DIR / "series_state.json"

SERIES_PATTERNS: Dict[str, Dict[str, Any]] = {
    "coches_gratis": {
        "keywords": ["coche gratis", "supercoche", "supercar", "free car", "rare car", "coche raro", "vehiculo gratis", "vehiculo secreto"],
        "title_template": "COCHES SECRETOS & GRATIS EN GTA 6 #{n}",
        "hook_prefix": "COCHE GRATIS #{n}",
    },
    "armas_legendarias": {
        "keywords": ["arma legendaria", "armas legendarias", "arma oculta", "armas ocultas", "arma secreta", "free weapon", "gold weapon", "arma dorada"],
        "title_template": "ARMAS SECRETAS DE GTA 6 #{n}",
        "hook_prefix": "ARMA SECRETA #{n}",
    },
    "dinero_rapido": {
        "keywords": ["dinero", "money method", "dinero rapido", "cash", "loot", "dinero facil", "maletin", "loot location"],
        "title_template": "TRUCOS DE DINERO EN GTA 6 #{n}",
        "hook_prefix": "DINERO RÁPIDO #{n}",
    },
    "secretos_leonida": {
        "keywords": ["secreto de leonida", "secretos de leonida", "easter egg", "hidden", "secreto oculto", "secretos ocultos", "ubicacion secreta", "hidden location", "misterio"],
        "title_template": "SECRETOS DEL MAPA DE GTA 6 #{n}",
        "hook_prefix": "SECRETO MAPA #{n}",
    },
    "detalles_enfermizos": {
        "keywords": ["detalle enfermizo", "detalles enfermizos", "detalles ocultos", "detalle oculto", "detalles que no viste", "insane detail"],
        "title_template": "DETALLES OCULTOS DE GTA 6 #{n}",
        "hook_prefix": "DETALLE #{n}",
    },
    "mitos_a_prueba": {
        "keywords": ["mito", "mitos a prueba", "verdad o mentira", "mitos de gta", "mythbusters"],
        "title_template": "MITOS A PRUEBA EN GTA 6 #{n}",
        "hook_prefix": "MITO #{n}",
    },
}


def _load_state() -> Dict[str, Any]:
    if not SERIES_STATE_FILE.exists():
        return {"series": {}, "last_updated": None}
    try:
        with open(SERIES_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"series": {}, "last_updated": None}


def _save_state(state: Dict[str, Any]) -> None:
    state["last_updated"] = datetime.now().isoformat()
    try:
        with open(SERIES_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[SeriesClassifier] Error guardando estado: {e}")


def classify_and_number(
    title: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Analiza el titulo y metadatos para detectar si encaja en una serie recurrente.

    Retorna None si no encaja, o un dict con:
    {
        "series_id": "detalles_enfermizos",
        "episode": 14,
        "stamp_text": "DETALLES ENFERMIZOS #14",
        "hook_prefix": "DETALLE #14"
    }
    """
    combined = f" {(title or '').lower()} "
    # Normalizar acentos basicos para matching
    combined = combined.replace("a\u0301", "a").replace("e\u0301", "e").replace("i\u0301", "i")
    combined = combined.replace("o\u0301", "o").replace("u\u0301", "u")
    combined = combined.replace("\u00e1", "a").replace("\u00e9", "e").replace("\u00ed", "i")
    combined = combined.replace("\u00f3", "o").replace("\u00fa", "u")

    archetype = (metadata or {}).get("archetype", "")

    best_match = None
    best_score = 0

    for series_id, config in SERIES_PATTERNS.items():
        score = 0
        for kw in config["keywords"]:
            kw_norm = kw.replace("\u00e1", "a").replace("\u00e9", "e").replace("\u00ed", "i").replace("\u00f3", "o").replace("\u00fa", "u")
            if kw_norm in combined:
                # Longer keywords are more specific, score higher
                score = max(score, len(kw_norm))

        if score > best_score:
            best_score = score
            best_match = series_id

    if not best_match or best_score < 4:
        return None

    # Incrementar contador
    state = _load_state()
    series_data = state.setdefault("series", {})
    entry = series_data.setdefault(best_match, {"count": 0, "history": []})
    entry["count"] = entry.get("count", 0) + 1
    episode = entry["count"]

    # Registrar en historial (ultimos 50)
    entry.setdefault("history", []).append({
        "episode": episode,
        "title": title[:80],
        "date": datetime.now().isoformat()
    })
    entry["history"] = entry["history"][-50:]

    _save_state(state)

    config = SERIES_PATTERNS[best_match]
    stamp = config["title_template"].replace("{n}", str(episode))
    hook_prefix = config["hook_prefix"].replace("{n}", str(episode))

    return {
        "series_id": best_match,
        "episode": episode,
        "stamp_text": stamp,
        "hook_prefix": hook_prefix
    }


def get_series_summary() -> str:
    """Genera un resumen de todas las series activas para Telegram."""
    state = _load_state()
    series = state.get("series", {})
    if not series:
        return "No hay series activas registradas."

    lines = ["*Series Numeradas Activas:*"]
    for sid, data in sorted(series.items()):
        count = data.get("count", 0)
        last = data.get("history", [{}])[-1] if data.get("history") else {}
        last_date = last.get("date", "")[:10] if last else ""
        config = SERIES_PATTERNS.get(sid, {})
        name = config.get("title_template", sid).replace(" #{n}", "")
        lines.append(f"  - `{name}`: {count} episodios (ultimo: {last_date})")

    return "\n".join(lines)

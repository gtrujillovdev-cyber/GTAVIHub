#!/usr/bin/env python3
"""
src/knowledge_recycler.py — Motor de Reciclaje Dinámico de Conocimiento para GTA 6.

Garantiza que la base de datos, el selector de IA y las búsquedas se adapten
automáticamente a medida que el juego evoluciona en el tiempo:
- Fase 1 (Pre-Lanzamiento: Hoy hasta 18 Nov): Filtraciones, físicas RAGE 9, comparativas, preventas.
- Fase 2 (Día D y Semana de Estreno: 19 Nov - 25 Nov): Gameplay puro, prólogo, misiones, rendimiento PS5.
- Fase 3 (Post-Lanzamiento: 26 Nov en adelante): Easter eggs, secretos, mejores vehículos, economía, fails.

Recicla y purga conceptos obsoletos (ej. rumores desmentidos o teasers viejos)
e incorpora nuevas entidades detectadas por el Traffic Sentinel y los vídeos procesados.
"""

import os
import sys
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import DATA_DIR
from src.traffic_sentinel import get_latest_traffic_radar

KNOWLEDGE_STATE_FILE = DATA_DIR / "gta6_dynamic_knowledge.json"
CANON_FILE = BASE_DIR / "docs" / "GTA6_LORE_AND_CANON.md"

# Fechas de transición de fases
LAUNCH_DATE = datetime(2026, 11, 19, 0, 0, 0, tzinfo=timezone.utc)
POST_LAUNCH_DATE = datetime(2026, 11, 26, 0, 0, 0, tzinfo=timezone.utc)

PHASE_CONFIGS = {
    "pre_launch": {
        "name": "Fase 1: Pre-Lanzamiento y Expectación Máxima",
        "description": "Filtraciones confirmadas, comparativas generacionales RAGE 9 vs GTA 5, mapa de Leonida y reservas Amazon.",
        "primary_topics": [
            "comparativas tecnicas", "fisicas de agua y colision", "filtraciones in-game",
            "detalles ocultos vice city", "reserva ps5 pro amazon", "lucia y jason dinamica"
        ],
        "forbidden_topics": [
            "trailer 1 2023", "rumores falsos de cancelacion", "gta online antiguo"
        ],
        "target_affiliate_focus": "Consolas PS5 Pro / Slim, Volantes Logitech, Preventa GTA 6",
        "title_prefixes": ["¡DETALLE IN-GAME!", "FÍSICAS RAGE 9:", "COMPARATIVA DEFINITIVA:"]
    },
    "launch_day": {
        "name": "Fase 2: Día D y Semana de Estreno (Estreno Mundial)",
        "description": "Gameplay puro en vivo, misiones iniciales de Lucía y Jason, mapa abierto explorado y rendimiento en consolas.",
        "primary_topics": [
            "mision prologo lucia", "primer atraco jason", "conduccion y tiroteos reales",
            "rendimiento ps5 pro vs ps5", "secretos desbloqueados dia 1", "mapa completo explorado"
        ],
        "forbidden_topics": [
            "especulaciones de fecha", "rumores de preventa", "trailers viejos"
        ],
        "target_affiliate_focus": "Accesorios de juego inmediato (mandos DualSense, auriculares Pulse 3D)",
        "title_prefixes": ["¡GAMEPLAY REAL!", "PRIMERA MISIÓN:", "BRUTAL DETALLE:"]
    },
    "post_launch": {
        "name": "Fase 3: Post-Lanzamiento, Secretos y Mundo Abierto",
        "description": "Easter eggs ocultos, armas y coches secretos, mitos desmentidos, momentos virales y noticias multijugador.",
        "primary_topics": [
            "easter eggs ocultos", "mansion vercetti secretos", "mejores coches y personalizacion",
            "armas secretas leonida", "fails y fisicas divertidas", "novedades gta online 2"
        ],
        "forbidden_topics": [
            "noticias de preventa", "rumores de estreno"
        ],
        "target_affiliate_focus": "Merchandising oficial, tarjetas PlayStation Network, periféricos de carreras",
        "title_prefixes": ["SECRETO OCULTO:", "EL DETALLE QUE NADIE VIO:", "UBICACIÓN SECRETA:"]
    }
}


def determine_current_phase(now: Optional[datetime] = None) -> str:
    """Determina la fase editorial activa según la fecha UTC actual."""
    if now is None:
        now = datetime.now(timezone.utc)
    if now < LAUNCH_DATE:
        return "pre_launch"
    elif now < POST_LAUNCH_DATE:
        return "launch_day"
    else:
        return "post_launch"


def load_dynamic_knowledge() -> Dict[str, Any]:
    """Carga el estado reciclable del conocimiento de GTA 6."""
    if KNOWLEDGE_STATE_FILE.exists():
        try:
            with open(KNOWLEDGE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return initialize_knowledge_state()


def initialize_knowledge_state() -> Dict[str, Any]:
    """Inicializa la estructura dinámica de conocimiento si no existe."""
    phase = determine_current_phase()
    cfg = PHASE_CONFIGS[phase]
    initial_data = {
        "version": 1,
        "last_recycled_at": datetime.now(timezone.utc).isoformat(),
        "current_phase": phase,
        "phase_name": cfg["name"],
        "phase_description": cfg["description"],
        "days_to_launch": max(0, (LAUNCH_DATE - datetime.now(timezone.utc)).days),
        "active_primary_topics": cfg["primary_topics"],
        "retired_topics": cfg["forbidden_topics"],
        "target_affiliate_focus": cfg["target_affiliate_focus"],
        "title_prefixes": cfg["title_prefixes"],
        "discovered_entities": {
            "characters": ["Lucia", "Jason Duval", "Boobie Ike", "Brian Heder", "Stefanie", "Raul Bautista"],
            "locations": ["Vice City", "Leonida Keys", "Grassrivers", "Port Gellhorn", "Ambrosia", "Mount Kalaga"],
            "weapons_and_tools": ["Loot Bag", "Slim Jim", "Tracker Jammer", "Immobilizer Bypass", "Heavy Rifle"],
            "cultural_memes": ["Florida Joker", "Mud Girl", "Thrillbilly Mud Club", "South Park Parody"]
        },
        "emerging_keywords_pool": []
    }
    save_dynamic_knowledge(initial_data)
    return initial_data


def save_dynamic_knowledge(data: Dict[str, Any]) -> bool:
    """Guarda el estado actualizado en data/gta6_dynamic_knowledge.json."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(KNOWLEDGE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[KnowledgeRecycler] Error guardando estado: {e}")
        return False


def recycle_knowledge(force: bool = False) -> Dict[str, Any]:
    """
    Ejecuta el ciclo de reciclaje continuo:
    1. Verifica si ha cambiado la fase temporal (pre-launch -> launch_day -> post_launch).
    2. Cruza con el Traffic Sentinel para extraer nuevas entidades y búsquedas emergentes.
    3. Purga conceptos que hayan quedado obsoletos.
    4. Actualiza data/gta6_dynamic_knowledge.json.
    """
    state = load_dynamic_knowledge()
    now_utc = datetime.now(timezone.utc)
    new_phase = determine_current_phase(now_utc)
    phase_changed = (new_phase != state.get("current_phase"))

    cfg = PHASE_CONFIGS[new_phase]
    state["current_phase"] = new_phase
    state["phase_name"] = cfg["name"]
    state["phase_description"] = cfg["description"]
    state["days_to_launch"] = max(0, (LAUNCH_DATE - now_utc).days)
    state["target_affiliate_focus"] = cfg["target_affiliate_focus"]
    state["title_prefixes"] = cfg["title_prefixes"]

    # Combinar temas canónicos de la fase con los aprendidos
    base_topics = list(cfg["primary_topics"])
    state["retired_topics"] = list(set(state.get("retired_topics", []) + cfg["forbidden_topics"]))

    # Extraer nuevas entidades y palabras clave del radar de tráfico
    try:
        radar = get_latest_traffic_radar()
        keywords = radar.get("trending_keywords", [])
        top_intents = radar.get("top_search_intents", [])

        # Filtrar keywords para evitar redundancias
        clean_kw = [k for k in keywords if len(k) > 3 and k not in state["retired_topics"]]
        state["emerging_keywords_pool"] = clean_kw[:25]

        # Añadir intenciones emergentes a los temas activos
        for intent in top_intents[:4]:
            if intent not in base_topics and intent not in state["retired_topics"]:
                base_topics.append(intent)

        # Detectar posibles nuevos personajes o localizaciones en las noticias
        news_items = radar.get("breaking_news", [])
        for n in news_items:
            t = n.get("title", "")
            # Palabras capitalizadas dentro del titular
            cap_words = re.findall(r'\b[A-Z][a-z0-9]+\b', t)
            for w in cap_words:
                if w.lower() not in ["gta", "grand", "theft", "auto", "rockstar", "take", "two", "sony", "xbox", "ps5", "espana", "noticia"]:
                    # Registrar como entidad emergente si no está
                    locs = state["discovered_entities"].get("locations", [])
                    chars = state["discovered_entities"].get("characters", [])
                    if w not in locs and w not in chars and len(w) > 4:
                        state["discovered_entities"].setdefault("emerging_entities", []).append(w)
                        # Limitar lista de emergentes a 15
                        state["discovered_entities"]["emerging_entities"] = list(set(state["discovered_entities"]["emerging_entities"]))[:15]

    except Exception as e:
        print(f"[KnowledgeRecycler] Error cruzando con radar de tráfico: {e}")

    state["active_primary_topics"] = base_topics[:10]
    state["last_recycled_at"] = now_utc.isoformat()

    save_dynamic_knowledge(state)
    return state


def get_current_editorial_context() -> str:
    """
    Genera un bloque de contexto editorial fresco para inyectar en Gemini Flash
    y los módulos de generación de metadatos.
    """
    state = load_dynamic_knowledge()
    phase = state.get("current_phase", "pre_launch")
    cfg = PHASE_CONFIGS.get(phase, PHASE_CONFIGS["pre_launch"])

    lines = [
        f"--- CONTEXTO EDITORIAL DINÁMICO (RECICLADO: {state.get('last_recycled_at', '')[:10]}) ---",
        f"FASE ACTIVA: {cfg['name']} ({cfg['description']})",
        f"DIAS PARA EL 19 DE NOVIEMBRE: {state.get('days_to_launch', 0)}",
        f"ENFOQUE AFILIADOS ACTUAL: {cfg['target_affiliate_focus']}",
        f"TEMAS PRIORITARIOS HOY: {', '.join(state.get('active_primary_topics', []))}",
        f"TEMAS OBSOLETOS O VETADOS: {', '.join(state.get('retired_topics', []))}",
        f"KEYWORDS EMERGENTES ACTIVAS: {', '.join(state.get('emerging_keywords_pool', [])[:8])}"
    ]
    return "\n".join(lines)


def format_recycler_telegram_message(state: Dict[str, Any]) -> str:
    """Formatea el estado del reciclaje para la interfaz de Telegram."""
    dt_str = state.get("last_recycled_at", "")[:16].replace("T", " ")
    phase_name = state.get("phase_name", "")
    days = state.get("days_to_launch", 0)
    topics = state.get("active_primary_topics", [])[:5]
    emerging = state.get("emerging_keywords_pool", [])[:6]
    retired = state.get("retired_topics", [])[:4]

    msg = (
        "🔄 *ESTADO DEL CONOCIMIENTO RECICLADO DE GTA 6*\n"
        + ("═" * 38) + "\n\n"
        f"📌 *Fase Activa:* `{phase_name}`\n"
        f"⏳ *Cuenta Atrás:* ¡{days} días para el 19 de noviembre!\n"
        f"⏱️ _Último Reciclaje: {dt_str} UTC_\n\n"
        "🔥 *Temas en Máxima Prioridad Hoy:*\n"
    )
    for t in topics:
        msg += f"  • `{t}`\n"

    msg += "\n⚡ *Keywords Emergentes en el Radar:*\n`"
    msg += ", ".join(emerging) + "`\n\n"

    msg += "🚫 *Temas Descartados / Obsoletos:*\n`"
    msg += ", ".join(retired) + "`\n\n"

    msg += "🎯 _El pipeline ajusta los prompts y las búsquedas automáticamente a medida que el juego evoluciona._"
    return msg


if __name__ == "__main__":
    print("[*] Ejecutando reciclaje de conocimiento dinámico...")
    updated = recycle_knowledge(force=True)
    print(f"[✓] Fase activa: {updated['phase_name']}")
    print(f"[✓] Días para el estreno: {updated['days_to_launch']}")
    print(f"[✓] Temas prioritarios: {updated['active_primary_topics']}")
    print(f"[✓] Keywords emergentes: {updated['emerging_keywords_pool'][:8]}")

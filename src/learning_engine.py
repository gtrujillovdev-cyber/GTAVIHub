import os
import re
import sys
import json
import time
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import BASE_DIR, DATA_DIR, GEMINI_MODEL
from .translator import get_gemini_client, clean_srt_response
from .channels import list_monitored_channels

PLAYBOOK_FILE = DATA_DIR / "viral_playbook.json"
OWN_CHANNEL_URL = "https://www.youtube.com/channel/UCBOl2KuaHEoUWYWJqb7ID9Q/videos"

DEFAULT_PLAYBOOK = {
    "version": 1,
    "last_updated": "2026-10-29T00:00:00",
    "channel_diagnosis": {
        "identified_flaws": [
            "Títulos saturados de clichés repetitivos ('¡FILTRACIÓN ÉPICA!', '¡BRUTAL!').",
            "Duración uniforme excesiva (~51s) que reduce la tasa de retención y finalización.",
            "Contenido centrado en GTA Online en lugar de novedades exclusivas de GTA 6."
        ],
        "average_views": 1.0,
        "completion_rate_estimate": "Baja (< 45%)"
    },
    "competitor_benchmarks": {
        "winning_duration_range": [18, 28],
        "key_growth_drivers": [
            "Curiosidades insólitas de físicas y mapa (ej. físicas de agua, colisiones, IA de NPCs).",
            "Cruces virales de cultura pop y streamers (ej. parodia South Park, IlloJuan, Xokas).",
            "Ganchos en 2 líneas contrastadas (Blanco + Amarillo Neón) con lectura instantánea."
        ]
    },
    "active_heuristics": {
        "winning_title_templates": [
            "¿SABÍAS ESTO DE {TOPIC}? 😱 [DETALLE OCULTO] #GTA6",
            "{ENTITY} RECREA EL GAMEPLAY DE {TOPIC} 💀 #GTA6",
            "¡EL SECRETO MEJOR GUARDADO DE {TOPIC}! 🔍🔥 #GTA6",
            "LAS FÍSICAS DE {TOPIC} NO TIENEN NINGÚN SENTIDO 🤯 #GTA6",
            "¿POR QUÉ ROCKSTAR OCULTÓ ESTO EN {TOPIC}? 🚨 #GTA6"
        ],
        "winning_hook_templates": [
            "Line 1: SUJETO O CONTEXTO | Line 2: IMPACTO O REVELACIÓN",
            "¿TE DIJISTE CUENTA DE ESTO? 🤯",
            "ESTO CAMBIA TODO EN GTA 6 💀",
            "EL DETALLE QUE NADIE VIO 🔍"
        ],
        "optimal_duration_seconds": 24,
        "forbidden_cliches": [
            "FILTRACIÓN ÉPICA", "FILTRACIÓN MORTAL", "BRUTAL", "ALERTA MUNDIAL", "CASAS DE GTA ONLINE"
        ]
    }
}

def load_viral_playbook() -> Dict[str, Any]:
    """Carga el playbook de optimización continua persistido en disco."""
    if not PLAYBOOK_FILE.exists():
        save_viral_playbook(DEFAULT_PLAYBOOK)
        return DEFAULT_PLAYBOOK
    try:
        with open(PLAYBOOK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Learning Engine] Error cargando {PLAYBOOK_FILE}: {e}")
        return DEFAULT_PLAYBOOK

def save_viral_playbook(data: Dict[str, Any]) -> bool:
    """Guarda el playbook de optimización continua en data/viral_playbook.json."""
    try:
        data["last_updated"] = datetime.now().isoformat()
        with open(PLAYBOOK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Learning Engine] Error guardando {PLAYBOOK_FILE}: {e}")
        return False

def get_playbook_context_for_prompt() -> str:
    """
    Genera un bloque de instrucciones dinámicas inyectables en los prompts de Gemini
    basado en las lecciones reales aprendidas de nuestro canal y los competidores.
    """
    pb = load_viral_playbook()
    heur = pb.get("active_heuristics", {})
    templates = heur.get("winning_title_templates", [])
    hooks = heur.get("winning_hook_templates", [])
    forbidden = heur.get("forbidden_cliches", [])

    lines = [
        "--- DIRECTRICES APRENDIDAS DEL CANAL (OPTIMIZACIÓN CONTINUA) ---",
        "1. ESTRUCTURAS DE TÍTULO COMPROBADAS CON MAYOR RETENCIÓN Y CTR:",
    ]
    for t in templates[:4]:
        lines.append(f"   • {t}")

    lines.append("2. GANCHOS SUPERIORES (0-2.5s) DE MÁXIMO IMPACTO VISUAL:")
    for h in hooks[:3]:
        lines.append(f"   • {h}")

    if forbidden:
        lines.append("3. PALABRAS Y CLICHÉS PROHIBIDOS (HAN FRACASADO EN NUESTRO CANAL):")
        lines.append(f"   ❌ Evita estrictamente: {', '.join(forbidden)}")

    lines.append("4. REGLA EDITORIAL: Enfócate en la curiosidad concreta y la acción inmediata, no en adjetivos vacíos.")
    lines.append("-----------------------------------------------------------------")
    return "\n".join(lines)

def generate_hook_card_texts(title: str, topic: str = "") -> tuple:
    """
    Genera dos líneas de texto de gancho superior (Línea 1 en blanco, Línea 2 en amarillo neón)
    basado en las heurísticas activas del playbook.
    """
    t_lower = title.lower()

    if any(k in t_lower for k in ["south park", "southpark"]):
        return ("SOUTH PARK LO HIZO", "¡PARODIA A GTA 6! 💀")
    elif any(k in t_lower for k in ["fisica", "física", "water", "agua", "rage"]):
        return ("FÍSICAS HIPERREALISTAS", "¡RAGE 9 AL LÍMITE! 🌊")
    elif any(k in t_lower for k in ["secreto", "secret", "easter egg"]):
        return ("EL SECRETO QUE NADIE VIO", "¡DESCUBIERTO EN EL MAPA! 🔍")
    elif any(k in t_lower for k in ["mision", "misión", "gameplay", "prologo"]):
        return ("GAMEPLAY EXCLUSIVO", "¡PRIMERA MISIÓN REAL! 🔥")
    elif any(k in t_lower for k in ["policia", "policía", "5 estrellas"]):
        return ("NIVEL 5 ESTRELLAS", "¡PERSECUCIÓN EXTREMA! 🚨")
    elif any(k in t_lower for k in ["comparativa", "gta 5", "versus"]):
        return ("COMPARATIVA DIRECTA", "¿CUÁL ES MEJOR? ⚔️")
    
    # Fallback general
    clean = re.sub(r"[#\[\].\-:!¡?¿]", "", title).strip()
    words = clean.split()
    if len(words) >= 4:
        l1 = " ".join(words[:2]).upper()[:24]
        l2 = " ".join(words[2:5]).upper()[:22]
        return (l1, l2)
    return ("¿SABÍAS ESTO?", "¡DETALLE OCULTO! 😱")

def fetch_own_channel_insights(limit: int = 8) -> List[Dict[str, Any]]:
    """
    Rastrea las métricas públicas de nuestros vídeos subidos a YouTube.
    Combina YouTube Data API (si token está disponible) y fallback robusto con yt-dlp.
    """
    # 1. Intentar YouTube Data API
    try:
        from .youtube_analytics import fetch_recent_videos
        api_videos = fetch_recent_videos(limit=limit)
        if api_videos:
            return api_videos
    except Exception:
        pass

    # 2. Fallback autónomo vía yt-dlp (cero dependencias de tokens de Google)
    try:
        res = subprocess.run([
            sys.executable, "-m", "yt_dlp",
            "--no-check-certificates",
            "--flat-playlist",
            "--print", "%(id)s\t%(title)s\t%(view_count)s\t%(duration)s",
            "-I", f"1:{limit}",
            OWN_CHANNEL_URL
        ], capture_output=True, text=True, timeout=25)

        videos = []
        for line in res.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                vid_id = parts[0].strip()
                title = parts[1].strip()
                try:
                    views = int(parts[2]) if len(parts) > 2 and parts[2] not in ("NA", "") else 0
                except ValueError:
                    views = 0
                try:
                    dur = float(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0.0
                except ValueError:
                    dur = 0.0

                videos.append({
                    "id": vid_id,
                    "title": title,
                    "views": views,
                    "duration": dur,
                    "url": f"https://youtu.be/{vid_id}"
                })
        return videos
    except Exception as e:
        print(f"[Learning Engine] Error rastreando canal propio: {e}")
        return []

def fetch_competitor_viral_benchmarks(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Extrae los vídeos más virales de la competencia en las últimas horas/días
    para analizar sus fórmulas de éxito y patrones de retención.
    """
    from .viral_discovery import DEFAULT_VIRAL_QUERIES

    benchmarks = []
    # Usar las 2 consultas principales para no saturar CPU
    sample_queries = DEFAULT_VIRAL_QUERIES[:2]

    for q in sample_queries:
        try:
            res = subprocess.run([
                sys.executable, "-m", "yt_dlp",
                "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(view_count)s\t%(duration)s",
                "-I", "1:6",
                q
            ], capture_output=True, text=True, timeout=20)

            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip()
                    try:
                        views = int(parts[2]) if len(parts) > 2 and parts[2] not in ("NA", "") else 0
                    except ValueError:
                        views = 0
                    try:
                        dur = float(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0.0
                    except ValueError:
                        dur = 0.0

                    if views > 5000:
                        benchmarks.append({
                            "id": vid_id,
                            "title": title,
                            "views": views,
                            "duration": dur,
                            "url": f"https://youtu.be/{vid_id}"
                        })
        except Exception:
            continue

    # Ordenar por visualizaciones descendentes
    benchmarks.sort(key=lambda x: x["views"], reverse=True)
    return benchmarks[:limit]

def run_self_learning_cycle() -> Dict[str, Any]:
    """
    Ejecuta el ciclo completo de auto-perfeccionamiento:
    1. Audita los vídeos propios del canal.
    2. Rastrea los líderes virales del sector.
    3. Gemini Flash sintetiza errores propios y clona heurísticas ganadoras.
    4. Actualiza data/viral_playbook.json para las futuras subidas.
    """
    print("[*] [Learning Engine] Iniciando ciclo de auto-perfeccionamiento y benchmark...")

    own_videos = fetch_own_channel_insights(limit=6)
    competitors = fetch_competitor_viral_benchmarks(limit=8)

    # Contexto de rendimiento real (bucle de feedback 24h post-publicación)
    performance_context = ""
    try:
        from .performance_tracker import get_performance_context_for_playbook
        performance_context = get_performance_context_for_playbook()
    except Exception:
        pass

    perf_section = f"RENDIMIENTO REAL DE NUESTROS ÚLTIMOS VÍDEOS PUBLICADOS (FEEDBACK 24H):\n{performance_context}\n" if performance_context else ""

    client = get_gemini_client()

    prompt = f"""Actúa como el Director de Analítica de Retención Algorítmica en YouTube Shorts y TikTok especializado en Gaming y GTA 6.

OBJETIVO:
Analiza los datos reales de nuestro canal (GTA VI Hub Spain) comparados con los vídeos virales de los líderes del sector de esta semana.
Detecta fallos en nuestro estilo, identifica qué fórmulas están funcionando a los competidores, y genera una estrategia de auto-perfeccionamiento.

DATOS DE NUESTRO CANAL (VÍDEOS SUBIDOS Y VISUALIZACIONES):
{json.dumps(own_videos, indent=2, ensure_ascii=False) if own_videos else "Canal recién arrancado con ~1-2 vistas por vídeo."}

DATOS DE LOS COMPETIDORES VIRALES (>10K - 500K VISTAS):
{json.dumps(competitors, indent=2, ensure_ascii=False) if competitors else "Competidores con vídeos de 18-28s basados en detalles específicos de físicas, IlloJuan y parodias."}

{perf_section}
REGLAS DE ANÁLISIS:
1. Autocrítica: Señala por qué nuestros títulos y duraciones no están consiguiendo retención (ej. clichés repetitivos '¡FILTRACIÓN ÉPICA!', duraciones de 51s demasiado largas para bucle, falta de misterio específico).
2. Benchmarking: Extrae exactamente qué hace que los vídeos de los competidores funcionen (duraciones de 18-28s, títulos de intriga que no revelan todo de golpe, humor/streamers).
3. Auto-adaptación: Propón 5 plantillas de títulos virales, 3 estructuras de gancho visual (0-2.5s) y una lista de términos prohibidos.

Devuelve tu respuesta EXACTAMENTE en este formato JSON (sin texto extra fuera de las llaves):
{{
  "channel_diagnosis": {{
    "identified_flaws": ["Fallo 1...", "Fallo 2..."],
    "average_views": 1.5,
    "completion_rate_estimate": "Baja"
  }},
  "competitor_benchmarks": {{
    "winning_duration_range": [18, 28],
    "key_growth_drivers": ["Factor 1...", "Factor 2..."]
  }},
  "active_heuristics": {{
    "winning_title_templates": [
      "PLANTILLA 1 CON {{TOPIC}} Y EMOJIS #GTA6",
      "PLANTILLA 2 CON {{ENTITY}} Y {{TOPIC}} #GTA6",
      "PLANTILLA 3 CON {{TOPIC}} #GTA6",
      "PLANTILLA 4 CON {{TOPIC}} #GTA6",
      "PLANTILLA 5 CON {{TOPIC}} #GTA6"
    ],
    "winning_hook_templates": [
      "Line 1: ... | Line 2: ...",
      "GANCHO 2...",
      "GANCHO 3..."
    ],
    "optimal_duration_seconds": 22,
    "forbidden_cliches": ["CLICHE 1", "CLICHE 2"]
  }},
  "executive_summary": "Resumen ejecutivo de 2 párrafos en español explicando qué hemos aprendido y cómo cambiaremos nuestra fórmula hoy."
}}
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        cleaned = clean_srt_response(response.text)
        analysis_data = json.loads(cleaned)

        # Persistir playbook
        playbook_payload = {
            "version": 2,
            "channel_diagnosis": analysis_data.get("channel_diagnosis", {}),
            "competitor_benchmarks": analysis_data.get("competitor_benchmarks", {}),
            "active_heuristics": analysis_data.get("active_heuristics", {}),
            "executive_summary": analysis_data.get("executive_summary", "")
        }
        save_viral_playbook(playbook_payload)
        print("[✓] [Learning Engine] Playbook de viralidad actualizado con éxito en data/viral_playbook.json.")
        return playbook_payload

    except Exception as e:
        print(f"[!] Error en auto-perfeccionamiento con Gemini: {e}")
        return load_viral_playbook()

def generate_learning_telegram_report(playbook: Dict[str, Any]) -> str:
    """Genera un reporte ejecutivo de alta calidad para Telegram con los aprendizajes del motor."""
    diag = playbook.get("channel_diagnosis", {})
    comp = playbook.get("competitor_benchmarks", {})
    heur = playbook.get("active_heuristics", {})
    summary = playbook.get("executive_summary", "")

    flaws_txt = "\n".join([f"• ❌ _{f}_" for f in diag.get("identified_flaws", [])[:3]])
    drivers_txt = "\n".join([f"• ⚡ _{d}_" for f in comp.get("key_growth_drivers", [])[:3] for d in [f]])
    templates_txt = "\n".join([f"• `{t}`" for t in heur.get("winning_title_templates", [])[:3]])
    forbidden_txt = ", ".join([f"`{c}`" for c in heur.get("forbidden_cliches", [])[:5]])

    msg = (
        "🧠 *MOTOR DE APRENDIZAJE Y AUTO-PERFECCIONAMIENTO*\n"
        + ("═" * 38) + "\n\n"
        + "🔍 *1. Diagnóstico de Nuestro Canal (Fallos Detectados):*\n"
        + f"{flaws_txt}\n\n"
        + "🎯 *2. Benchmarking (Qué Hacen los Líderes Virales):*\n"
        + f"• ⏱️ *Duración Óptima:* `{comp.get('winning_duration_range', [18, 28])[0]}` a `{comp.get('winning_duration_range', [18, 28])[1]} segundos` (fomenta el bucle continuo).\n"
        + f"{drivers_txt}\n\n"
        + "🧬 *3. Nuevas Fórmulas Asimiladas en el Algoritmo:*\n"
        + f"{templates_txt}\n\n"
        + f"🚫 *Clichés Prohibidos Descartados:* {forbidden_txt}\n\n"
        + "📊 *4. Resumen Estratégico:*\n"
        + f"{summary or 'El motor ha reconfigurado los pesos editoriales para replicar los factores de retención de los vídeos líderes.'}\n\n"
        + "✅ _El Playbook se ha inyectado automáticamente en el pipeline de generación._"
    )
    return msg

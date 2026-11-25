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
OWN_CHANNEL_URL = "https://www.youtube.com/@gtavihubextra/shorts"

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
            "¿TE DISTE CUENTA DE ESTE DETALLE EN {TOPIC}? 🔍 #GTA6",
            "ASÍ REACCIONA LA IA CUANDO HACES ESTO EN {TOPIC} 🤯 #GTA6",
            "COMPARATIVA REAL: RDR2 VS {TOPIC} AL LÍMITE 🔥 #GTA6",
            "LO QUE NADIE VIO EN ESTA ESCENA DE {TOPIC} 👀 #GTA6"
        ],
        "winning_hook_templates": [
            "Line 1: SUJETO O CONTEXTO | Line 2: IMPACTO O REVELACIÓN",
            "MIRA ESTE DETALLE OCULTO 🔍",
            "LA REACCIÓN DE LOS NPCs 🤯",
            "RDR2 VS GTA 6 AL DETALLE 🔥"
        ],
        "optimal_duration_seconds": 24,
        "forbidden_cliches": [
            "FILTRACIÓN ÉPICA", "FILTRACIÓN MORTAL", "BRUTAL", "ALERTA MUNDIAL",
            "CASAS DE GTA ONLINE", "NO TIENEN NINGÚN SENTIDO", "NO TIENE NINGÚN SENTIDO"
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
        "   • Fiel 100% al dato real del clip (FPS, tamaño, mecánica o declaración concreta del creador).",
        "   • Prohibido copiar ejemplos o inventar mecánicas ajenas (nada de RDR2, NPCs ni cámaras si no salen en el clip).",
        "2. GANCHOS SUPERIORES (0-4.0s) DE MÁXIMO IMPACTO VISUAL:",
        "   • Línea 1 (Blanco): Contexto claro y directo | Línea 2 (Amarillo): El dato o revelación exacta del clip.",
    ]

    if forbidden:
        lines.append("3. PALABRAS Y CLICHÉS PROHIBIDOS (HAN FRACASADO EN NUESTRO CANAL):")
        lines.append(f"   ❌ Evita estrictamente: {', '.join(forbidden)}")

    lines.append("4. REGLA EDITORIAL: Enfócate en la curiosidad concreta y la fidelidad al fragmento real, sin alucinar ni usar adjetivos vacíos.")
    lines.append("-----------------------------------------------------------------")
    return "\n".join(lines)

def _truncate_word_boundary(text: str, max_len: int) -> str:
    """Recorta texto en límite exacto de palabra sin cortar palabras a la mitad."""
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    cut = clean[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip()


def generate_hook_card_texts(title: str, topic: str = "") -> tuple:
    """
    Genera dos líneas de texto de gancho superior en ESPAÑOL (Línea 1 en blanco, Línea 2 en amarillo neón)
    con corte limpio en límite de palabra (<= 21 caracteres por línea) y enfoque específico al frame 0.
    """
    t_lower = (title or "").lower()

    if any(k in t_lower for k in ["south park", "southpark"]):
        return ("SOUTH PARK PARODIA", "EL ESTRENO DE GTA 6 💀")
    elif any(k in t_lower for k in ["fisica", "física", "physics", "water", "agua", "rage", "npc", "density", "densidad"]):
        return ("EL MOTOR RAGE 9", "REACCIONA AL ENTORNO 🌊")
    elif any(k in t_lower for k in ["screenshot", "screenshots", "image", "images", "imágenes", "imagenes", "pantallazo"]):
        return ("CAPTURA INÉDITA", "DETALLES DE LEONIDA 🔍")
    elif any(k in t_lower for k in ["graphic", "graphics", "gráfico", "grafico", "visual", "ray tracing", "4k", "ps5"]):
        return ("ANÁLISIS TÉCNICO", "RENDIMIENTO EN GTA 6")
    elif any(k in t_lower for k in ["compar", "versus", " vs ", "evoluc", "difference", "diferencia"]):
        return ("COMPARATIVA REAL", "DIFERENCIA EN PANTALLA ⚔️")
    elif any(k in t_lower for k in ["radio", "music", "música", "soundtrack", "song"]):
        return ("RADIOS DE VICE CITY", "BANDA SONORA GTA 6")
    elif any(k in t_lower for k in ["map", "mapa", "leonida", "vice city", "mountain", "hotel", "location"]):
        return ("EXPLORA LEONIDA", "ZONAS DEL MAPA 🗺️")
    elif any(k in t_lower for k in ["secreto", "secret", "easter egg", "detail", "detalle", "hidden"]):
        return ("DETALLE OCULTO", "EN ESTE FRAGMENTO")
    elif any(k in t_lower for k in ["mision", "misión", "gameplay", "prologo", "feature"]):
        return ("GAMEPLAY EN BRUTO", "ACCIÓN EN VICE CITY 🔥")
    elif any(k in t_lower for k in ["policia", "policía", "police", "chase", "persecuci", "wanted", "5 estrellas"]):
        return ("NIVEL 5 ESTRELLAS", "PERSECUCIÓN POLICIAL 🚨")
    elif any(k in t_lower for k in ["trailer", "tráiler", "launch", "pre-order", "cover art"]):
        return ("AVANCE OFICIAL", "NOVEDAD EN GTA 6")
    elif any(k in t_lower for k in ["free", "gratis", "money", "dinero", "$", "cash", "rolls royce", "supercar"]):
        return ("EN ESTA UBICACIÓN", "DINERO Y COCHE GRATIS 🤑")
    elif any(k in t_lower for k in ["tip", "tips", "trick", "guide", "how to", "best weapon", "best car", "where to find",
                                      "guia", "guía", "consejo", "mejor arma", "mejor coche", "como conseguir",
                                      "legendary", "legendaria", "rare", "raro", "unlock", "desbloquear"]):
        return ("GUÍA DE UBICACIÓN", "CONSIGUE ESTO EN GTA 6")

    # Fallback estricto en español con corte en límite de palabra
    is_spanish = any(w in t_lower for w in [" de ", " el ", " la ", " los ", " las ", " en ", " por ", " con ", " que "])
    if is_spanish:
        clean = re.sub(r"[#\[\].\-:!¡?¿]", "", title).strip()
        words = clean.split()
        if len(words) >= 4:
            l1 = _truncate_word_boundary(" ".join(words[:3]).upper(), 21)
            l2 = _truncate_word_boundary(" ".join(words[3:6]).upper(), 20)
            if l1 and l2:
                return (l1, l2)
    return ("CLAVES DE GTA 6", "LO QUE MUESTRA EL CLIP")

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
        from .translator import generate_content_with_retry
        response = generate_content_with_retry(
            client=client,
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


def sync_tiktok_insights_to_playbook(username: str = "gtavihubextra", force: bool = False) -> Dict[str, Any]:
    """
    Extrae métricas reales de TikTok (vistas + likes por vídeo), identifica los ángulos
    ganadores y perdedores reales, actualiza data/viral_playbook.json y sincroniza
    tiktok_views/tiktok_likes en data/performance_records.json.
    """
    from .youtube_analytics import fetch_tiktok_overview

    pb = load_viral_playbook()
    diag = pb.setdefault("channel_diagnosis", {})
    prev_snap = diag.get("tiktok_snapshot") or {}
    if not force and prev_snap.get("synced_at"):
        try:
            prev_dt = datetime.fromisoformat(str(prev_snap["synced_at"]))
            if (datetime.now() - prev_dt).total_seconds() < 4 * 3600:
                return {"ok": True, "cached": True, "snapshot": prev_snap}
        except Exception:
            pass

    ov = fetch_tiktok_overview(username)
    if not ov or not ov.get("recent_videos"):
        return {"ok": False, "reason": "Sin datos recientes de TikTok"}

    videos = ov["recent_videos"]
    scored = []
    for v in videos:
        views = int(v.get("views") or 0)
        likes = int(v.get("likes") or 0)
        ratio = (likes / views) if views > 0 else 0.0
        scored.append({**v, "views": views, "likes": likes, "like_ratio": round(ratio, 4)})

    scored.sort(key=lambda x: (x["views"], x["likes"]), reverse=True)
    winners = [v for v in scored if v["views"] >= 600][:4]
    losers = [v for v in scored if v["views"] < 150]

    stopwords = {"gta", "6", "vi", "en", "de", "la", "el", "y", "a", "los", "las", "que", "con", "por", "para", "del", "qué", "te", "es", "lo", "más"}
    win_kws: List[str] = []
    for w in winners:
        clean = re.sub(r"[^\wáéíóúñü\s]", " ", (w.get("title") or "").lower())
        for tok in clean.split():
            if len(tok) >= 4 and tok not in stopwords and tok not in win_kws:
                win_kws.append(tok)
    for core in ("oculta", "oculto", "secreto", "leonida", "arma", "legendaria", "ps5", "comparativa"):
        if core not in win_kws:
            win_kws.append(core)

    avoid_kws: List[str] = []
    for l_item in losers:
        clean_l = re.sub(r"[^\wáéíóúñü\s]", " ", (l_item.get("title") or "").lower())
        for tok in clean_l.split():
            if len(tok) >= 4 and tok not in stopwords and tok not in win_kws and tok not in avoid_kws:
                avoid_kws.append(tok)

    heur = pb.setdefault("active_heuristics", {})
    plat_alphas = pb.setdefault("platform_alphas", {})
    plat_alphas["tiktok"] = {
        "angle_label": "Secretos Visuales, Curiosidades In-Game y Gameplay Directo (0.0s)",
        "priority_keywords": win_kws[:12],
        "avoid_keywords": avoid_kws[:8],
        "top_winner": winners[0] if winners else None,
        "avg_views": round(int(ov.get("views") or 0) / max(len(videos), 1), 1),
        "followers": int(ov.get("followers") or 0),
        "synced_at": datetime.now().isoformat(),
    }
    plat_alphas.setdefault("instagram", {
        "angle_label": "Reels Narrados / Doblados con Estética Vice City 4K",
        "priority_keywords": ["secreto", "oculta", "detalle", "comparativa", "leonida"],
        "requires_voiceover": True,
    })

    # Solo pasar a avoid_keywords global palabras que NO hayan tenido éxito en YouTube (>=500 vistas)
    yt_protected_tokens = set()
    try:
        from .performance_tracker import _load_records
        for rec in _load_records():
            if int(rec.get("views_live") or 0) >= 500 or int(rec.get("views_24h") or 0) >= 500:
                clean_yt = re.sub(r"[^\wáéíóúñü\s]", " ", (rec.get("title") or "").lower())
                yt_protected_tokens.update(tok for tok in clean_yt.split() if len(tok) >= 4)
    except Exception:
        pass

    global_avoid = [kw for kw in avoid_kws if kw not in yt_protected_tokens]
    if global_avoid:
        heur["avoid_keywords"] = global_avoid[:8]
    elif "avoid_keywords" in heur:
        heur["avoid_keywords"] = [kw for kw in (heur.get("avoid_keywords") or []) if kw not in yt_protected_tokens]

    # Combinar keywords universales (TikTok + YouTube) sin pisar las de YouTube
    yt_kws = (plat_alphas.get("youtube") or {}).get("priority_keywords") or heur.get("priority_keywords") or []
    merged_global = []
    for kw in list(win_kws[:6]) + list(yt_kws[:6]):
        if kw not in merged_global:
            merged_global.append(kw)
    if merged_global:
        heur["priority_keywords"] = merged_global[:12]
    heur.setdefault("priority_angle_label", "Secretos/Objetos Ocultos en Leonida y Comparativas PS5 Pro")

    total_v = int(ov.get("views") or 0)
    total_l = int(ov.get("likes") or 0)
    tt_avg = round(total_v / max(len(videos), 1), 1)
    diag["tiktok_snapshot"] = {
        "username": username,
        "videos": len(videos),
        "total_views": total_v,
        "total_likes": total_l,
        "followers": int(ov.get("followers") or 0),
        "avg_views": tt_avg,
        "top_winner": winners[0] if winners else None,
        "bottom_losers": [{"title": l["title"][:60], "views": l["views"]} for l in losers[:3]],
        "synced_at": datetime.now().isoformat(),
    }
    # Calibrar average_views real desde performance_records (YouTube) + TikTok snapshot
    try:
        from .performance_tracker import _load_records
        yt_vals = [int(r.get("views_live") or 0) for r in _load_records() if r.get("views_live") is not None]
        if yt_vals:
            diag["average_views"] = round(sum(yt_vals) / len(yt_vals), 1)
        elif tt_avg > 0:
            diag["average_views"] = tt_avg
    except Exception:
        if tt_avg > 0:
            diag["average_views"] = tt_avg
    save_viral_playbook(pb)

    # Sincronizar vistas/likes reales de TikTok hacia performance_records.json
    try:
        from difflib import SequenceMatcher
        from .performance_tracker import _load_records, _save_records
        records = _load_records()
        updated_perf = 0
        for v in scored:
            v_norm = re.sub(r"[^a-z0-9áéíóúñ ]", "", (v.get("title") or "").lower()).strip()
            if not v_norm:
                continue
            best_rec = None
            best_sim = 0.0
            for rec in records:
                r_norm = re.sub(r"[^a-z0-9áéíóúñ ]", "", (rec.get("title") or "").lower()).strip()
                if not r_norm:
                    continue
                sim = SequenceMatcher(None, v_norm[:45], r_norm[:45]).ratio()
                if sim > best_sim:
                    best_sim = sim
                    best_rec = rec
            if best_rec is not None and best_sim >= 0.62:
                best_rec["tiktok_views"] = v["views"]
                best_rec["tiktok_likes"] = v["likes"]
                best_rec["tiktok_synced_at"] = datetime.now().isoformat()
                updated_perf += 1
        if updated_perf > 0:
            _save_records(records)
    except Exception:
        pass

    return {"ok": True, "snapshot": diag["tiktok_snapshot"], "priority_keywords": heur["priority_keywords"]}


def route_platforms_by_alpha(
    base_platforms: List[str],
    metadata: Dict[str, Any],
    creator_name: str = "",
) -> tuple[List[str], str]:
    """
    Enruta cada clip a las plataformas donde su formato tiene alfa real,
    garantizando siempre >= 1 plataforma destino y respetando cooldowns activos.
    """
    platforms = list(base_platforms or ["youtube", "tiktok", "instagram", "x"])
    if os.getenv("ENABLE_PLATFORM_ALPHA_ROUTING", "true").lower() not in ("true", "1", "yes"):
        return platforms, "Routing por alfa desactivado (todas las plataformas)."
    if len(platforms) <= 1:
        return platforms, "Lista única recibida."

    title_low = (metadata.get("title") or "").lower()
    creator_low = (creator_name or "").lower()
    combined = f"{title_low} {creator_low}"

    has_voiceover = bool(metadata.get("has_voiceover") or metadata.get("mode") in ("dub", "voice"))
    is_split = bool(metadata.get("is_transformed_visual"))
    is_secret = any(k in title_low for k in (
        "secret", "ocult", "arma", "legendaria", "detalle", "misterio", "easter",
        "curiosidad", "gratis", "dinero", "coche", "ubicacion", "ubicación", "free",
        "money", "location", "$"
    ))
    is_streamer = any(k in combined for k in ("willyrex", "danirep", "rubius", "illojuan", "thegrefg", "auron", "elxokas", "streamer", "reacción", "reaccion"))

    # 1. Alfa Universal (secretos, comparativas split o voz sin intro lenta de streamer): todas las redes
    if is_secret or is_split:
        return platforms, "Alfa Universal (secreto/comparativa): apto para todas las redes."

    # 2. Alfa YouTube-first (streamer hispano sin ángulo de secreto/split):
    # Evita quemar cuota diaria de TikTok si YouTube está disponible (no en cooldown).
    if is_streamer and "youtube" in platforms and "tiktok" in platforms:
        try:
            from .uploader import _is_youtube_upload_blocked_by_cooldown
            yt_blocked, _ = _is_youtube_upload_blocked_by_cooldown(metadata.get("title", ""), metadata.get("privacy", "public"))
        except Exception:
            yt_blocked = False
        if not yt_blocked:
            routed = [p for p in platforms if p != "tiktok"]
            return routed, "Alfa YouTube-first (streamer hispano): reservando TikTok para clips visuales directos."

    # 3. Alfa TikTok-first (gameplay puro mudo sin voz ni streamer ni comparativa):
    # Evita desplomes de 3-6 vistas en YouTube Shorts y lo envía a TikTok (+ Story IG).
    if (not has_voiceover) and (not is_streamer) and "tiktok" in platforms and "youtube" in platforms:
        routed = [p for p in platforms if p != "youtube"]
        return routed, "Alfa TikTok-first (gameplay mudo): evitando penalización de Shorts sin voz."

    return platforms, "Alfa Mixto: manteniendo plataformas elegibles."

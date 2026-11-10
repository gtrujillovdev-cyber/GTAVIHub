import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from .config import GEMINI_MODEL
from .translator import get_gemini_client, clean_srt_response, FALLBACK_GEMINI_MODELS
from .learning_engine import load_viral_playbook, generate_hook_card_texts
from .channels import get_processed_ids

def select_best_candidate_ai(
    candidates: List[Dict[str, Any]],
    launch_mode: bool = False,
    playbook: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Motor de Selección con IA (Gemini Flash):
    Analiza una lista de vídeos candidatos y selecciona el clip con el mayor potencial
    viral de engagement, evitando redundancia con vídeos ya procesados y aplicando
    las directrices del Playbook de Optimización Continua.
    
    En 'launch_mode' (Día del Estreno):
    - Prioriza la frescura inmediata (< 6-12 horas).
    - Maximiza la velocidad de visualización (views/hora).
    - Selecciona gameplay real, misiones clave y secretos de primer día.
    """
    if not candidates:
        return {}

    from .compliance_auditor import is_safe_rrss_candidate
    from .channels import filter_repetitive_candidates
    safe_candidates = []
    for c in candidates:
        safe, _, _ = is_safe_rrss_candidate(
            c.get("title", ""),
            uploader=c.get("uploader") or c.get("source_name", ""),
            duration_sec=float(c.get("duration") or 0.0),
            allow_long_clipping=bool(c.get("allow_long_clipping", False)),
            allow_official_commentary=bool(c.get("allow_official_commentary", False))
        )
        if safe:
            safe_candidates.append(c)
    candidates = filter_repetitive_candidates(safe_candidates)
    if not candidates:
        print("[AI Selector] Todos los candidatos fueron descartados por seguridad RRSS o anti-repetición.")
        return {}

    # Si solo hay un candidato, enriquecerlo y retornarlo
    if len(candidates) == 1:
        chosen = dict(candidates[0])
        l1, l2 = generate_hook_card_texts(chosen.get("title", ""))
        chosen["ai_selection"] = False
        chosen["ai_justification"] = "Único candidato disponible en la ronda."
        chosen["hook_line1"] = l1
        chosen["hook_line2"] = l2
        return chosen

    # Limitar a los 15 mejores según virality_score para la IA
    pool = candidates[:15]

    # Cargar playbook si no se suministró
    if playbook is None:
        playbook = load_viral_playbook()

    # Obtener historial reciente para evitar repetir temáticas
    recent_titles = []
    try:
        from .config import PROCESSED_FILE
        if PROCESSED_FILE.exists():
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                hist = json.load(f)
                recent_titles = [item.get("title", "") for item in hist[-8:] if item.get("title")]
    except Exception:
        recent_titles = []

    # Cargar radar de tráfico y contexto editorial reciclado en tiempo real
    traffic_radar_summary = {}
    dynamic_editorial_context = ""
    try:
        from .traffic_sentinel import get_latest_traffic_radar
        from .knowledge_recycler import get_current_editorial_context
        radar = get_latest_traffic_radar()
        traffic_radar_summary = {
            "top_youtube_search_intents": radar.get("top_search_intents", [])[:5],
            "breaking_news_topics": [n.get("title", "") for n in radar.get("breaking_news", [])[:4]],
            "hottest_keywords": radar.get("trending_keywords", [])[:8]
        }
        dynamic_editorial_context = get_current_editorial_context()
    except Exception:
        traffic_radar_summary = {}

    # Preparar resumen de candidatos para el prompt
    candidates_summary = []
    for idx, c in enumerate(pool):
        views = c.get("views") or 0
        like_count = c.get("like_count") or 0
        engagement_rate = round(like_count / views, 4) if views > 0 and like_count > 0 else None
        candidates_summary.append({
            "index": idx,
            "id": c.get("id"),
            "title": c.get("title"),
            "duration": c.get("duration"),
            "views": views,
            "views_per_hour": c.get("views_per_hour"),
            "hours_old": c.get("hours_old"),
            "velocity_vpd": c.get("velocity_vpd") or c.get("velocity"),
            "days_old": c.get("days_old"),
            "engagement_rate": engagement_rate,
            "source_count": c.get("source_count", 1),
            "uploader": c.get("uploader") or c.get("source_name", "Desconocido"),
            "base_score": c.get("score")
        })

    client = get_gemini_client()
    if client:
        try:
            mode_context = (
                "MODO: DÍA DEL ESTRENO (LAUNCH DAY 2026). Prioriza novedad absoluta, misiones iniciales, "
                "gameplay real, descubrimientos en el mapa y velocidad explosiva de vistas por hora."
                if launch_mode else
                "MODO: COBERTURA VIRAL DE ALTO IMPACTO (GTA 6 PURO). Prioriza clips con MÁXIMA VELOCIDAD ACTUAL (views_per_hour y hours_old <= 24), "
                "reacciones genuinas, desgloses de detalles, gameplay real y análisis técnicos RAGE 9. "
                "ESTRICTAMENTE PROHIBIDO: parodias, memes, clips de GTA 5 o rellenos viejos de semanas pasadas."
            )

            prompt = f"""Eres el Director de Estrategia de Contenidos y Algoritmos para 'GTA VI Hub Spain' (YouTube Shorts, TikTok, Instagram Reels).
{mode_context}
{dynamic_editorial_context}

OBJETIVO:
Analiza los siguientes {len(pool)} vídeos candidatos pre-filtrados y SELECCIONA EL MEJOR CLIP ABSOLUTO para conseguir visitas REALES ahora mismo.

CANDIDATOS:
{json.dumps(candidates_summary, indent=2, ensure_ascii=False)}

DEMANDA DE BÚSQUEDA Y TRÁFICO EN TIEMPO REAL (LO QUE INTERNET BUSCA AHORA MISMO):
{json.dumps(traffic_radar_summary, indent=2, ensure_ascii=False)}

VÍDEOS RECIENTES YA PUBLICADOS (EVITA REPETIR ESTAS TEMÁTICAS):
{json.dumps(recent_titles, indent=2, ensure_ascii=False)}

CRITERIOS EDITORIALES DE VICTORIA (PLAYBOOK VIRAL):
0. PRIORIDAD ABSOLUTA A EXPLOSIÓN EN ÚLTIMAS 24H (views_per_hour Y hours_old):
   - Prioriza al máximo vídeos con hours_old <= 24 y miles de views_per_hour: lanzamientos recién publicados por Rockstar Games (ej. 'Pre-Load Now', 'Launch Trailer', 'PS5 Features'), reacciones reales al nuevo tráiler, desgloses frame-a-frame de detalles ocultos y gameplay auténtico.
   - Elige vídeos con VOZ Y EMOCIÓN REAL de creadores top o tráilers de alto impacto visual frente a vídeos antiguos de baja tracción.
   - DESCARTAR tráileres antiguos de 2023 ('Trailer 1') y charlas lentas de radio/podcast sin ritmo visual.
1. VELOCIDAD VIRAL REAL (views_per_hour / velocity_vpd): Prioriza vídeos en ascenso vertical ahora mismo. Un vídeo de hace 5 horas con 50,000 views/hora vale 10x más que uno de hace 2 semanas.
2. MULTI-FUENTE (source_count > 1): Un vídeo detectado por múltiples fuentes/queries simultáneamente es una señal inequívoca de momento viral. Priorizarlo sobre candidatos únicos.
3. ENGAGEMENT REAL (engagement_rate): Ratio likes/vistas como proxy de distribución activa por el algoritmo. Un ratio > 0.02 indica audiencia comprometida.
4. ENGAGEMENT Y CURIOSIDAD: El vídeo debe provocar el deseo irrefrenable de comentar o ver hasta el final.
5. CERO CLICKBAIT FALSO: Descarta conceptos abstractos o mods antiguos. Solo contenido real y de impacto.
6. CONTENIDO 100% GTA 6 REAL: Prioriza clips con tracción real de vistas (demostraciones de RAGE 9, detalles del mapa de Leonida, mecánicas in-game, vehículos, comparativas con vida real). DESCALIFICAR AUTOMÁTICAMENTE cualquier parodia, meme, o gameplay de GTA 5.
7. GANCHO DE 2 LÍNEAS EN ESPAÑOL (OBLIGATORIO ESPAÑOL, NUNCA INGLÉS): Redacta dos líneas de titular afirmativo en ESPAÑOL (Línea 1 en blanco max 20 caracteres, Línea 2 en amarillo neón max 20 caracteres). PROHIBIDO usar signos de interrogación ('¿' o '?') en el gancho superior.
8. CERO LEAKS O FILTRACIONES ILEGALES (CUMPLIMIENTO ESTRICTO ANTI-DMCA): PROHIBIDO terminantemente seleccionar clips con código robado, filtraciones confidenciales de desarrollo de 2022 o marcas de debug. Prioriza análisis legítimos bajo Fair Use, comparativas gráficas, curiosidades de prensa y descubrimientos geográficos.

RESPONDE EXCLUSIVAMENTE CON UN OBJETO JSON VÁLIDO:
{{
  "selected_index": 0,
  "justification": "Explicación de por qué este clip es el ganador indiscutible frente a los otros.",
  "recommended_title": "TÍTULO VIRAL EN ESPAÑOL Y MAYÚSCULAS CON EMOJIS Y #GTA6",
  "hook_line1": "LÍNEA 1 EN ESPAÑOL",
  "hook_line2": "LÍNEA 2 EN ESPAÑOL",
  "audience_appeal": "Razón del gancho en la audiencia hispanohablante"
}}
"""

            from .translator import generate_content_with_retry
            response = generate_content_with_retry(client=client, contents=prompt)
            cleaned = clean_srt_response(response.text)
            decision = json.loads(cleaned)

            sel_idx = decision.get("selected_index", 0)
            if not isinstance(sel_idx, int) or sel_idx < 0 or sel_idx >= len(pool):
                sel_idx = 0

            chosen = dict(pool[sel_idx])
            chosen["ai_selection"] = True
            chosen["ai_justification"] = decision.get("justification", "Seleccionado por IA como el vídeo con mayor engagement.")
            chosen["recommended_title"] = decision.get("recommended_title", chosen.get("title"))
            chosen["hook_line1"] = decision.get("hook_line1", "").strip().upper()
            chosen["hook_line2"] = decision.get("hook_line2", "").strip().upper()
            chosen["audience_appeal"] = decision.get("audience_appeal", "")

            # Si la IA no generó ganchos válidos, usar el generador del playbook
            if not chosen["hook_line1"] or not chosen["hook_line2"]:
                l1, l2 = generate_hook_card_texts(chosen.get("title", ""))
                chosen["hook_line1"] = chosen["hook_line1"] or l1
                chosen["hook_line2"] = chosen["hook_line2"] or l2

            print(f"[AI Selector] Ganador seleccionado por IA: '{chosen.get('title')}'")
            print(f"             Justificación: {chosen['ai_justification']}")
            return chosen

        except Exception as e:
            print(f"[AI Selector] Advertencia: Error en evaluación con IA ({e}). Usando fallback heurístico.")

    # FALLBACK HEURÍSTICO ROBUSTO (penaliza charlas de radio/podcast lentas y premia espectáculo visual)
    def _visual_priority_score(item: Dict[str, Any]) -> float:
        base = float(item.get("score", 0))
        vph = float(item.get("views_per_hour") or 0.0)
        hours_old = float(item.get("hours_old") or 720.0)
        if vph >= 10000:
            base += 40.0
        elif vph >= 1000:
            base += 25.0
        elif vph >= 200:
            base += 12.0
        if hours_old <= 6:
            base += 25.0
        elif hours_old <= 24:
            base += 15.0
        elif hours_old > 168:
            base -= 20.0

        tl = (item.get("title") or "").lower()
        if any(k in tl for k in ("radio station", "podcast", "tier list", "unboxing")):
            base -= 25.0
        if any(k in tl for k in ("pre-load", "preload", "reaction", "reaccion", "reacciona", "breakdown", "details", "detalles", "physics", "rage 9", "graphics", "comparison", "gameplay", "trailer")):
            base += 15.0
        return base

    if launch_mode:
        sorted_pool = sorted(
            pool,
            key=lambda x: (
                -(x.get("views_per_hour") or x.get("velocity") or 0) - _visual_priority_score(x),
                x.get("hours_old") or x.get("days_old") or 999
            )
        )
    else:
        sorted_pool = sorted(pool, key=lambda x: -_visual_priority_score(x))

    chosen = dict(sorted_pool[0])
    l1, l2 = generate_hook_card_texts(chosen.get("title", ""))
    chosen["ai_selection"] = False
    chosen["ai_justification"] = "Seleccionado por máxima puntuación heurística de engagement."
    chosen["hook_line1"] = l1
    chosen["hook_line2"] = l2
    return chosen

import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from .config import GEMINI_MODEL
from .translator import get_gemini_client, clean_srt_response
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

    from .channels import is_strictly_gta6, is_official_or_reupload
    candidates = [c for c in candidates if is_strictly_gta6(c.get("title", ""))]
    candidates = [c for c in candidates if not is_official_or_reupload(c.get("title", ""), c.get("uploader", ""))]
    if not candidates:
        print("[AI Selector] Todos los candidatos fueron descartados (no GTA 6 o contenido oficial/reupload).")
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
                "MODO: COBERTURA VIRAL DE ALTO IMPACTO (GTA 6 PURO). Prioriza clips con ALTO VOLUMEN DE VISTAS, "
                "análisis técnicos de gráficos, físicas RAGE 9, secretos del mapa de Leonida, novedades confirmadas y filtraciones creíbles. "
                "ESTRICTAMENTE PROHIBIDO: parodias, memes, clips de GTA 5 o parodias tipo South Park."
            )

            prompt = f"""Eres el Director de Estrategia de Contenidos y Algoritmos para 'GTA VI Hub Spain' (YouTube Shorts, TikTok, Instagram Reels).
{mode_context}
{dynamic_editorial_context}

OBJETIVO:
Analiza los siguientes 15 vídeos candidatos pre-filtrados y SELECCIONA EL MEJOR CLIP ABSOLUTO para procesar y publicar ahora mismo.

CANDIDATOS:
{json.dumps(candidates_summary, indent=2, ensure_ascii=False)}

DEMANDA DE BÚSQUEDA Y TRÁFICO EN TIEMPO REAL (LO QUE INTERNET BUSCA AHORA MISMO):
{json.dumps(traffic_radar_summary, indent=2, ensure_ascii=False)}

VÍDEOS RECIENTES YA PUBLICADOS (EVITA REPETIR ESTAS TEMÁTICAS):
{json.dumps(recent_titles, indent=2, ensure_ascii=False)}

CRITERIOS EDITORIALES DE VICTORIA (PLAYBOOK VIRAL):
0. CERO METRAJE DEL TRÁILER DE 2023: DESCARTAR FULMINANTEMENTE cualquier corte o tráiler oficial antiguo de Rockstar Games (Trailer 1, 'Extended Look', o resubidas del teaser de 2023). La comunidad ya lo ha visto 500 millones de veces. Prioriza contenido fresco, streamers (reacciones/humor), análisis técnicos y descubrimientos reales.
1. VELOCIDAD VIRAL (velocity_vpd): Prioriza vídeos con alta velocidad de crecimiento (vistas/día). El algoritmo de YouTube distribuye activamente el contenido en ascenso explosivo.
2. MULTI-FUENTE (source_count > 1): Un vídeo detectado por múltiples fuentes/queries simultáneamente es una señal inequívoca de momento viral. Priorizarlo sobre candidatos únicos.
3. ENGAGEMENT REAL (engagement_rate): Ratio likes/vistas como proxy de distribución activa por el algoritmo. Un ratio > 0.02 indica audiencia comprometida.
4. ENGAGEMENT Y CURIOSIDAD: El vídeo debe provocar el deseo irrefrenable de comentar o ver hasta el final.
5. CERO CLICKBAIT FALSO: Descarta conceptos abstractos o mods antiguos. Solo contenido real y de impacto.
6. CONTENIDO 100% GTA 6 REAL: Prioriza clips con tracción real de vistas (demostraciones de RAGE 9, detalles del mapa de Leonida, mecánicas in-game, vehículos, comparativas con vida real). DESCALIFICAR AUTOMÁTICAMENTE cualquier parodia, meme, o gameplay de GTA 5.
7. GANCHO DE 2 LÍNEAS (AFIRMACIÓN DE IMPACTO, NUNCA PREGUNTAS): Redacta dos líneas de titular afirmativo (Línea 1 en blanco max 24 caracteres, Línea 2 en amarillo neón max 22 caracteres). PROHIBIDO usar signos de interrogación ('¿' o '?') en el gancho superior; debe ser una afirmación o alerta rotunda (ej. 'FÍSICAS RAGE 9' / 'TORNADOS EXTREMOS' o 'DETALLE OCULTO' / 'SECRETOS DE LEONIDA').

RESPONDE EXCLUSIVAMENTE CON UN OBJETO JSON VÁLIDO:
{{
  "selected_index": 0,
  "justification": "Explicación de por qué este clip es el ganador indiscutible frente a los otros.",
  "recommended_title": "TÍTULO VIRAL EN MAYÚSCULAS CON EMOJIS Y #GTA6",
  "hook_line1": "LÍNEA 1 CORTA",
  "hook_line2": "LÍNEA 2 IMPACTANTE",
  "audience_appeal": "Razón del gancho en la audiencia hispanohablante"
}}
"""

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
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

    # FALLBACK HEURÍSTICO ROBUSTO
    # Ordenar por score base; en launch_mode dar prioridad extrema a velocity y frescura
    if launch_mode:
        sorted_pool = sorted(
            pool,
            key=lambda x: (
                -(x.get("velocity") or 0) * 2 - x.get("score", 0),
                x.get("days_old") or 999
            )
        )
    else:
        sorted_pool = sorted(pool, key=lambda x: -x.get("score", 0))

    chosen = dict(sorted_pool[0])
    l1, l2 = generate_hook_card_texts(chosen.get("title", ""))
    chosen["ai_selection"] = False
    chosen["ai_justification"] = "Seleccionado por máxima puntuación heurística de engagement."
    chosen["hook_line1"] = l1
    chosen["hook_line2"] = l2
    return chosen

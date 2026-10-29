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

    from .channels import is_strictly_gta6
    candidates = [c for c in candidates if is_strictly_gta6(c.get("title", ""))]
    if not candidates:
        print("[AI Selector] Todos los candidatos fueron descartados por no ser estrictamente de GTA 6.")
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

    # Limitar a los 10 mejores según virality_score para la IA
    pool = candidates[:10]

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

    # Preparar resumen de candidatos para el prompt
    candidates_summary = []
    for idx, c in enumerate(pool):
        candidates_summary.append({
            "index": idx,
            "id": c.get("id"),
            "title": c.get("title"),
            "duration": c.get("duration"),
            "views": c.get("views"),
            "velocity": c.get("velocity"),
            "days_old": c.get("days_old"),
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
                "MODO: COBERTURA VIRAL CONTINUA. Prioriza parodias de impacto cultural (ej. South Park), "
                "físicas RAGE 9 increíbles, secretos y debates que polaricen a la comunidad."
            )

            prompt = f"""Eres el Director de Estrategia de Contenidos y Algoritmos para 'GTA VI Hub Spain' (YouTube Shorts, TikTok, Instagram Reels).
{mode_context}

OBJETIVO:
Analiza los siguientes 10 vídeos candidatos pre-filtrados y SELECCIONA EL MEJOR CLIP ABSOLUTO para procesar y publicar ahora mismo.

CANDIDATOS:
{json.dumps(candidates_summary, indent=2, ensure_ascii=False)}

VÍDEOS RECIENTES YA PUBLICADOS (EVITA REPETIR ESTAS TEMÁTICAS):
{json.dumps(recent_titles, indent=2, ensure_ascii=False)}

CRITERIOS EDITORIALES DE VICTORIA (PLAYBOOK VIRAL):
1. ENGAGEMENT Y CURIOSIDAD: El vídeo debe provocar el deseo irrefrenable de comentar o ver hasta el final.
2. CERO CLICKBAIT FALSO: Descarta conceptos abstractos o mods antiguos. Solo contenido real y de impacto.
3. CULTURA POP & VIRALIDAD: Las parodias virales (como la de South Park) y las demostraciones técnicas de físicas tienen altísima retención.
4. GANCHO DE 2 LÍNEAS: Redacta dos líneas de gancho superiores (Línea 1 en blanco max 26 caracteres, Línea 2 en amarillo neón max 22 caracteres).

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

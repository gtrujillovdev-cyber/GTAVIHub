"""
story_scheduler.py — Engranaje Autónomo de Publicación y Rotación de Historias
Coordina la publicación equilibrada de Historias (70% Noticias/Gameplay vs 30% Ofertas)
respetando los límites de frecuencia de los algoritmos (máximo 1-2 historias/día).
"""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from .config import BASE_DIR, OUTPUT_DIR
from .story_generator import (
    generate_clean_product_story,
    build_hardware_deal_story,
    publish_story_to_instagram,
    PRODUCTS_DIR,
    ASSETS_DIR
)

logger = logging.getLogger("story_scheduler")

DATA_DIR = BASE_DIR / "data"
STORIES_STATE_FILE = DATA_DIR / "stories_state.json"

MAX_STORIES_PER_DAY = 2
MIN_HOURS_BETWEEN_STORIES = 4

# Catálogo rotativo de productos para historias de afiliados (30% de la cuota)
ROTATING_PRODUCTS = [
    "volante_logitech_g29",
    "ssd_ps5_2tb",
    "ps5_pro",
    "pulse_headset",
    "dualsense_controller"
]

def load_stories_state() -> Dict[str, Any]:
    """Carga el estado de publicación y rotación de historias."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORIES_STATE_FILE.exists():
        return {
            "last_published": None,
            "today_date": None,
            "today_count": 0,
            "last_product_idx": -1,
            "history": []
        }
    try:
        with open(STORIES_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error leyendo stories_state.json: {e}")
        return {
            "last_published": None,
            "today_date": None,
            "today_count": 0,
            "last_product_idx": -1,
            "history": []
        }

def save_stories_state(state: Dict[str, Any]) -> None:
    """Persiste el estado de historias en data/stories_state.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(STORIES_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando stories_state.json: {e}")

def can_publish_story(force: bool = False) -> Tuple[bool, str]:
    """
    Comprueba si se cumplen las reglas anti-spam y rate-limits del algoritmo:
    - Máximo 2 historias al día.
    - Mínimo 4 horas de descanso entre publicaciones.
    """
    if force:
        return True, "Publicación forzada por usuario o prueba."

    state = load_stories_state()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Reset diario de contador
    if state.get("today_date") != today_str:
        state["today_date"] = today_str
        state["today_count"] = 0
        save_stories_state(state)

    if state.get("today_count", 0) >= MAX_STORIES_PER_DAY:
        return False, f"Límite diario alcanzado ({MAX_STORIES_PER_DAY} historias hoy). Esperando al siguiente día."

    last_pub = state.get("last_published")
    if last_pub:
        try:
            last_dt = datetime.fromisoformat(last_pub)
            elapsed = datetime.now(timezone.utc) - last_dt
            if elapsed < timedelta(hours=MIN_HOURS_BETWEEN_STORIES):
                rem_mins = int((timedelta(hours=MIN_HOURS_BETWEEN_STORIES) - elapsed).total_seconds() / 60)
                return False, f"Descanso entre historias activo ({rem_mins} minutos restantes para evitar sobrecargar)."
        except Exception:
            pass

    return True, "Listo para publicar historia."

def get_next_story_type() -> str:
    """
    Determina si la próxima historia debe ser de contenido/gameplay (70%)
    o de producto/oferta (30%).
    """
    state = load_stories_state()
    history = state.get("history", [])
    if not history:
        return "content"
    
    # Comprobar las últimas 3 historias
    recent_types = [h.get("type") for h in history[-3:]]
    if "product" not in recent_types:
        return "product"
    return "content"

def build_next_rotating_deal_story() -> Tuple[Path, str, str, str]:
    """
    Selecciona el siguiente producto de la rueda y genera su historia cinemática limpia.
    Retorna: (ruta_imagen, url_afiliado, caption, product_key)
    """
    state = load_stories_state()
    curr_idx = state.get("last_product_idx", -1)
    next_idx = (curr_idx + 1) % len(ROTATING_PRODUCTS)
    deal_key = ROTATING_PRODUCTS[next_idx]

    img_path, url, caption = build_hardware_deal_story(deal_key)
    
    # Actualizar puntero de rotación
    state["last_product_idx"] = next_idx
    save_stories_state(state)

    return img_path, url, caption, deal_key

def build_content_teaser_story(
    video_title: str,
    video_thumb_path: Optional[Path] = None,
    reel_url: str = "https://linktr.ee/gtavihubspain"
) -> Tuple[Path, str, str]:
    """
    Genera una historia cinemática de Noticias / Gameplay de GTA VI
    a partir del vídeo o Short publicado hoy.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = OUTPUT_DIR / "stories" / f"story_teaser_{ts}.jpg"

    # Seleccionar imagen de fondo
    thumb_name = None
    if video_thumb_path and Path(video_thumb_path).exists():
        thumb_name = Path(video_thumb_path).name

    img_path = generate_clean_product_story(
        badge_text="NUEVO CLIP EXCLUSIVO",
        product_title=video_title[:32].upper(),
        price_tag="YA DISPONIBLE",
        discount_pill="EN EL CANAL",
        product_img_name=thumb_name,
        cta_text="TOCAR PARA VER VIDEO >",
        output_path=out_file
    )

    caption = (
        f"🚨 Nuevo vídeo en el canal: {video_title[:60]}\n"
        f"Toca la historia o entra a @gtavihubspain para verlo completo 🌴\n"
        f"#GTA6 #GTAVI #RockstarGames #ViceCity"
    )

    return img_path, reel_url, caption

def publish_scheduled_story(force: bool = False, preferred_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Ejecuta el ciclo de publicación programada de historias si las condiciones de algoritmo son óptimas.
    """
    allowed, reason = can_publish_story(force=force)
    if not allowed and not force:
        return {
            "status": "skipped",
            "reason": reason
        }

    story_type = preferred_type or get_next_story_type()
    
    if story_type == "product":
        img_path, link_url, caption, prod_key = build_next_rotating_deal_story()
        item_desc = f"Oferta Rotatoria: {prod_key}"
    else:
        # Buscar último thumbnail disponible de GTA 6 en output
        thumbs = sorted(OUTPUT_DIR.glob("*_thumb.jpg"), key=lambda f: f.stat().st_mtime, reverse=True)
        thumb_path = thumbs[0] if thumbs else None
        img_path, link_url, caption = build_content_teaser_story(
            video_title="FILTRACION Y NOVEDADES GTA 6",
            video_thumb_path=thumb_path,
            reel_url="https://linktr.ee/gtavihubspain"
        )
        item_desc = "Noticia / Gameplay Teaser GTA VI"

    # Publicar a Instagram Stories
    result_url = publish_story_to_instagram(
        image_path=img_path,
        affiliate_url=link_url,
        caption=caption
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    state = load_stories_state()
    if state.get("today_date") != today_str:
        state["today_date"] = today_str
        state["today_count"] = 0
    state["today_count"] = state.get("today_count", 0) + 1
    state["last_published"] = now_iso

    history = state.setdefault("history", [])
    history.append({
        "timestamp": now_iso,
        "type": story_type,
        "item": item_desc,
        "image": str(img_path.name),
        "url": result_url
    })
    # Mantener últimos 30 registros
    state["history"] = history[-30:]
    save_stories_state(state)

    return {
        "status": "published" if result_url else "failed",
        "type": story_type,
        "item": item_desc,
        "image": str(img_path),
        "story_url": result_url,
        "today_count": state["today_count"],
        "max_daily": MAX_STORIES_PER_DAY
    }

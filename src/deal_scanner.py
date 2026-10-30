"""
deal_scanner.py — Rastreador y Gestor Autónomo de Ofertas de Amazon
Actualiza automáticamente las mejores ofertas de hardware, periféricos y reservas
relacionadas con GTA VI cada 3 días y notifica al usuario vía Telegram.
"""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import CONFIG_DIR, BASE_DIR
from .affiliates import get_amazon_tag, build_amazon_url

logger = logging.getLogger("deal_scanner")

DATA_DIR = BASE_DIR / "data"
DEALS_STATE_FILE = DATA_DIR / "deals_state.json"
AFFILIATES_FILE = CONFIG_DIR / "affiliates.json"

DEFAULT_INTERVAL_DAYS = 3

# Catálogo dinámico de ofertas y categorías prioritarias para GTA VI
CURATED_DEALS_CATALOG = [
    {
        "key": "volante_logitech_g29",
        "title": "Logitech G29 / G923 Driving Force (Volante + Pedales Leonida)",
        "badge": "🏎️ CONDUCCIÓN VICE CITY",
        "category": "perifericos",
        "search_query": "logitech g29 driving force ps5",
        "direct_url": "https://www.amazon.es/s?k=logitech+g29+ps5",
        "target_deal": "Rebajas habituales del 20% al 40% en campañas gaming"
    },
    {
        "key": "monitor_gaming_4k",
        "title": "Monitor Gaming 4K 144Hz HDMI 2.1 (Para PS5 Pro y Modo Fidelidad)",
        "badge": "🖥️ 4K 144HZ HDR",
        "category": "monitores",
        "search_query": "monitor gaming 4k 144hz hdmi 2.1 ps5",
        "direct_url": "https://www.amazon.es/s?k=monitor+gaming+4k+144hz+ps5",
        "target_deal": "Top valorados con tasa de refresco 144Hz y VRR"
    },
    {
        "key": "ssd_ps5_2tb",
        "title": "WD_BLACK SN850X 2TB SSD M.2 con Disipador (+200GB GTA 6)",
        "badge": "💾 EXPANSIÓN OBLIGATORIA",
        "category": "almacenamiento",
        "search_query": "wd black sn850x 2tb ps5 con disipador",
        "direct_url": "https://www.amazon.es/s?k=wd+black+sn850x+2tb+ps5",
        "target_deal": "Mínimos históricos habituales en Black Friday / Gaming Days"
    },
    {
        "key": "ps5_pro",
        "title": "PlayStation 5 Pro (Modo 4K 60 FPS Leonida)",
        "badge": "⚡ MÁXIMO RENDIMIENTO",
        "category": "consolas",
        "search_query": "playstation 5 pro consola",
        "direct_url": "https://www.amazon.es/s?k=playstation+5+pro+consola",
        "target_deal": "Packs oficiales y stock garantizado"
    },
    {
        "key": "pulse_headset",
        "title": "Auriculares Pulse Elite / Pulse 3D (Audio 3D Tempest)",
        "badge": "🎧 INMERSIÓN TOTAL",
        "category": "audio",
        "search_query": "pulse elite ps5",
        "direct_url": "https://www.amazon.es/s?k=pulse+elite+ps5",
        "target_deal": "Descuentos en auriculares inalámbricos oficiales"
    },
    {
        "key": "dualsense_controller",
        "title": "Mando Inalámbrico DualSense (Colores Especiales / Edge)",
        "badge": "🕹️ GATILLOS HÁPTICOS",
        "category": "perifericos",
        "search_query": "mando dualsense ps5",
        "direct_url": "https://www.amazon.es/s?k=mando+dualsense+ps5",
        "target_deal": "Ofertas en mandos adicionales para multijugador"
    },
    {
        "key": "psn_card_50",
        "title": "Tarjeta Saldo PlayStation Store 50€ / 100€ (Monedero Digital)",
        "badge": "💳 RESERVA DIGITAL",
        "category": "tarjetas",
        "search_query": "tarjeta playstation network 50 euros",
        "direct_url": "https://www.amazon.es/s?k=tarjeta+playstation+network",
        "target_deal": "Código digital inmediato para reservas en PS Store"
    },
    {
        "key": "gta6_game_ps5",
        "title": "Grand Theft Auto VI - Reserva Oficial (PS5)",
        "badge": "🔥 RESERVA OFICIAL",
        "category": "juegos",
        "search_query": "gta 6 playstation 5",
        "direct_url": "https://www.amazon.es/s?k=gta+6+playstation+5",
        "target_deal": "Precio mínimo garantizado en preventa Amazon"
    }
]

def load_deals_state() -> Dict[str, Any]:
    """Carga el estado de la última sincronización de ofertas."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DEALS_STATE_FILE.exists():
        return {
            "last_updated": None,
            "interval_days": DEFAULT_INTERVAL_DAYS,
            "updates_count": 0,
            "active_deals": []
        }
    try:
        with open(DEALS_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error cargando estado de ofertas: {e}")
        return {
            "last_updated": None,
            "interval_days": DEFAULT_INTERVAL_DAYS,
            "updates_count": 0,
            "active_deals": []
        }

def save_deals_state(state: Dict[str, Any]) -> None:
    """Persiste el estado de ofertas en data/deals_state.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(DEALS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando estado de ofertas: {e}")

def should_update_deals(interval_days: int = DEFAULT_INTERVAL_DAYS) -> bool:
    """
    Comprueba si han transcurrido los días configurados (por defecto 3 días)
    desde la última actualización de ofertas.
    """
    state = load_deals_state()
    last_str = state.get("last_updated")
    if not last_str:
        return True
    try:
        last_dt = datetime.fromisoformat(last_str)
        now = datetime.now(timezone.utc)
        elapsed = now - last_dt
        return elapsed >= timedelta(days=interval_days)
    except Exception:
        return True

def get_days_until_next_update(interval_days: int = DEFAULT_INTERVAL_DAYS) -> float:
    """Devuelve los días restantes hasta la siguiente actualización automática."""
    state = load_deals_state()
    last_str = state.get("last_updated")
    if not last_str:
        return 0.0
    try:
        last_dt = datetime.fromisoformat(last_str)
        now = datetime.now(timezone.utc)
        elapsed = now - last_dt
        remaining = timedelta(days=interval_days) - elapsed
        return max(0.0, remaining.total_seconds() / 86400.0)
    except Exception:
        return 0.0

def sync_affiliates_json(catalog: List[Dict[str, Any]], tag: str) -> None:
    """Sincroniza y enriquece config/affiliates.json con los productos y categorías del catálogo."""
    if not AFFILIATES_FILE.exists():
        return
    try:
        with open(AFFILIATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    products = data.setdefault("products", {})
    for item in catalog:
        key = item["key"]
        products[key] = {
            "title": item["title"],
            "badge": item["badge"],
            "category": item.get("category", "gaming"),
            "search_query": item["search_query"],
            "direct_url": item["direct_url"]
        }

    data["amazon_associate_tag"] = tag
    try:
        with open(AFFILIATES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error actualizando config/affiliates.json: {e}")

def scan_and_update_deals(force: bool = False, notify_telegram: bool = True) -> Dict[str, Any]:
    """
    Ejecuta el ciclo de actualización de ofertas de Amazon cada 3 días.
    Enriquece los enlaces con el tag de afiliado oficial y actualiza el estado.
    """
    if not force and not should_update_deals():
        state = load_deals_state()
        return {
            "status": "skipped",
            "message": "Aún no han transcurrido los 3 días desde la última sincronización.",
            "last_updated": state.get("last_updated"),
            "days_remaining": round(get_days_until_next_update(), 1),
            "deals": state.get("active_deals", [])
        }

    tag = get_amazon_tag()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Construir lista de ofertas con tag verificado
    active_deals = []
    for item in CURATED_DEALS_CATALOG:
        url = build_amazon_url(item["direct_url"], tag=tag)
        active_deals.append({
            "key": item["key"],
            "title": item["title"],
            "badge": item["badge"],
            "category": item.get("category", "gaming"),
            "url": url,
            "note": item.get("target_deal", "Oferta activa")
        })

    # Sincronizar archivo principal
    sync_affiliates_json(CURATED_DEALS_CATALOG, tag=tag)

    # Actualizar estado persistente
    state = load_deals_state()
    updates_count = state.get("updates_count", 0) + 1
    new_state = {
        "last_updated": now_iso,
        "interval_days": DEFAULT_INTERVAL_DAYS,
        "updates_count": updates_count,
        "tag": tag,
        "total_active": len(active_deals),
        "active_deals": active_deals
    }
    save_deals_state(new_state)

    report_text = format_deals_report(new_state)

    # Notificar por Telegram si está configurado
    if notify_telegram:
        try:
            from .telegram_bot import send_telegram_alert
            send_telegram_alert(report_text)
        except Exception as e:
            logger.warning(f"No se pudo enviar notificación de ofertas a Telegram: {e}")

    return {
        "status": "updated",
        "message": f"Ofertas sincronizadas correctamente (Ciclo #{updates_count}).",
        "last_updated": now_iso,
        "total_deals": len(active_deals),
        "report": report_text
    }

def format_deals_report(state: Dict[str, Any]) -> str:
    """Genera el informe formateado para Telegram y la terminal."""
    tag = state.get("tag", get_amazon_tag())
    deals = state.get("active_deals", [])
    count = state.get("updates_count", 1)
    
    lines = [
        "🛒 *RADAR DE OFERTAS AMAZON — GTA VI HUB*",
        f"📅 _Actualización automática cada 3 días (Ciclo #{count})_",
        f"🏷️ Tag de Afiliado: `{tag}`\n",
        "🔥 *OFERTAS Y PREPARATIVOS DESTACADOS:*"
    ]

    for d in deals:
        lines.append(f"{d['badge']} *{d['title']}*")
        lines.append(f"🔗 [Ver en Amazon.es]({d['url']})")
        lines.append(f"💡 _{d.get('note', '')}_\n")

    lines.append("⚡ *Efecto Carrito Activo*: Las visitas activan la cookie de 24h para comisiones en cualquier compra.")
    lines.append("🔄 _Próxima actualización automática: en 3 días._")
    return "\n".join(lines)

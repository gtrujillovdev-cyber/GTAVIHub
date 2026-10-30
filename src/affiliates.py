"""
affiliates.py — Motor de Monetización, Afiliados de Amazon y Branding de Canales
Diseñado para maximizar comisiones y preparar los canales de GTA VI Hub Spain
para el lanzamiento oficial de Grand Theft Auto VI.
"""
import os
import json
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import CONFIG_DIR, BASE_DIR

AFFILIATES_FILE = CONFIG_DIR / "affiliates.json"

def _load_affiliates_data() -> Dict[str, Any]:
    if not AFFILIATES_FILE.exists():
        return {}
    try:
        with open(AFFILIATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_amazon_tag() -> str:
    """Obtiene la etiqueta de afiliado de Amazon desde .env o de config/affiliates.json."""
    tag = os.getenv("AMAZON_ASSOCIATE_TAG")
    if tag:
        return tag.strip()
    data = _load_affiliates_data()
    return data.get("amazon_associate_tag", "gtavihub-21")

def get_hub_linktree() -> str:
    """Obtiene la URL central de Linktree / Hub de enlaces."""
    return os.getenv("MONETIZATION_AFFILIATE_URL", os.getenv("LINKTREE_URL", "https://linktr.ee/gtavihubspain"))

def build_amazon_url(base_or_search: str, tag: Optional[str] = None) -> str:
    """
    Inyecta la etiqueta de afiliado en una URL de Amazon España.
    """
    active_tag = tag or get_amazon_tag()
    if not base_or_search:
        return f"https://www.amazon.es/?tag={active_tag}"
    
    # Si es una búsqueda libre
    if not base_or_search.startswith("http"):
        q = urllib.parse.quote_plus(base_or_search)
        return f"https://www.amazon.es/s?k={q}&tag={active_tag}"
    
    # Si ya es una URL
    separator = "&" if "?" in base_or_search else "?"
    if f"tag=" in base_or_search:
        return base_or_search
    return f"{base_or_search}{separator}tag={active_tag}"

def get_all_affiliate_products(tag: Optional[str] = None) -> List[Dict[str, str]]:
    """Devuelve la lista de productos preparados para GTA 6 con sus enlaces de afiliado."""
    data = _load_affiliates_data()
    products = data.get("products", {})
    active_tag = tag or get_amazon_tag()
    
    result = []
    for key, p in products.items():
        direct = p.get("direct_url", "")
        url = build_amazon_url(direct, tag=active_tag)
        result.append({
            "key": key,
            "title": p.get("title", ""),
            "badge": p.get("badge", "🎮 OFICIAL"),
            "url": url
        })
    return result

def format_description_affiliate_block(tag: Optional[str] = None) -> str:
    """
    Genera el bloque de afiliados de Amazon para las descripciones de YouTube Shorts y vídeos,
    cumpliendo estrictamente con la política de divulgación de Amazon Associates.
    """
    active_tag = tag or get_amazon_tag()
    hub = get_hub_linktree()
    
    # Enlaces clave para descripción
    gta6_ps5 = build_amazon_url("https://www.amazon.es/s?k=gta+6+playstation+5", tag=active_tag)
    ps5_pro = build_amazon_url("https://www.amazon.es/s?k=playstation+5+pro+consola", tag=active_tag)
    ssd_2tb = build_amazon_url("https://www.amazon.es/s?k=wd+black+sn850x+2tb+ps5", tag=active_tag)
    
    block = f"""🎮 𝗥𝗘𝗦𝗘𝗥𝗩𝗔 𝗢𝗙𝗜𝗖𝗜𝗔𝗟 𝗚𝗧𝗔 𝗩𝗜 & 𝗛𝗔𝗥𝗗𝗪𝗔𝗥𝗘 𝗣𝗥𝗘-𝗟𝗔𝗡𝗭𝗔𝗠𝗜𝗘𝗡𝗧𝗢:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 Reserva GTA 6 (Amazon Garantizado): {gta6_ps5}
⚡ Consola PS5 Pro (4K 60 FPS Leonida): {ps5_pro}
💾 SSD M.2 2TB Ultra-Rápido (+200GB GTA 6): {ssd_2tb}
🌐 Todas las ofertas de consolas y accesorios: {hub}

⚖️ 𝗔𝗩𝗜𝗦𝗢 𝗗𝗘 𝗔𝗙𝗜𝗟𝗜𝗔𝗗𝗢𝗦:
En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los requisitos aplicables."""
    return block

def format_pinned_comment_affiliates(debate_question: str, tag: Optional[str] = None) -> str:
    """
    Genera el comentario anclado de YouTube / TikTok / Reels optimizado para conversión y debate.
    """
    active_tag = tag or get_amazon_tag()
    hub = get_hub_linktree()
    gta6_reserva = build_amazon_url("https://www.amazon.es/s?k=gta+6+playstation+5", tag=active_tag)
    ps5_deal = build_amazon_url("https://www.amazon.es/s?k=playstation+5+pro+consola", tag=active_tag)
    
    business = os.getenv("BUSINESS_EMAIL", "gabtru@hotmail.com")
    
    return f"""🌴 💬 𝗗𝗘𝗕𝗔𝗧𝗘 𝗚𝗧𝗔 𝟲:
{debate_question}
👇 ¡Déjanos tu teoría en los comentarios!

🔥 𝗥𝗘𝗦𝗘𝗥𝗩𝗔 𝗢𝗙𝗜𝗖𝗜𝗔𝗟 𝗚𝗧𝗔 𝟲 (Amazon) 👉 {gta6_reserva}
⚡ 𝗖𝗢𝗡𝗦𝗢𝗟𝗔𝗦 𝗣𝗦𝟱 𝗣𝗥𝗢 & 𝗦𝗟𝗜𝗠 👉 {ps5_deal}
🌐 𝗧𝗢𝗗𝗔𝗦 𝗟𝗔𝗦 𝗢𝗙𝗘𝗥𝗧𝗔𝗦 & 𝗥𝗘𝗗𝗘𝗦 👉 {hub}
📩 Contacto Business: {business}"""

def get_channel_branding_kit() -> Dict[str, Any]:
    """
    Devuelve los textos, metadatos y enlaces listos para configurar
    los perfiles oficiales de YouTube, TikTok, Instagram y Linktree de cara al estreno de GTA 6.
    """
    hub = get_hub_linktree()
    tag = get_amazon_tag()
    
    return {
        "youtube": {
            "channel_name": "GTA VI Hub Spain",
            "handle": "@GTAVIHubSpain",
            "tagline": "Tu canal definitivo de Grand Theft Auto VI en España y en español 🇪🇸",
            "description": (
                "🌴 Bienvenido a GTA VI Hub Spain, el canal oficial y de referencia sobre Grand Theft Auto VI (GTA 6) "
                "para la comunidad hispanohablante.\n\n"
                "🎮 Aquí encontrarás:\n"
                "• Cobertura diaria de novedades, filtraciones reales y análisis al milímetro del motor RAGE 9.\n"
                "• Desgloses escena por escena de trailers y comunicados oficiales de Rockstar Games.\n"
                "• Físicas de Leonida, mapa completo de Vice City, misiones con Lucía y Jason y secretos ocultos.\n"
                "• Los momentos más virales y reacciones de la comunidad y streamers.\n"
                "• Comparativas técnicas de rendimiento en PS5, PS5 Pro y Xbox Series X.\n\n"
                "🔔 ¡Suscríbete y activa la campana para no perderte ni un solo segundo del camino hacia el estreno más esperado de la historia!\n\n"
                f"🌐 Enlaces oficiales, reserva de GTA 6 y ofertas de hardware: {hub}\n\n"
                "📩 Contacto comercial / Business: gabtru@hotmail.com\n\n"
                "#GTA6 #GrandTheftAutoVI #RockstarGames #ViceCity #GamingEspaña"
            ),
            "links": [
                {"title": "🔥 Reserva GTA 6 (Amazon)", "url": build_amazon_url("https://www.amazon.es/s?k=gta+6+playstation+5", tag=tag)},
                {"title": "🌐 Hub de Enlaces & Ofertas", "url": hub},
                {"title": "🎬 TikTok Oficial", "url": "https://tiktok.com/@gtavihubspain"},
                {"title": "📸 Instagram Reels", "url": "https://instagram.com/gtavihubspain"}
            ]
        },
        "tiktok": {
            "display_name": "GTA VI Hub Spain 🌴",
            "username": "@gtavihubspain",
            "bio": (
                "🌴 Tu canal #1 de GTA VI en España 🇪🇸\n"
                "🎮 Filtraciones, físicas & secretos diarios\n"
                "👇 Reserva oficial de GTA 6 y ofertas PS5:"
            ),
            "bio_link": hub,
            "category": "Videojuegos / Gaming"
        },
        "instagram": {
            "name": "GTA VI Hub Spain | Noticias & Gameplay",
            "username": "@gtavihubspain",
            "category": "Creador de contenido de videojuegos",
            "bio": (
                "🌴 La mayor comunidad de GTA 6 en España 🇪🇸\n"
                "🚨 Filtraciones reales, físicas RAGE 9 y noticias diarias\n"
                "🎮 Cobertura 24/7 hacia el estreno en PS5 & Xbox\n"
                "👇 Reserva tu edición y hardware con descuento ⬇️"
            ),
            "bio_link": hub
        },
        "linktree_buttons": [
            {
                "order": 1,
                "title": "🔥 RESERVAR GRAND THEFT AUTO VI (PS5 / Xbox)",
                "subtitle": "Amazon Garantizado — Precio mínimo garantizado",
                "url": build_amazon_url("https://www.amazon.es/s?k=gta+6+playstation+5", tag=tag),
                "badge": "Prioridad 1"
            },
            {
                "order": 2,
                "title": "⚡ PLAYSTATION 5 PRO — Modo 4K 60 FPS Leonida",
                "subtitle": "Ofertas en consola oficial recomendada para GTA 6",
                "url": build_amazon_url("https://www.amazon.es/s?k=playstation+5+pro+consola", tag=tag),
                "badge": "Hardware Top"
            },
            {
                "order": 3,
                "title": "💾 SSD M.2 2TB para PS5 (Prepárate para los +200GB)",
                "subtitle": "WD_BLACK SN850X con disipador compatible oficial",
                "url": build_amazon_url("https://www.amazon.es/s?k=wd+black+sn850x+2tb+ps5", tag=tag),
                "badge": "Imprescindible"
            },
            {
                "order": 4,
                "title": "🎧 Auriculares Pulse Elite / Pulse 3D (Audio Vice City)",
                "subtitle": "Audio 3D espacial para escuchar cada detalle",
                "url": build_amazon_url("https://www.amazon.es/s?k=pulse+elite+ps5", tag=tag),
                "badge": "Sonido Inmersivo"
            },
            {
                "order": 5,
                "title": "💳 Tarjetas Saldo PlayStation Store 50€ / 100€",
                "subtitle": "Código digital inmediato para reservas digitales",
                "url": build_amazon_url("https://www.amazon.es/s?k=tarjeta+playstation+network", tag=tag),
                "badge": "Digital"
            },
            {
                "order": 6,
                "title": "🔴 Canal Oficial de YouTube Shorts",
                "subtitle": "Suscríbete y activa la campana",
                "url": "https://youtube.com/@GTAVIHubSpain?sub_confirmation=1",
                "badge": "Comunidad"
            },
            {
                "order": 7,
                "title": "🎬 TikTok Oficial (@gtavihubspain)",
                "subtitle": "Clips diarios y directos",
                "url": "https://tiktok.com/@gtavihubspain",
                "badge": "Viral"
            }
        ]
    }

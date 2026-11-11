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

def is_affiliates_enabled() -> bool:
    """
    Indica si la inyección de enlaces comerciales y avisos de Amazon está habilitada.
    Por defecto está DESACTIVADA (False) para proteger las cuentas nuevas contra penalizaciones
    de spam algorítmico en YouTube, TikTok e Instagram (Modo Orgánico Anti-Ban).
    """
    val = os.getenv("ENABLE_AFFILIATE_LINKS", "false").strip().lower()
    return val in ("true", "1", "yes")

def format_pinned_comment_clean(debate_question: str) -> str:
    """
    Genera un comentario anclado 100% orgánico enfocado solo en debate comunitario,
    libre de enlaces externos salientes (protección anti-spam en canales nuevos de Shorts).
    """
    return f"""🌴 💬 𝗗𝗘𝗕𝗔𝗧𝗘 𝗚𝗧𝗔 𝟲:
{debate_question}
👇 ¡Déjanos tu opinión en los comentarios!"""

def get_hub_linktree() -> str:
    """Obtiene la URL central de Linktree / Hub de enlaces."""
    return os.getenv("MONETIZATION_AFFILIATE_URL", os.getenv("LINKTREE_URL", "https://linktr.ee/gtavihubextra"))

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
            "channel_name": "GTA VI Hub",
            "handle": "@gtavihubextra",
            "tagline": "Tu espacio diario en español sobre Grand Theft Auto VI, Vice City y Leonida 🇪🇸",
            "description": (
                "🌴 Bienvenido a GTA VI Hub, tu espacio diario en español sobre Grand Theft Auto VI.\n\n"
                "🎮 Cobertura rápida, directa y contrastada sobre Vice City y Leonida:\n"
                "• Análisis técnicos del motor RAGE 9, comparativas gráficas y rendimiento en consolas.\n"
                "• Desgloses detalle a detalle de cada tráiler, mecánica confirmada y novedad oficial de Rockstar Games.\n"
                "• Curiosidades del mapa, secretos ocultos y los descubrimientos más relevantes de la comunidad.\n\n"
                "📌 Todos los vídeos se publican con fines informativos, de análisis y traducción comentada bajo Fair Use (Art. 107 Copyright Act), acreditando siempre a cada fuente original.\n\n"
                "🔔 Suscríbete y activa la campanita para no perderte ninguna novedad rumbo al estreno.\n\n"
                "📩 Contacto / Business / Copyright: gabtru@hotmail.com\n\n"
                "#GTA6 #GrandTheftAutoVI #RockstarGames #ViceCity #Leonida #Gaming"
            ),
            "links": [
                {"title": "🔴 YouTube Oficial", "url": "https://www.youtube.com/@gtavihubextra"},
                {"title": "🌐 Hub de Enlaces", "url": hub},
                {"title": "🎬 TikTok Oficial", "url": "https://tiktok.com/@gtavihubextra"}
            ]
        },
        "tiktok": {
            "display_name": "GTA VI Hub 🌴",
            "username": "@gtavihubextra",
            "bio": "GTA VI en español 🌴 Análisis RAGE 9, noticias y gameplay de Vice City 🎮",
            "bio_link": "",
            "category": "Videojuegos / Gaming"
        },
        "instagram": {
            "name": "GTA VI Hub | Noticias & Gameplay",
            "username": "@gtavihubextra",
            "category": "Creador de contenido de videojuegos",
            "bio": (
                "🌴 Comunidad de GTA VI en español 🇪🇸\n"
                "⚡ Análisis RAGE 9, noticias y gameplay de Vice City\n"
                "🎮 Cobertura diaria rumbo al estreno en PS5 & Xbox\n"
                "📺 YouTube & TikTok: @gtavihubextra"
            ),
            "bio_link": ""
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
                "title": "🔴 Canal Oficial de YouTube Shorts (@gtavihubextra)",
                "subtitle": "Suscríbete y activa la campana para nuevos clips",
                "url": "https://youtube.com/@gtavihubextra?sub_confirmation=1",
                "badge": "Comunidad"
            },
            {
                "order": 7,
                "title": "🎬 TikTok Oficial (@gtavihubextra)",
                "subtitle": "Clips diarios y análisis de Vice City",
                "url": "https://tiktok.com/@gtavihubextra",
                "badge": "Viral"
            },
            {
                "order": 8,
                "title": "📸 Instagram Oficial (@gtavihubextra)",
                "subtitle": "Reels y noticias de última hora",
                "url": "https://instagram.com/gtavihubextra",
                "badge": "Reels"
            }
        ]
    }

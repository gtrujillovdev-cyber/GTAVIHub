"""
story_generator.py — Generador Cinemático de Historias con Estética Real GTA VI
Diseñado para Instagram y TikTok Stories con fotografías reales de GTA VI,
escaparate visual de producto, mínimo texto de alto impacto y compliance estricto.
"""
import os
import re
import math
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from .config import BASE_DIR, OUTPUT_DIR, CONFIG_DIR
from .affiliates import get_amazon_tag, build_amazon_url

logger = logging.getLogger("story_generator")

STORIES_DIR = OUTPUT_DIR / "stories"
ASSETS_DIR = BASE_DIR / "assets"
PRODUCTS_DIR = ASSETS_DIR / "products"

STORY_WIDTH = 1080
STORY_HEIGHT = 1920

# Paleta oficial Leonida / Vice City
PALETTE = {
    "dusk_dark": (14, 8, 22),
    "neon_magenta": (217, 26, 96),     # #D91A60
    "neon_pink": (255, 30, 140),       # Glow rosa
    "miami_cyan": (0, 240, 255),       # #00F0FF
    "leonida_gold": (255, 175, 20),    # Dorado
    "card_dark": (20, 12, 30, 220),
    "text_white": (255, 255, 255),
    "text_muted": (210, 200, 230),
    "legal_gray": (160, 150, 175)
}

EMOJI_REGEX = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe00-\ufe0f]|[\u200d]|[➔→←↑↓]",
    flags=re.UNICODE
)

def clean_text_for_font(text: str) -> str:
    """
    Elimina emojis Unicode y flechas no soportadas por tipografías TTF estándar,
    evitando que aparezcan rectángulos vacíos (tofu glyphs) en la imagen renderizada.
    """
    cleaned = EMOJI_REGEX.sub("", text)
    cleaned = cleaned.replace("➔", ">").replace("→", ">")
    return " ".join(cleaned.split()).strip()

def get_story_font(size: int = 48, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Obtiene la tipografía sans-serif más limpia e impactante del sistema."""
    font_paths = [
        "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
        "/System/Library/Fonts/Supplemental/Futura.ttc",
        "/System/Library/Fonts/SF-Compact-Display-Bold.otf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf"
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass
    return ImageFont.load_default()

def create_cinematic_background() -> Image.Image:
    """
    Crea el fondo cinemático 1080x1920 a partir del arte oficial de GTA VI (assets/banner.jpg),
    con desenfoque atmosférico y viñeta oscura para que el producto y los textos resalten.
    """
    banner_path = ASSETS_DIR / "banner.jpg"
    if banner_path.exists():
        try:
            banner = Image.open(banner_path)
            scale = STORY_HEIGHT / banner.height
            bw = int(banner.width * scale)
            bh = STORY_HEIGHT
            banner_scaled = banner.resize((bw, bh), Image.Resampling.LANCZOS)
            left = (bw - STORY_WIDTH) // 2
            bg = banner_scaled.crop((left, 0, left + STORY_WIDTH, STORY_HEIGHT))
            # Desenfoque cinemático sutil
            bg = bg.filter(ImageFilter.GaussianBlur(radius=6))
        except Exception:
            bg = Image.new("RGB", (STORY_WIDTH, STORY_HEIGHT), color=PALETTE["dusk_dark"])
    else:
        bg = Image.new("RGB", (STORY_WIDTH, STORY_HEIGHT), color=PALETTE["dusk_dark"])

    # Viñeta oscura con degradado vertical (oscuro arriba para el badge, oscuro abajo para el sticker)
    overlay = Image.new("RGBA", (STORY_WIDTH, STORY_HEIGHT), (0, 0, 0, 0))
    d_ol = ImageDraw.Draw(overlay)
    for y in range(STORY_HEIGHT):
        if y < 450:
            a = int(180 * (1.0 - y / 450.0) + 90)
        elif y > 1150:
            a = int(220 * ((y - 1150.0) / 770.0) + 110)
        else:
            a = 110
        d_ol.line([(0, y), (STORY_WIDTH, y)], fill=(12, 6, 20, a))

    final_bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
    return final_bg.convert("RGB")

def generate_clean_product_story(
    badge_text: str,
    product_title: str,
    price_tag: str,
    discount_pill: str = "-35% DTO",
    product_img_name: Optional[str] = None,
    cta_text: str = "TOCAR PARA VER EN AMAZON ➔",
    output_path: Optional[Path] = None
) -> Path:
    """
    Renderiza una historia moderna, limpia y visual inspirada en las campañas de creadores top:
    - Fondo cinemático real de GTA VI.
    - Foto real del producto recortada con resplandor neón.
    - Tipografía masiva y legible de un vistazo (cero parrafadas).
    - Botón perfectamente alineado con el Link Sticker de Instagram.
    - Compliance FTC/Amazon discreto en el pie.
    """
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = STORIES_DIR / f"story_{ts}.jpg"

    # Sanitizar textos para evitar rectángulos 'tofu' por falta de glifos en fuentes TTF
    badge_text = clean_text_for_font(badge_text)
    product_title = clean_text_for_font(product_title)
    price_tag = clean_text_for_font(price_tag)
    discount_pill = clean_text_for_font(discount_pill)
    cta_text = clean_text_for_font(cta_text)

    # 1. Fondo cinemático
    canvas = create_cinematic_background()
    draw = ImageDraw.Draw(canvas)

    # 2. Marco sutil neón en los extremos
    draw.rectangle([20, 20, STORY_WIDTH - 20, STORY_HEIGHT - 20], outline=PALETTE["neon_magenta"], width=2)

    # 3. Badge Superior Flotante (Y: 280 a 350)
    pill_font = get_story_font(size=36, bold=True)
    bb = draw.textbbox((0, 0), badge_text, font=pill_font)
    pw = bb[2] - bb[0] + 50
    ph = bb[3] - bb[1] + 24
    px1 = (STORY_WIDTH - pw) // 2
    py1 = 290
    draw.rounded_rectangle([px1, py1, px1 + pw, py1 + ph], radius=18, fill=PALETTE["neon_magenta"])
    draw.rounded_rectangle([px1, py1, px1 + pw, py1 + ph], radius=18, outline=PALETTE["miami_cyan"], width=2)
    draw.text((px1 + 25, py1 + 10), badge_text, font=pill_font, fill=PALETTE["text_white"])

    # 4. Escaparate de Producto (Tarjeta Central Y: 400 a 1120)
    card_x1 = 90
    card_y1 = 400
    card_x2 = STORY_WIDTH - 90
    card_y2 = 1140
    cw = card_x2 - card_x1
    ch = card_y2 - card_y1

    # Fondo de la tarjeta con glassmorphism oscuro y resplandor
    card_overlay = Image.new("RGBA", (STORY_WIDTH, STORY_HEIGHT), (0, 0, 0, 0))
    d_card = ImageDraw.Draw(card_overlay)
    d_card.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=36, fill=(18, 10, 28, 200))
    d_card.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=36, outline=(255, 30, 140, 160), width=3)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), card_overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 5. Cargar y estampar la fotografía real del producto
    prod_path = None
    if product_img_name:
        prod_path = PRODUCTS_DIR / product_img_name
    if not prod_path or not prod_path.exists():
        # Fallback al logo o imagen disponible
        prod_path = ASSETS_DIR / "avatar.jpg"

    if prod_path.exists():
        try:
            prod_img = Image.open(prod_path)
            # Escalar el producto para que encaje limpiamente dentro de la tarjeta
            max_pw = cw - 80
            max_ph = ch - 80
            prod_img.thumbnail((max_pw, max_ph), Image.Resampling.LANCZOS)
            
            # Centrar producto en la tarjeta
            prod_x = card_x1 + (cw - prod_img.width) // 2
            prod_y = card_y1 + (ch - prod_img.height) // 2

            # Si tiene transparencia, componer con alpha
            if prod_img.mode in ("RGBA", "LA") or (prod_img.mode == "P" and "transparency" in prod_img.info):
                canvas_rgba = canvas.convert("RGBA")
                canvas_rgba.paste(prod_img, (prod_x, prod_y), prod_img.convert("RGBA"))
                canvas = canvas_rgba.convert("RGB")
                draw = ImageDraw.Draw(canvas)
            else:
                # Si es JPG, redondear esquinas suavemente
                mask = Image.new("L", prod_img.size, 0)
                d_m = ImageDraw.Draw(mask)
                d_m.rounded_rectangle([0, 0, prod_img.width, prod_img.height], radius=24, fill=255)
                canvas.paste(prod_img, (prod_x, prod_y), mask)
        except Exception as e:
            logger.warning(f"Error procesando imagen del producto: {e}")

    # 6. Titular Grande, Limpio y Directo (Y: 1190 a 1300)
    title_font = get_story_font(size=62, bold=True)
    t_bb = draw.textbbox((0, 0), product_title, font=title_font)
    tw = t_bb[2] - t_bb[0]
    # Sombra negra gruesa
    draw.text(((STORY_WIDTH - tw) // 2 + 3, 1193), product_title, font=title_font, fill=(0, 0, 0))
    draw.text(((STORY_WIDTH - tw) // 2, 1190), product_title, font=title_font, fill=PALETTE["text_white"])

    # 7. Bloque de Precio y Rebaja (Y: 1280 a 1370)
    # Ejemplo: "199,99€" en dorado + píldora rosa con "-35% DTO"
    price_font = get_story_font(size=64, bold=True)
    p_bb = draw.textbbox((0, 0), price_tag, font=price_font)
    pw_val = p_bb[2] - p_bb[0]

    disc_font = get_story_font(size=34, bold=True)
    d_bb = draw.textbbox((0, 0), discount_pill, font=disc_font)
    dw_val = d_bb[2] - d_bb[0] + 32
    dh_val = d_bb[3] - d_bb[1] + 18

    total_w = pw_val + dw_val + 24
    start_x = (STORY_WIDTH - total_w) // 2

    # Precio en Dorado Leonida con sombra
    draw.text((start_x + 3, 1283), price_tag, font=price_font, fill=(0, 0, 0))
    draw.text((start_x, 1280), price_tag, font=price_font, fill=PALETTE["leonida_gold"])

    # Píldora de Descuento en Neón Magenta
    pill_dx = start_x + pw_val + 24
    pill_dy = 1290
    draw.rounded_rectangle([pill_dx, pill_dy, pill_dx + dw_val, pill_dy + dh_val], radius=14, fill=PALETTE["neon_magenta"])
    draw.text((pill_dx + 16, pill_dy + 8), discount_pill, font=disc_font, fill=PALETTE["text_white"])

    # 8. Botón Flotante para el Sticker Clicable (Y: 1420 a 1530)
    btn_w = 880
    btn_h = 105
    btn_x1 = (STORY_WIDTH - btn_w) // 2
    btn_y1 = 1420
    btn_x2 = btn_x1 + btn_w
    btn_y2 = btn_y1 + btn_h

    # Fondo degradado o dorado neón
    draw.rounded_rectangle([btn_x1, btn_y1, btn_x2, btn_y2], radius=28, fill=PALETTE["miami_cyan"])
    draw.rounded_rectangle([btn_x1, btn_y1, btn_x2, btn_y2], radius=28, outline=PALETTE["leonida_gold"], width=3)

    btn_font = get_story_font(size=44, bold=True)
    btn_bb = draw.textbbox((0, 0), cta_text, font=btn_font)
    btw = btn_bb[2] - btn_bb[0]
    draw.text((btn_x1 + (btn_w - btw) // 2, btn_y1 + 26), cta_text, font=btn_font, fill=(10, 5, 18))

    # 9. Pie de Compliance y Aviso Legal Obligatorio (Discreto en gris)
    legal_font = get_story_font(size=24, bold=False)
    legal_text = "#Ad #Afiliado • En calidad de Afiliado de Amazon, obtengo ingresos por compras adscritas."
    l_bb = draw.textbbox((0, 0), legal_text, font=legal_font)
    lw = l_bb[2] - l_bb[0]
    draw.text(((STORY_WIDTH - lw) // 2, 1560), legal_text, font=legal_font, fill=PALETTE["legal_gray"])

    # 10. Guardar imagen final
    canvas.save(str(output_path), quality=96)
    logger.info(f"Historia cinemática generada: {output_path}")
    return output_path

def build_hardware_deal_story(deal_key: str = "volante_logitech_g29") -> Tuple[Path, str, str]:
    """
    Construye una historia cinemática con fotos reales y datos oficiales.
    """
    tag = get_amazon_tag()
    
    presets = {
        "volante_logitech_g29": {
            "badge": "PREPARATIVOS GTA VI",
            "title": "LOGITECH G29 PS5 / PC",
            "price": "219,00€",
            "discount": "-35% DTO",
            "img": "logitech_g29.png",
            "cta": "TOCAR PARA VER EN AMAZON >",
            "url": build_amazon_url("https://www.amazon.es/s?k=logitech+g29+ps5", tag=tag),
            "caption": "Volante Logitech G29 en oferta para GTA VI y Leonida.\nEnlace directo en la historia y bio @gtavihubspain\n#GTA6 #GTAVI #LogitechG29 #AmazonDeals #PS5"
        },
        "ps5_pro": {
            "badge": "POTENCIA 4K 60 FPS",
            "title": "PLAYSTATION 5 PRO",
            "price": "799,99€",
            "discount": "STOCK OFICIAL",
            "img": "ps5.png",
            "cta": "TOCAR PARA VER EN AMAZON >",
            "url": build_amazon_url("https://www.amazon.es/s?k=playstation+5+pro+consola", tag=tag),
            "caption": "Consola PlayStation 5 Pro lista para Grand Theft Auto VI.\nEnlace directo en la historia y bio @gtavihubspain\n#GTA6 #GTAVI #PS5Pro #Leonida"
        },
        "ssd_ps5_2tb": {
            "badge": "ALMACENAMIENTO GTA VI",
            "title": "SSD M.2 2TB CON DISIPADOR",
            "price": "139,00€",
            "discount": "-28% DTO",
            "img": "ssd_m2.jpg",
            "cta": "TOCAR PARA VER EN AMAZON >",
            "url": build_amazon_url("https://www.amazon.es/s?k=wd+black+sn850x+2tb+ps5", tag=tag),
            "caption": "SSD M.2 2TB ultra-rápido para los +200GB de GTA VI.\nEnlace directo en la historia y bio @gtavihubspain\n#GTA6 #GTAVI #SSD #PS5"
        }
    }

    data = presets.get(deal_key, presets["volante_logitech_g29"])
    out_file = STORIES_DIR / f"story_cinema_{deal_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

    img_path = generate_clean_product_story(
        badge_text=data["badge"],
        product_title=data["title"],
        price_tag=data["price"],
        discount_pill=data["discount"],
        product_img_name=data["img"],
        cta_text=data["cta"],
        output_path=out_file
    )

    return img_path, data["url"], data["caption"]

def publish_story_to_instagram(
    image_path: Path,
    affiliate_url: str,
    caption: str = ""
) -> Optional[str]:
    """
    Publica la historia directamente en Instagram Stories usando instagrapi con Link Sticker.
    """
    ig_user = os.getenv("INSTAGRAM_USERNAME")
    ig_pass = os.getenv("INSTAGRAM_PASSWORD")
    if not ig_user or not ig_pass:
        print("[Story] Falta INSTAGRAM_USERNAME / INSTAGRAM_PASSWORD en entorno.")
        return None

    session_file = ASSETS_DIR / ".browser_profiles" / "instagrapi_session.json"
    try:
        from instagrapi import Client
        from instagrapi.types import StoryLink

        cl = Client()
        cl.delay_range = [2, 4]
        if session_file.exists():
            try:
                cl.load_settings(str(session_file))
                cl.login(ig_user, ig_pass)
            except Exception:
                cl = Client()
                cl.login(ig_user, ig_pass)
        else:
            cl.login(ig_user, ig_pass)
        cl.dump_settings(str(session_file))

        print(f"[*] Subiendo Historia cinemática a Instagram (@{ig_user})...")
        link_sticker = StoryLink(webUri=affiliate_url, x=0.5, y=0.76, width=0.75, height=0.08)
        media = cl.photo_upload_to_story(
            path=str(image_path),
            caption=caption,
            links=[link_sticker]
        )
        story_pk = getattr(media, "pk", "ok")
        print(f"[✓] Historia cinemática publicada en Instagram con éxito (PK: {story_pk})")
        return f"https://www.instagram.com/stories/{ig_user}/"
    except Exception as e:
        print(f"[Story] Error publicando historia en Instagram: {e}")
        return None

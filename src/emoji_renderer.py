import re
import os
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

EMOJI_PATTERN = re.compile(
    r"("
    r"[\U00010000-\U0010ffff]"
    r"|[\u2600-\u27bf]"
    r"|[\u2300-\u23ff]"
    r"|[\u2b50-\u2b55]"
    r")[\ufe0e\ufe0f]?",
    flags=re.UNICODE
)

# Tamaños válidos de bitmap soportados por FreeType en Apple Color Emoji (sbix table)
VALID_EMOJI_SIZES = [20, 26, 32, 40, 48, 52, 64, 96]

_EMOJI_FONT_CACHE = {}
_EMOJI_IMAGE_CACHE = {}


def get_best_emoji_font(requested_size: int = 40) -> Tuple[Optional[ImageFont.FreeTypeFont], int]:
    """
    Obtiene la fuente de emojis nativa en el tamaño de bitmap válido más adecuado.
    Evita la excepción 'OSError: invalid pixel size' en FreeType al forzar uno de los
    tamaños soportados (20, 26, 32, 40, 48, 52, 64, 96).
    """
    candidates = [s for s in VALID_EMOJI_SIZES if s >= requested_size]
    chosen_size = candidates[0] if candidates else VALID_EMOJI_SIZES[-1]

    if chosen_size in _EMOJI_FONT_CACHE:
        return _EMOJI_FONT_CACHE[chosen_size], chosen_size

    for p in [
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/System/Library/Fonts/Supplemental/Apple Color Emoji.ttc",
        "/Library/Fonts/Apple Color Emoji.ttc"
    ]:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, chosen_size)
                _EMOJI_FONT_CACHE[chosen_size] = font
                return font, chosen_size
            except Exception:
                pass

    return None, 0


def render_emoji_image(emoji_char: str, target_size: int = 44) -> Optional[Image.Image]:
    """
    Renderiza un carácter emoji en alta fidelidad y lo redimensiona con LANCZOS
    al tamaño deseado exacto, garantizando cero rectángulos rotos ('tofu glyphs').
    """
    cache_key = (emoji_char, target_size)
    if cache_key in _EMOJI_IMAGE_CACHE:
        return _EMOJI_IMAGE_CACHE[cache_key]

    font, base_size = get_best_emoji_font(target_size)
    if not font:
        return None

    canvas_size = int(base_size * 1.5)
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    try:
        d.text((0, 0), emoji_char, font=font, embedded_color=True)
    except Exception:
        return None

    bbox = img.getbbox()
    if not bbox:
        return None

    cropped = img.crop(bbox)

    # 1. Filtro estricto Anti-Tofu (.notdef detector):
    # Si FreeType no soporta bitmaps a color (sbix/Apple Color Emoji), dibuja un rectángulo gris/negro.
    # Un emoji real tiene amplia variación cromática (R != G o G != B).
    # Si todos los píxeles visibles son monocromos (R == G == B), es una caja rota '[]' y se descarta.
    try:
        import numpy as np
        arr = np.array(cropped)
        if arr.shape[-1] >= 4:
            alpha_mask = arr[:, :, 3] > 30
            if not alpha_mask.any():
                return None
            vis = arr[alpha_mask]
            r, g, b = vis[:, 0], vis[:, 1], vis[:, 2]
            # Verificar si existe al menos un 5% de píxeles con saturación/color real
            chromatic = (np.abs(r.astype(int) - g.astype(int)) > 15) | (np.abs(g.astype(int) - b.astype(int)) > 15)
            if chromatic.sum() < max(5, int(len(vis) * 0.05)):
                # Es un glifo .notdef (rectángulo vacío / tofu), no un emoji a color real
                return None
    except Exception:
        pass

    aspect = cropped.width / max(1, cropped.height)
    if cropped.width > cropped.height:
        new_w = target_size
        new_h = max(1, int(target_size / aspect))
    else:
        new_h = target_size
        new_w = max(1, int(target_size * aspect))

    resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
    _EMOJI_IMAGE_CACHE[cache_key] = resized
    return resized


def is_color_emoji_supported() -> bool:
    """
    Verifica empíricamente si el entorno y la versión de FreeType actual
    son capaces de renderizar emojis a color reales sin generar rectángulos rotos.
    """
    sample = render_emoji_image("🔥", target_size=40)
    return sample is not None


def split_text_and_emojis(text: str) -> List[Tuple[str, str]]:
    """
    Segmenta un texto en tokens distinguiendo entre texto plano y caracteres emoji.
    Retorna una lista de tuplas: [('text', '¡BOMBAZO! '), ('emoji', '🔥'), ...]
    """
    if not text:
        return []

    tokens = []
    last_end = 0
    for match in EMOJI_PATTERN.finditer(text):
        start, end = match.span()
        if start > last_end:
            tokens.append(("text", text[last_end:start]))
        tokens.append(("emoji", match.group()))
        last_end = end

    if last_end < len(text):
        tokens.append(("text", text[last_end:]))

    return tokens


def measure_composite_line(
    tokens: List[Tuple[str, str]],
    font: ImageFont.FreeTypeFont,
    emoji_size: int
) -> Tuple[int, int]:
    """Calcula el ancho y alto total de una línea compuesta por texto y emojis."""
    temp_d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    sample_bb = temp_d.textbbox((0, 0), "AY", font=font)
    text_h = max(sample_bb[3] - sample_bb[1], emoji_size)

    total_w = 0
    for kind, content in tokens:
        if kind == "text":
            bb = temp_d.textbbox((0, 0), content, font=font)
            total_w += (bb[2] - bb[0])
        elif kind == "emoji":
            emo_img = render_emoji_image(content, target_size=emoji_size)
            if emo_img:
                total_w += emo_img.width + 4

    return total_w, text_h


def draw_composite_line(
    target_img: Image.Image,
    draw: ImageDraw.Draw,
    tokens: List[Tuple[str, str]],
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill_color: Tuple[int, int, int, int] = (255, 230, 0, 255),
    stroke_color: Tuple[int, int, int, int] = (0, 0, 0, 255),
    stroke_width: int = 0,
    emoji_size: Optional[int] = None
) -> int:
    """
    Dibuja una línea mixta de texto y emojis:
    - El texto se dibuja con la fuente TTF y su contorno (stroke).
    - Los emojis se dibujan como imágenes a color mediante alpha_composite, centrados verticalmente.
    - Los emojis no soportados nunca generan cajas rotas '[]' (se omiten de forma segura).
    Devuelve la posición X final acumulada.
    """
    if emoji_size is None:
        emoji_size = getattr(font, "size", 44)

    sample_bb = draw.textbbox((0, 0), "AY", font=font)
    text_h = sample_bb[3] - sample_bb[1]

    cur_x = x
    for kind, content in tokens:
        if kind == "text":
            # Filtrar caracteres que no pertenecen al juego de caracteres latino estándar para evitar cajas rotas
            clean_content = re.sub(r'[^\w\s\d¡!¿?,\.:\'-áéíóúÁÉÍÓÚñÑüÜ#$€%&/()+=@_\"“”«»]', '', content)
            if not clean_content:
                continue
            if stroke_width > 0:
                for dx in range(-stroke_width, stroke_width + 1, 2):
                    for dy in range(-stroke_width, stroke_width + 1, 2):
                        if dx != 0 or dy != 0:
                            draw.text((cur_x + dx, y + dy), clean_content, font=font, fill=stroke_color)
            draw.text((cur_x, y), clean_content, font=font, fill=fill_color)
            bb = draw.textbbox((0, 0), clean_content, font=font)
            cur_x += (bb[2] - bb[0])
        elif kind == "emoji":
            emo_img = render_emoji_image(content, target_size=emoji_size)
            if emo_img:
                ey = int(y + (text_h - emo_img.height) / 2)
                target_img.alpha_composite(emo_img, (int(cur_x), ey))
                cur_x += emo_img.width + 4

    return cur_x


def clean_text_preserve_emojis(text: str) -> str:
    """
    Limpia tags HTML/VTT y espacios residuales pero preserva caracteres alfanuméricos,
    signos gramaticales y emojis Unicode intactos para ganchos y tarjetas visuales.
    """
    if not text:
        return ""
    # 1. Tags HTML/VTT
    text = re.sub(r"<[^>]+>", " ", text)
    # 2. Entidades HTML
    text = re.sub(r"&[a-zA-Z0-9#]+;", " ", text)
    # 3. Separar palabras pegadas
    text = re.sub(r"([a-zñáéíóú])([A-ZÑÁÉÍÓÚ])", r"\1 \2", text)
    # 4. Whitelist que incluye caracteres normales + rango Unicode de emojis
    allowed_chars = r"[^\w\s\d¡!¿?,\.:\'-áéíóúÁÉÍÓÚñÑüÜ\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55\ufe0e\ufe0f]"
    cleaned = re.sub(allowed_chars, "", text)
    return " ".join(cleaned.split()).strip()

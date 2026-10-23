import os
import textwrap
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter


def extract_keyframe(video_path: Path, output_frame: Path, timestamp_sec: float = 3.0) -> bool:
    """Extrae un fotograma clave del vídeo usando ffmpeg."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(timestamp_sec),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(output_frame)
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        return output_frame.exists()
    except Exception as e:
        print(f"[!] Error extrayendo fotograma: {e}")
        return False


def get_best_font(size: int = 70):
    """Obtiene tipografía bold moderna en macOS."""
    font_configs = [
        ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", 0),
        ("/System/Library/Fonts/Avenir Next.ttc", 8),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 9),
        ("/System/Library/Fonts/Supplemental/Futura.ttc", 0),
    ]
    for path, idx in font_configs:
        if os.path.exists(path):
            try:
                if path.endswith(".ttc"):
                    return ImageFont.truetype(path, size, index=idx)
                else:
                    return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _apply_color_tone(img: Image.Image, tone: str) -> Image.Image:
    """Aplica un tono de color según la tendencia viral detectada."""
    r, g, b = img.split()
    if tone == "neon_miami":
        r = r.point(lambda i: min(255, int(i * 1.08)))
        b = b.point(lambda i: min(255, int(i * 1.12)))
    elif tone == "orange_fire":
        r = r.point(lambda i: min(255, int(i * 1.15)))
        g = g.point(lambda i: min(255, int(i * 0.95)))
    elif tone == "bright_pop":
        r = r.point(lambda i: min(255, int(i * 1.05)))
        g = g.point(lambda i: min(255, int(i * 1.05)))
        b = b.point(lambda i: min(255, int(i * 1.05)))
    # dark_cinematic: sin ajuste de canales
    return Image.merge("RGB", (r, g, b))


def _draw_hook_text(draw: ImageDraw.Draw, text: str, img_w: int, img_h: int, style: Dict[str, Any]) -> None:
    """Dibuja el texto del gancho viral con contorno grueso estilo YouTube trending."""
    if not text:
        return

    font_size = max(32, int(img_h * style.get("font_size_ratio", 0.07)))
    font = get_best_font(font_size)

    # Limitar a 2 líneas de ~22 chars
    wrapped = textwrap.wrap(text[:80], width=22)[:2]
    line_h = font_size + 8
    total_h = len(wrapped) * line_h
    y_start = img_h - total_h - int(img_h * 0.08)

    stroke_w = style.get("text_stroke_width", 6)
    stroke_c = tuple(style.get("text_stroke", [0, 0, 0]))
    fill_c = tuple(style.get("text_color", [255, 230, 0]))

    for i, line in enumerate(wrapped):
        bbox = font.getbbox(line)
        text_w = bbox[2] - bbox[0]
        x = (img_w - text_w) // 2
        y = y_start + i * line_h

        # Contorno (stroke) — dibujado en 8 direcciones
        for dx in range(-stroke_w, stroke_w + 1, 2):
            for dy in range(-stroke_w, stroke_w + 1, 2):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=font, fill=stroke_c)
        draw.text((x, y), line, font=font, fill=fill_c)


def create_video_thumbnail(
    video_path: Path,
    output_thumb_path: Path,
    hook_text: str = "",
    creator_tag: str = "",
    is_short: bool = False,
    style: Optional[Dict[str, Any]] = None
) -> Optional[Path]:
    """
    Genera una miniatura viral adaptada al estilo tendencia actual:
    - Fotograma clave del vídeo renderizado.
    - Realce de color, contraste y saturación según perfil viral.
    - Tono de color (neon_miami, orange_fire, bright_pop, dark_cinematic).
    - Viñeta oscura inferior configurable.
    - Texto de gancho bold con contorno (estilo YouTube trending).
    """
    # Cargar perfil viral si no se pasa explícitamente
    if style is None:
        try:
            from .viral_thumbnail_style import get_viral_style
            style = get_viral_style()
        except Exception:
            style = {
                "saturation": 1.35, "contrast": 1.25, "brightness": 1.05,
                "text_color": [255, 230, 0], "text_stroke": [0, 0, 0],
                "text_stroke_width": 6, "font_size_ratio": 0.07,
                "bottom_gradient": True, "vignette_alpha": 120,
                "color_tone": "neon_miami", "text_hook": True,
            }

    temp_frame = output_thumb_path.with_suffix(".tmp_frame.jpg")

    extracted = extract_keyframe(video_path, temp_frame, timestamp_sec=3.0)
    if not extracted or not temp_frame.exists():
        extract_keyframe(video_path, temp_frame, timestamp_sec=1.0)

    target_w, target_h = (1080, 1920) if is_short else (1280, 720)

    if temp_frame.exists():
        img = Image.open(temp_frame).convert("RGB")
        try:
            temp_frame.unlink()
        except OSError:
            pass
    else:
        img = Image.new("RGB", (target_w, target_h), (25, 20, 30))

    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Realce según perfil viral
    img = ImageEnhance.Color(img).enhance(style.get("saturation", 1.35))
    img = ImageEnhance.Contrast(img).enhance(style.get("contrast", 1.25))
    img = ImageEnhance.Brightness(img).enhance(style.get("brightness", 1.05))

    # Tono de color tendencia
    img = _apply_color_tone(img, style.get("color_tone", "neon_miami"))

    img = img.convert("RGBA")

    # Viñeta inferior (configurable)
    if style.get("bottom_gradient", True):
        overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        grad_h = int(target_h * 0.35)
        max_alpha = style.get("vignette_alpha", 120)
        for y in range(grad_h):
            alpha = int(max_alpha * (y / grad_h))
            y_pos = target_h - grad_h + y
            draw_ov.line([(0, y_pos), (target_w, y_pos)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, overlay)

    # Texto de gancho viral
    if style.get("text_hook", True) and hook_text:
        draw = ImageDraw.Draw(img)
        _draw_hook_text(draw, hook_text, target_w, target_h, style)

    final_rgb = img.convert("RGB")
    final_rgb.save(output_thumb_path, "JPEG", quality=95)
    tone = style.get("color_tone", "?")
    source = style.get("analysis_source", "default")
    print(f"[✓] Miniatura viral generada ({tone}, {source}) -> {output_thumb_path.name}")
    return output_thumb_path

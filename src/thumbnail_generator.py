import os
import json
import textwrap
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

from .config import CANVAS_WIDTH, CANVAS_HEIGHT
from .emoji_renderer import (
    split_text_and_emojis,
    measure_composite_line,
    draw_composite_line,
    clean_text_preserve_emojis
)


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
    """Obtiene tipografía oficial de marca (Montserrat Black / Anton) o fallback macOS."""
    base_fonts = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    font_configs = [
        (str(base_fonts / "Montserrat-Black.ttf"), 0),
        (str(base_fonts / "Anton-Regular.ttf"), 0),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
        ("/System/Library/Fonts/Avenir Next.ttc", 8),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 9),
        ("/System/Library/Fonts/Supplemental/Futura.ttc", 0),
        ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", 0),
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


def _draw_hook_text(draw_or_img: Any, text: str, img_w: int, img_h: int, style: Dict[str, Any], target_img: Optional[Image.Image] = None) -> None:
    """
    Dibuja el texto del gancho viral con contorno grueso estilo YouTube trending
    y renderizado composite de emojis (cero rectángulos vacíos '[]').
    """
    if not text:
        return

    if isinstance(draw_or_img, Image.Image):
        target_img = draw_or_img
        draw = ImageDraw.Draw(target_img)
    else:
        draw = draw_or_img
        if target_img is None and hasattr(draw, "_image"):
            target_img = draw._image

    clean_text = clean_text_preserve_emojis(text)
    if not clean_text:
        return

    font_size = max(32, int(img_h * style.get("font_size_ratio", 0.07)))
    font = get_best_font(font_size)

    # Limitar a 2 líneas de ~22 chars
    wrapped = textwrap.wrap(clean_text[:80], width=22)[:2]
    line_h = font_size + 8
    total_h = len(wrapped) * line_h
    y_start = img_h - total_h - int(img_h * 0.08)

    stroke_w = style.get("text_stroke_width", 6)
    raw_stroke = style.get("text_stroke", [0, 0, 0])
    raw_fill = style.get("text_color", [255, 230, 0])
    stroke_c = tuple(raw_stroke) + (255,) if len(raw_stroke) == 3 else tuple(raw_stroke)
    fill_c = tuple(raw_fill) + (255,) if len(raw_fill) == 3 else tuple(raw_fill)

    for i, line in enumerate(wrapped):
        tokens = split_text_and_emojis(line)
        line_w, _ = measure_composite_line(tokens, font, emoji_size=font_size)
        x = (img_w - line_w) // 2
        y = y_start + i * line_h

        if target_img is not None:
            draw_composite_line(
                target_img=target_img,
                draw=draw,
                tokens=tokens,
                x=x,
                y=y,
                font=font,
                fill_color=fill_c,
                stroke_color=stroke_c,
                stroke_width=stroke_w,
                emoji_size=font_size
            )
        else:
            # Fallback seguro: solo texto alfanumérico sin emojis para no dibujar rectángulos
            cur_x = x
            for kind, content in tokens:
                if kind == "text":
                    clean_c = re.sub(r'[^\w\s\d¡!¿?,\.:\'-áéíóúÁÉÍÓÚñÑüÜ#$€%&/()+=@_\"“”«»]', '', content)
                    if not clean_c:
                        continue
                    for dx in range(-stroke_w, stroke_w + 1, 2):
                        for dy in range(-stroke_w, stroke_w + 1, 2):
                            if dx != 0 or dy != 0:
                                draw.text((cur_x + dx, y + dy), clean_c, font=font, fill=stroke_c[:3])
                    draw.text((cur_x, y), clean_c, font=font, fill=fill_c[:3])
                    bb = draw.textbbox((0, 0), clean_c, font=font)
                    cur_x += (bb[2] - bb[0])


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

    # Multi-keyframe: extraer varios candidatos tras desaparecer el gancho (t>4s) y elegir el de mayor contraste/brillo
    best_frame = None
    best_energy = -1.0
    candidate_timestamps = [4.5, 8.0, 12.0]

    # Obtener duración total para añadir un candidato a mitad del vídeo
    try:
        dur_probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
        total_dur = float(dur_probe.stdout.strip()) if dur_probe.stdout.strip() else 0
        if total_dur > 14:
            candidate_timestamps.append(round(total_dur / 2, 1))
        elif total_dur > 4:
            candidate_timestamps = [round(total_dur * 0.25, 1), round(total_dur * 0.55, 1), round(total_dur * 0.8, 1)]
    except Exception:
        pass

    from PIL import ImageStat
    for ts in candidate_timestamps:
        cand_frame = output_thumb_path.with_suffix(f".cand_{ts:.0f}.jpg")
        if extract_keyframe(video_path, cand_frame, timestamp_sec=ts) and cand_frame.exists():
            try:
                cand_img = Image.open(cand_frame).convert("RGB").resize((320, 180), Image.Resampling.LANCZOS)
                stat = ImageStat.Stat(cand_img)
                # Energía visual nativa con Pillow: prioriza fotogramas luminosos y nítidos (penaliza planos nocturnos oscuros)
                mean_luma = sum(stat.mean) / 3.0
                dark_penalty = -150.0 if mean_luma < 45.0 else 0.0
                energy = sum(stat.stddev) * 1.8 + sum(stat.mean) * 0.9 + dark_penalty
                if energy > best_energy:
                    best_energy = energy
                    if best_frame and best_frame.exists():
                        best_frame.unlink(missing_ok=True)
                    best_frame = cand_frame
                else:
                    cand_frame.unlink(missing_ok=True)
            except Exception:
                cand_frame.unlink(missing_ok=True)

    if best_frame and best_frame.exists():
        best_frame.rename(temp_frame)
    elif not temp_frame.exists():
        extract_keyframe(video_path, temp_frame, timestamp_sec=1.0)

    target_w, target_h = (CANVAS_WIDTH, CANVAS_HEIGHT) if is_short else (1280, 720)

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

    # Viñeta inferior: Solo para vídeos horizontales (16:9) con texto explicativo.
    # En Shorts verticales, mantener el fotograma 100% limpio y brillante sin oscurecer la imagen.
    if not is_short and style.get("bottom_gradient", True):
        overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        grad_h = int(target_h * 0.35)
        max_alpha = style.get("vignette_alpha", 120)
        for y in range(grad_h):
            alpha = int(max_alpha * (y / grad_h))
            y_pos = target_h - grad_h + y
            draw_ov.line([(0, y_pos), (target_w, y_pos)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, overlay)

    # Texto de gancho viral: SOLO para miniaturas horizontales 16:9 (YouTube estándar).
    # En Shorts verticales 9:16, NO dibujar texto superpuesto en el tercio inferior para evitar
    # colisiones con la interfaz de TikTok/Reels/Shorts y duplicidades con el gancho del vídeo.
    if not is_short and style.get("text_hook", True) and hook_text:
        draw = ImageDraw.Draw(img)
        _draw_hook_text(draw, hook_text, target_w, target_h, style, target_img=img)

    final_rgb = img.convert("RGB")
    final_rgb.save(output_thumb_path, "JPEG", quality=95)
    tone = style.get("color_tone", "?")
    source = style.get("analysis_source", "default")
    print(f"[✓] Miniatura viral generada ({tone}, {source}) -> {output_thumb_path.name}")
    return output_thumb_path


def _classify_caspahz_cover_badge(title_text: str, category_hint: str = "") -> tuple[str, tuple[int, int, int], tuple[int, int, int]]:
    """Devuelve (texto_pildora, color_fondo_rgb, color_texto_rgb) consistente para el feed estilo Caspahz."""
    blob = f"{title_text} {category_hint}".lower()
    if any(k in blob for k in ("coche", "auto", "bugatti", "supercar", "vehic", "moto", "car", "gratis")):
        if any(k in blob for k in ("arma", "cuchillo", "pistola", "rifle", "gun", "weapon", "knife")):
            return ("ARMA OCULTA", (255, 68, 45), (255, 255, 255))
        if any(k in blob for k in ("dinero", "hora", "método", "metodo", "$", "millon", "money")):
            return ("MÉTODO $", (0, 210, 120), (12, 14, 18))
        return ("COCHE GRATIS", (255, 198, 0), (12, 14, 18))
    if any(k in blob for k in ("arma", "cuchillo", "pistola", "rifle", "gun", "weapon", "knife", "oro", "gold")):
        return ("ARMA OCULTA", (255, 68, 45), (255, 255, 255))
    if any(k in blob for k in ("dinero", "hora", "método", "metodo", "$", "millon", "money")):
        return ("MÉTODO $", (0, 210, 120), (12, 14, 18))
    return ("SECRETO GTA 6", (0, 212, 255), (12, 14, 18))


def _condense_caspahz_cover_title(title_text: str, max_chars: int = 26) -> str:
    """Condensa el título a 2-4 palabras de alto impacto visual sin hashtags ni emojis sueltos."""
    import re
    clean = re.sub(r"#\w+", "", title_text or "")
    clean = clean_text_preserve_emojis(clean)
    # Quitar signos/emojis no imprimibles en fuentes estándar para portada limpia
    clean = re.sub(r"[^\w\sáéíóúÁÉÍÓÚñÑüÜ$€!¡?¿\-]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip().upper()
    for prefix in ("GTA 6 ", "GTA VI ", "CÓMO CONSEGUIR ", "COMO CONSEGUIR ", "DÓNDE ENCONTRAR ", "DONDE ENCONTRAR "):
        if clean.startswith(prefix) and len(clean) > len(prefix) + 4:
            clean = clean[len(prefix):].strip()
            break
    if len(clean) <= max_chars:
        return clean or "SECRETO EN LEONIDA"
    words = clean.split()
    out = []
    for w in words:
        cand = " ".join(out + [w])
        if len(cand) <= max_chars:
            out.append(w)
        else:
            break
    return " ".join(out) if out else clean[:max_chars].strip()


def _split_caspahz_two_lines(title_text: str, category_hint: str = "") -> tuple[str, str, tuple[int, int, int]]:
    """
    Genera exactamente 2 líneas cortas estilo Caspahz (Línea 1 blanca + Línea 2 color vibrante):
    Ej: ('COCHE', 'GRATIS', (255, 184, 0)), ('DINERO', '+$500K', (184, 255, 60)), ('ARMA', 'OCULTA', (255, 122, 0)).
    """
    import re
    blob = f"{title_text} {category_hint}".lower()
    # Extraer cantidad de dinero si existe ($500K, $40,000, etc.)
    money_m = re.search(r"\$\s*[\d,\.]+[kKmM]?", title_text or "")

    if any(k in blob for k in ("dinero", "hora", "método", "metodo", "$", "millon", "money", "duplicar")):
        line2 = money_m.group(0).replace(" ", "").upper() if money_m else "RÁPIDO"
        return ("DINERO", line2, (184, 255, 60))
    if any(k in blob for k in ("arma", "cuchillo", "pistola", "rifle", "gun", "weapon", "knife", "oro", "gold")):
        line2 = "DE ORO" if ("oro" in blob or "gold" in blob) else "OCULTA"
        return ("ARMA", line2, (255, 122, 0))
    if re.search(r"\b(coche|coches|auto|autos|bugatti|ferrari|lambo|supercar|veh[ií]culo|veh[ií]culos|moto|motos|car|cars)\b", blob):
        # Intentar extraer marca/modelo o usar GRATIS
        for model in ("BUGATTI", "FERRARI", "LAMBO", "CHEETAH", "PORSCHE", "GTR"):
            if model.lower() in blob:
                return (model, "GRATIS", (255, 184, 0))
        return ("COCHE", "GRATIS", (255, 184, 0))
    return ("SECRETO", "GTA 6", (0, 229, 255))


def _generate_caspahz_cover_via_gemini(
    ref_frame_path: Path,
    output_cover_path: Path,
    line1: str,
    line2: str,
    accent_rgb: tuple[int, int, int],
    title_text: str,
    target_w: int,
    target_h: int,
) -> Optional[Path]:
    """
    Genera la portada cinematográfica 9:16 estilo Caspahz usando Gemini Image
    tomando como referencia el frame de recompensa del clip (coche/arma/dinero).
    """
    if not os.getenv("GEMINI_API_KEY", "").strip() or not ref_frame_path.exists():
        return None
    try:
        import io
        from google.genai import types
        from .translator import get_gemini_client

        accent_desc = "vibrant fiery gold-to-orange gradient"
        icon_desc = "flat bright gold car silhouette icon"
        if accent_rgb == (184, 255, 60):
            accent_desc = "vibrant neon lime-green gradient"
            icon_desc = "flat bright neon lime-green dollar/money icon"
        elif accent_rgb == (255, 122, 0):
            accent_desc = "vibrant fiery orange-to-gold gradient"
            icon_desc = "flat bright gold weapon/gun silhouette icon"
        elif accent_rgb == (0, 229, 255):
            accent_desc = "vibrant neon cyan gradient"
            icon_desc = "flat bright neon cyan pin/target icon"

        prompt = (
            f"Create an ultra-spectacular, viral 9:16 vertical YouTube Shorts cover in the exact high-CTR style of top GTA 6 creator Caspahz, "
            f"inspired by the vehicle/weapon/subject shown in this reference frame (for '{title_text}'): "
            "1. HERO SUBJECT (lower 62% of frame): Dramatic low-angle 3/4 FRONT shot of the exact same car/weapon/reward from the reference frame "
            "in a Vice City / Leonida setting at dramatic golden-hour / neon dusk, with glowing highlights, wet asphalt reflections, "
            "subtle golden rim-light outline around the subject, and subtle floating embers/sparks. Photorealistic GTA 6 RAGE 9 graphics look. "
            "2. TOP GRADIENT & ICON: Smooth dark cinematic gradient in the top 40%. At top center (y=6%), a clean " + icon_desc + ". "
            "3. MASSIVE EDGE-TO-EDGE TYPOGRAPHY (y=12% to 35%, filling ~88% of frame width, tight line spacing, bold geometric Montserrat Black font, soft drop shadow, NO ugly black outline): "
            f"Line 1 (pure bright white): {line1} | Line 2 ({accent_desc}): {line2}. "
            "4. ZERO watermarks, ZERO subtitles, ZERO extra text."
        )

        client = get_gemini_client()
        ref_part = types.Part.from_bytes(data=ref_frame_path.read_bytes(), mime_type="image/jpeg")
        cfg = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="9:16"),
        )
        for img_model in ("gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"):
            try:
                resp = client.models.generate_content(
                    model=img_model,
                    contents=[ref_part, prompt],
                    config=cfg,
                )
                for cand in (resp.candidates or []):
                    for part in (cand.content.parts or []):
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            gen_img = Image.open(io.BytesIO(inline.data)).convert("RGB")
                            if gen_img.size != (target_w, target_h):
                                gen_img = gen_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                            gen_img.save(output_cover_path, "JPEG", quality=95)
                            print(f"[✓ Caspahz AI Cover] Portada generada con {img_model} ('{line1} / {line2}') -> {output_cover_path.name}")
                            return output_cover_path
            except Exception as me:
                print(f"[Caspahz AI Cover] {img_model} no disponible: {me}")
    except Exception as e:
        print(f"[Caspahz AI Cover] Fallback a Pillow: {e}")
    return None


def _generate_caspahz_bg_via_pollinations(
    title_text: str,
    line1: str,
    line2: str,
    target_w: int,
    target_h: int,
) -> Optional[Image.Image]:
    """Fallback gratuito sin facturación: genera fondo limpio 9:16 vía Pollinations.ai (sin texto)."""
    try:
        import io
        import urllib.parse
        import requests
        subject = "luxury red supercar parked in front of Miami palm mansion at neon dusk, wet asphalt reflections, golden rim light"
        blob = f"{title_text} {line1} {line2}".lower()
        if any(k in blob for k in ("arma", "cuchillo", "pistola", "lmg", "rifle", "gun", "weapon")):
            subject = "golden tactical assault rifle and character holding legendary weapon in Vice City street at sunset, dramatic rim lighting"
        elif any(k in blob for k in ("dinero", "$", "money", "método")):
            subject = "luxury sports car and stacks of cash glowing green neon in Miami Vice City night street, wet asphalt reflections"
        prompt = f"GTA 6 RAGE 9 photorealistic game screenshot, {subject}, clean image, no text, no watermark, no logos, vertical 9:16"
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=720&height=1280&nologo=true&enhance=true"
        r = requests.get(url, timeout=35)
        if r.status_code == 200 and len(r.content) > 15000:
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            return im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"[Caspahz Cover] Pollinations fallback no disponible: {e}")
    return None


def render_caspahz_cover_image(
    video_path: Path,
    output_cover_path: Path,
    title_text: str,
    category_hint: str = "",
    clean_source_video: Optional[Path] = None,
) -> Optional[Path]:
    """
    Genera una portada vertical 9:16 full-bleed estilo Caspahz para inyectar en Frame 0 (0.12s):
    - Muestrea `clean_source_video` (sin subtítulos quemados) a lo largo de todo el clip (15%-90%)
      y usa Gemini Vision para elegir el mejor frame de la RECOMPENSA (coche, arma, personaje) sin mapa.
    - Recorta/escala la zona central a 100% pantalla 9:16 (sin barras negras/blur).
    - Degradado superior oscuro (42% altura) + 2 líneas GIGANTES estilo Caspahz.
    """
    target_w, target_h = CANVAS_WIDTH, CANVAS_HEIGHT
    total_dur = 25.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-show_entries", "format=duration",
             "-of", "json", str(video_path)],
            capture_output=True, text=True, timeout=8
        )
        if probe.returncode == 0 and probe.stdout:
            pdata = json.loads(probe.stdout)
            v_st = (pdata.get("streams") or [{}])[0]
            if int(v_st.get("width", 0)) > 0 and int(v_st.get("height", 0)) > 0:
                target_w, target_h = int(v_st["width"]), int(v_st["height"])
            dur_v = float((pdata.get("format") or {}).get("duration") or 0)
            if dur_v > 4.0:
                total_dur = dur_v
    except Exception:
        pass

    sample_video = clean_source_video if (clean_source_video and Path(clean_source_video).exists()) else video_path
    sample_times = [round(total_dur * r, 1) for r in (0.06, 0.18, 0.34, 0.50, 0.66, 0.80, 0.92)]
    candidates: list[Path] = []
    for idx, ts in enumerate(sample_times):
        cand = output_cover_path.with_suffix(f".caspahz_{idx}.jpg")
        if extract_keyframe(sample_video, cand, timestamp_sec=ts) and cand.exists():
            candidates.append(cand)

    def _is_map_or_menu_frame(img_path: Path) -> bool:
        try:
            im = Image.open(img_path).convert("RGB").resize((160, 90), Image.Resampling.BILINEAR)
            px = list(im.getdata())
            n_px = max(1, len(px))
            # Mapa de Leonida/GTA: gran proporción de agua cian/turquesa o verde plano (B>115, G>120, R<95)
            cyan_green = sum(1 for r, g, b in px if (b > 115 and g > 120 and r < 95) or (g > 150 and r < 140 and b < 140))
            if cyan_green / n_px >= 0.28:
                return True
            # Barra superior oscura de menú de pausa (MAP / BRIEF / PROGRESS)
            top_strip = px[:160 * 10]
            top_luma = sum((r + g + b) / 3.0 for r, g, b in top_strip) / max(1, len(top_strip))
            if top_luma < 28.0 and (cyan_green / n_px) >= 0.12:
                return True
        except Exception:
            pass
        return False

    non_map_candidates = [c for c in candidates if not _is_map_or_menu_frame(c)]
    pool_for_selection = non_map_candidates if non_map_candidates else candidates

    best_frame: Optional[Path] = None
    if pool_for_selection and os.getenv("GEMINI_API_KEY", "").strip():
        try:
            from google.genai import types
            from .translator import get_gemini_client, generate_content_with_retry, clean_srt_response
            parts = [types.Part.from_bytes(data=c.read_bytes(), mime_type="image/jpeg") for c in pool_for_selection]
            parts.append(
                f"Te paso {len(pool_for_selection)} fotogramas de un clip de GTA 6 sobre '{title_text}'. "
                "Elige el índice (0 a N-1) que muestre MEJOR la recompensa principal (el COCHE, arma, dinero o personaje en gameplay 3D en primer plano). "
                "RECHAZA OBLIGATORIAMENTE cualquier fotograma que sea un MAPA 2D/3D (agua azul/turquesa, calles en vista aérea, barra 'MAP / BRIEF / PROGRESS / JASON & LUCIA'), "
                "menú de pausa, pantalla de estadísticas/tablas o subtítulos grandes. "
                'Responde SOLO JSON: {"best_idx": 0}'
            )
            resp = generate_content_with_retry(client=get_gemini_client(), contents=parts)
            data = json.loads(clean_srt_response(resp.text or "{}"))
            b_idx = int(data.get("best_idx", 0))
            if 0 <= b_idx < len(pool_for_selection):
                best_frame = pool_for_selection[b_idx]
        except Exception as e:
            print(f"[Caspahz Cover] Fallback selector visual: {e}")

    if best_frame is None and pool_for_selection:
        from PIL import ImageStat
        best_energy = -1.0
        for cand in pool_for_selection:
            try:
                c_img = Image.open(cand).convert("RGB").resize((270, 480), Image.Resampling.LANCZOS)
                stat = ImageStat.Stat(c_img)
                luma = sum(stat.mean) / 3.0
                dark_pen = -160.0 if luma < 42.0 else 0.0
                energy = sum(stat.stddev) * 1.8 + luma * 0.9 + dark_pen
                if energy > best_energy:
                    best_energy = energy
                    best_frame = cand
            except Exception:
                pass

    line1, line2, accent_rgb = _split_caspahz_two_lines(title_text, category_hint)

    # Intentar primero generación cinematográfica vía Gemini Image solo si está habilitada (requiere facturación)
    if (
        os.getenv("ENABLE_GEMINI_IMAGE_COVER", "false").lower() in ("true", "1", "yes")
        and best_frame
        and best_frame.exists()
    ):
        ai_cover = _generate_caspahz_cover_via_gemini(
            ref_frame_path=best_frame,
            output_cover_path=output_cover_path,
            line1=line1,
            line2=line2,
            accent_rgb=accent_rgb,
            title_text=title_text,
            target_w=target_w,
            target_h=target_h,
        )
        if ai_cover and ai_cover.exists():
            for cand in candidates:
                try:
                    cand.unlink(missing_ok=True)
                except Exception:
                    pass
            return ai_cover

    if best_frame and best_frame.exists():
        img = Image.open(best_frame).convert("RGB")
    else:
        img = _generate_caspahz_bg_via_pollinations(title_text, line1, line2, target_w, target_h)
        if img is None:
            img = Image.new("RGB", (target_w, target_h), (20, 22, 30))

    for cand in candidates:
        try:
            cand.unlink(missing_ok=True)
        except Exception:
            pass

    # Full-bleed center crop: asegurar relleno 9:16 limpio sin bandas laterales ni negras
    iw, ih = img.size
    target_ratio = target_w / target_h
    if iw > ih:
        # Fuente horizontal 16:9 -> recorte vertical 9:16 centrado en la acción
        crop_w = int(ih * target_ratio)
        left = max(0, (iw - crop_w) // 2)
        img = img.crop((left, 0, left + crop_w, ih))
    elif ih > iw:
        # Fuente vertical ya renderizada -> recortar 65% central para quitar bandas/subtítulos
        crop_h = int(ih * 0.65)
        crop_w = int(crop_h * target_ratio)
        if crop_w <= iw and crop_w > 100:
            left = (iw - crop_w) // 2
            top = (ih - crop_h) // 2
            img = img.crop((left, top, left + crop_w, top + crop_h))

    if img.size != (target_w, target_h):
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Auto-exposición + acabado cinematográfico pro (levanta escenas oscuras para que la portada brille en el feed)
    from PIL import ImageStat, ImageFilter
    cover_luma = float(ImageStat.Stat(img.convert("L")).mean[0])
    if cover_luma < 90.0:
        img = ImageEnhance.Brightness(img).enhance(1.34)
        img = ImageEnhance.Contrast(img).enhance(1.20)
        img = ImageEnhance.Color(img).enhance(1.28)
        img = ImageEnhance.Sharpness(img).enhance(1.30)
    else:
        img = ImageEnhance.Color(img).enhance(1.24)
        img = ImageEnhance.Contrast(img).enhance(1.18)
        img = ImageEnhance.Brightness(img).enhance(1.08)
        img = ImageEnhance.Sharpness(img).enhance(1.25)
    img = img.convert("RGBA")

    # Degradado cinematográfico superior + viñeta inferior sutil para dar profundidad de póster
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    top_grad_h = int(target_h * 0.44)
    for y in range(top_grad_h):
        alpha = int(215 * ((1.0 - (y / top_grad_h)) ** 1.35))
        draw_ov.line([(0, y), (target_w, y)], fill=(6, 8, 14, alpha))
    bot_grad_h = int(target_h * 0.22)
    for i in range(bot_grad_h):
        y = target_h - 1 - i
        alpha = int(150 * ((1.0 - (i / bot_grad_h)) ** 1.5))
        draw_ov.line([(0, y), (target_w, y)], fill=(6, 8, 14, alpha))
    img = Image.alpha_composite(img, overlay)

    scale = target_w / 1080.0
    # Halo ambiental suave detrás del titular con el color de acento
    glow_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw_glow = ImageDraw.Draw(glow_layer)
    gx0, gy0 = int(target_w * 0.10), int(target_h * 0.14)
    gx1, gy1 = int(target_w * 0.90), int(target_h * 0.34)
    draw_glow.ellipse([gx0, gy0, gx1, gy1], fill=accent_rgb + (72,))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=int(95 * scale)))
    img = Image.alpha_composite(img, glow_layer)

    draw = ImageDraw.Draw(img)

    def _fit_font(text: str, base_px: int):
        size = int(base_px * scale)
        max_text_w = int(target_w * 0.84)
        while size > int(68 * scale):
            f = get_best_font(size)
            bb = draw.textbbox((0, 0), text, font=f)
            if (bb[2] - bb[0]) <= max_text_w:
                return f
            size -= int(8 * scale)
        return get_best_font(max(48, size))

    # Micro-badge superior estilo guía pro dentro de la Safe Zone 3:4 (y=13.5% @ 1920h = 259px)
    badge_txt = "GUÍA GTA 6"
    badge_font = get_best_font(max(24, int(36 * scale)))
    b_bb = draw.textbbox((0, 0), badge_txt, font=badge_font)
    bw, bh = b_bb[2] - b_bb[0], b_bb[3] - b_bb[1]
    pad_x, pad_y = int(28 * scale), int(12 * scale)
    bx0 = (target_w - (bw + pad_x * 2)) // 2
    by0 = int(target_h * 0.138)
    bx1 = bx0 + bw + pad_x * 2
    by1 = by0 + bh + pad_y * 2
    draw.rounded_rectangle(
        [bx0, by0, bx1, by1],
        radius=int(24 * scale),
        fill=(12, 14, 22, 215),
        outline=accent_rgb + (235,),
        width=max(2, int(4 * scale)),
    )
    draw.text((bx0 + pad_x - b_bb[0], by0 + pad_y - b_bb[1]), badge_txt, font=badge_font, fill=accent_rgb + (255,))

    font1 = _fit_font(line1, 145)
    font2 = _fit_font(line2, 158)

    # y=18.2% (349px @ 1920h) debajo del micro-badge y 100% dentro del recorte 3:4 de TikTok
    y_cur = by1 + int(22 * scale)
    shadow_off = max(5, int(10 * scale))
    stroke_w = max(3, int(6 * scale))

    # Glow neón sutil en la línea 2 (color acento)
    txt_glow = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw_tg = ImageDraw.Draw(txt_glow)
    positions = []
    for idx_l, (txt, fnt, col) in enumerate((
        (line1, font1, (255, 255, 255, 255)),
        (line2, font2, accent_rgb + (255,)),
    )):
        bb = draw.textbbox((0, 0), txt, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx = (target_w - tw) // 2 - bb[0]
        ty = y_cur - bb[1]
        positions.append((idx_l, txt, fnt, col, tx, ty))
        if idx_l == 1:
            draw_tg.text((tx, ty), txt, font=fnt, fill=accent_rgb + (155,))
        y_cur += th + int(22 * scale)

    txt_glow = txt_glow.filter(ImageFilter.GaussianBlur(radius=int(22 * scale)))
    img = Image.alpha_composite(img, txt_glow)
    draw = ImageDraw.Draw(img)

    for idx_l, txt, fnt, col, tx, ty in positions:
        draw.text((tx + shadow_off, ty + shadow_off), txt, font=fnt, fill=(0, 0, 0, 220))
        draw.text(
            (tx, ty),
            txt,
            font=fnt,
            fill=col,
            stroke_width=stroke_w,
            stroke_fill=(8, 10, 16, 245),
        )

    img.convert("RGB").save(output_cover_path, "JPEG", quality=95)
    print(f"[✓ Caspahz Cover] Portada 9:16 Pro generada ('{line1} / {line2}', luma={cover_luma:.0f}) -> {output_cover_path.name}")
    return output_cover_path

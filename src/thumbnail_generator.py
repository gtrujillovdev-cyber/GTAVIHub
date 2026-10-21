import os
import subprocess
from pathlib import Path
from typing import Optional
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
    """Obtiene tipografía moderna y limpia en macOS."""
    font_configs = [
        ("/System/Library/Fonts/Avenir Next.ttc", 8),
        ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 9),
        ("/System/Library/Fonts/Supplemental/Futura.ttc", 0)
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

def create_video_thumbnail(
    video_path: Path,
    output_thumb_path: Path,
    hook_text: str = "",
    creator_tag: str = "",
    is_short: bool = False
) -> Optional[Path]:
    """
    Genera una miniatura limpia y cinemática de alto impacto:
    - Extrae el mejor fotograma del vídeo renderizado.
    - Aplica realce de color cinemático (saturación y contraste vibrantes).
    - Viñeta oscura sutil inferior.
    - CERO rótulos invasivos, CERO cajas rotas '[]'.
    """
    temp_frame = output_thumb_path.with_suffix(".tmp_frame.jpg")
    
    # Extraer fotograma al segundo 3 o 1
    extracted = extract_keyframe(video_path, temp_frame, timestamp_sec=3.0)
    if not extracted or not temp_frame.exists():
        extract_keyframe(video_path, temp_frame, timestamp_sec=1.0)

    target_w, target_h = (1080, 1920) if is_short else (1280, 720)

    if temp_frame.exists():
        img = Image.open(temp_frame).convert("RGBA")
        try:
            temp_frame.unlink()
        except OSError:
            pass
    else:
        img = Image.new("RGBA", (target_w, target_h), (25, 20, 30, 255))

    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Realce de color sutil cinemático
    rgb_img = img.convert("RGB")
    enhancer_color = ImageEnhance.Color(rgb_img)
    rgb_img = enhancer_color.enhance(1.15)
    enhancer_contrast = ImageEnhance.Contrast(rgb_img)
    rgb_img = enhancer_contrast.enhance(1.10)
    img = rgb_img.convert("RGBA")

    # Viñeta oscura inferior sutil (para shorts o miniaturas)
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    grad_h = int(target_h * 0.25)
    for y in range(grad_h):
        alpha = int(100 * (y / grad_h))
        y_pos = target_h - grad_h + y
        draw_overlay.line([(0, y_pos), (target_w, y_pos)], fill=(0, 0, 0, alpha))

    img = Image.alpha_composite(img, overlay)

    final_rgb = img.convert("RGB")
    final_rgb.save(output_thumb_path, "JPEG", quality=95)
    print(f"[✓] Miniatura cinemática generada -> {output_thumb_path.name}")
    return output_thumb_path
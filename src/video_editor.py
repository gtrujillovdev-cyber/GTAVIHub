import os
import re
import json
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont

from .config import FFMPEG_VIDEO_CODEC, FFMPEG_BITRATE

def get_video_dimensions(video_path: Path) -> Tuple[int, int]:
    """Obtiene ancho y alto del vídeo usando ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            str(video_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except Exception:
        return 1920, 1080

def get_best_font(size: int = 58):
    """
    Obtiene la mejor tipografía sans-serif moderna disponible en macOS.
    Prioridad: Avenir Next Heavy -> DIN Alternate Bold -> Futura.
    """
    font_configs = [
        ("/System/Library/Fonts/Avenir Next.ttc", 8), # Avenir Next Heavy
        ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 9), # Condensed Black
        ("/System/Library/Fonts/Supplemental/Futura.ttc", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 0)
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

def parse_time(t_str: str) -> float:
    """Convierte '00:01:23,456' a segundos flotantes."""
    try:
        h, m, s = t_str.strip().replace(',', '.').split(':')
        return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception:
        return 0.0

def clean_text_no_emoji(text: str) -> str:
    """Elimina emojis y símbolos raros que provocan cajas rotas '[]' en Pillow."""
    cleaned = re.sub(r'[^\w\s\d¡!¿?,\.:\'-áéíóúÁÉÍÓÚñÑüÜ]', '', text)
    return " ".join(cleaned.split()).strip()

def split_cue_into_micro_bursts(text: str, start: float, end: float, max_words: int = 3) -> List[Dict[str, Any]]:
    """
    Divide frases largas en ráfagas dinámicas de 2-3 palabras (ritmo Opus Clip / TikTok / MrBeast).
    Garantiza retención visual y sincronización rápida con la voz.
    """
    words = text.split()
    if len(words) <= max_words:
        return [{"start": start, "end": end, "text": text}]

    chunks = []
    i = 0
    while i < len(words):
        remaining = len(words) - i
        if remaining == 4:
            chunks.append(words[i:i + 2])
            chunks.append(words[i + 2:i + 4])
            break
        elif remaining <= max_words:
            chunks.append(words[i:])
            break
        else:
            chunks.append(words[i:i + max_words])
            i += max_words

    total_dur = max(0.5, end - start)
    total_words = len(words)
    res = []
    cur_t = start
    for c in chunks:
        c_dur = total_dur * (len(c) / total_words)
        res.append({
            "start": round(cur_t, 2),
            "end": round(cur_t + c_dur - 0.03, 2),
            "text": " ".join(c)
        })
        cur_t += c_dur
    return res

def parse_srt_file(srt_path: Path) -> List[Dict[str, Any]]:
    """Parsea el archivo SRT y devuelve micro-cues dinámicas de 2-3 palabras."""
    if not srt_path.exists():
        return []
    
    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().replace("\r\n", "\n")

    blocks = content.strip().split("\n\n")
    cues = []
    for b in blocks:
        lines = [line.strip() for line in b.split("\n") if line.strip()]
        if len(lines) >= 3 and "-->" in lines[1]:
            start_str, end_str = lines[1].split("-->")
            start_sec = parse_time(start_str)
            end_sec = parse_time(end_str)
            raw_text = " ".join(lines[2:]).strip()
            text = clean_text_no_emoji(raw_text)
            if not text or end_sec <= start_sec:
                continue

            bursts = split_cue_into_micro_bursts(text, start_sec, end_sec, max_words=3)
            cues.extend(bursts)
    return cues

def render_modern_floating_subtitle(text: str, is_vertical: bool, output_path: Path) -> bool:
    """
    Subtítulos Virales Modernos (Estilo Opus Clip / CapCut / MrBeast):
    - 100% flotantes: CERO cajas oscuras, CERO marcos fucsia/cian, CERO cajas rotas '[]'.
    - Tipografía moderna Avenir Next Heavy (58px).
    - Primera palabra en Amarillo Eléctrico (#FFE500), resto en Blanco Puro (#FFFFFF).
    - Trazo negro fino de 3.5px + sombra 3D suave (offset +3, +4).
    - Margen seguro: max_w = 720px (al menos 180px libres a cada lado).
    """
    cleaned = clean_text_no_emoji(text).upper()
    words = cleaned.split()
    if not words:
        return False

    max_w = 720 if is_vertical else 1100
    font_size = 58 if is_vertical else 42
    font = get_best_font(size=font_size)

    temp_img = Image.new("RGBA", (1, 1))
    d_temp = ImageDraw.Draw(temp_img)

    # Si supera el ancho máximo seguro, reducir ligeramente la fuente
    while font_size > 34:
        test_w = sum(d_temp.textbbox((0, 0), w, font=font)[2] - d_temp.textbbox((0, 0), w, font=font)[0] for w in words)
        test_w += 18 * (len(words) - 1)
        if test_w <= max_w:
            break
        font_size -= 4
        font = get_best_font(size=font_size)

    space_w = 18
    total_w = sum(d_temp.textbbox((0, 0), w, font=font)[2] - d_temp.textbbox((0, 0), w, font=font)[0] for w in words) + space_w * (len(words) - 1)
    sample_bb = font.getbbox("AY")
    line_h = (sample_bb[3] - sample_bb[1]) + 20

    box_w = int(total_w + 50)
    box_h = int(line_h + 24)

    # Imagen transparente pura
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cur_x = 25
    cur_y = 10

    for idx, w in enumerate(words):
        wb = d_temp.textbbox((0, 0), w, font=font)
        ww = wb[2] - wb[0]
        # Primera palabra en Amarillo Eléctrico (#FFE500), resto en Blanco Puro
        text_color = (255, 229, 0, 255) if idx == 0 else (255, 255, 255, 255)
        
        # Sombra de profundidad 3D
        d.text((cur_x + 3, cur_y + 4), w, font=font, fill=(0, 0, 0, 220))
        # Trazo negro nítido de 3.5px
        d.text((cur_x, cur_y), w, font=font, fill=text_color, stroke_width=3, stroke_fill=(0, 0, 0, 255))
        
        cur_x += ww + space_w

    img.save(output_path, "PNG")
    return True

def create_subtle_vignette(output_png: Path, fg_top: int = 160, fg_bottom: int = 1760) -> bool:
    """
    Genera gradientes cinemáticos sutiles:
    - Viñetas en extremos superior (160px) e inferior (160px).
    - Sombras suaves en los puntos de unión (fg_top y fg_bottom) para integrar el vídeo sobre el blur.
    """
    w, h = 1080, 1920
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 1. Viñeta superior extrema
    for y in range(fg_top):
        alpha = int(110 * (1 - (y / fg_top)))
        d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    # 2. Sombra de unión superior (alrededor de fg_top)
    for i in range(25):
        alpha = int(75 * (1 - (i / 25)))
        d.line([(0, fg_top - i), (w, fg_top - i)], fill=(0, 0, 0, alpha))
        d.line([(0, fg_top + i), (w, fg_top + i)], fill=(0, 0, 0, alpha // 2))

    # 3. Sombra de unión inferior (alrededor de fg_bottom)
    for i in range(25):
        alpha = int(75 * (1 - (i / 25)))
        d.line([(0, fg_bottom - i), (w, fg_bottom - i)], fill=(0, 0, 0, alpha // 2))
        d.line([(0, fg_bottom + i), (w, fg_bottom + i)], fill=(0, 0, 0, alpha))

    # 4. Viñeta inferior extrema
    for y in range(h - fg_bottom):
        alpha = int(110 * (y / (h - fg_bottom)))
        y_pos = fg_bottom + y
        d.line([(0, y_pos), (w, y_pos)], fill=(0, 0, 0, alpha))

    img.save(output_png, "PNG")
    return True

def render_final_video(
    input_video: Path,
    output_video: Path,
    srt_subtitles: Optional[Path] = None,
    dub_audio: Optional[Path] = None,
    force_short_format: bool = False,
    hook_text: str = ""
) -> bool:
    """
    Ensamblaje viral definitivo y limpio:
    1. Zoom & Crop Maximizado (83.3% de pantalla):
       - Primer plano ampliado a 1080x1600 (y=160 a y=1760), recortando laterales para centrar la acción.
       - Fondo velvet blur (boxblur 25:5) reducido a una franja elegante superior e inferior de 160px.
       - Filtro unsharp para nitidez 4K en texturas y caras.
    2. CERO retraso de intro: El vídeo y el audio arrancan DIRECTAMENTE en 0.0s.
    3. CERO rótulos invasivos: CERO cajas negras, CERO bordes fucsia/cian, CERO '[]'.
    4. Subtítulos dinámicos de 2-3 palabras flotantes (blanco + palabra clave en amarillo) centrados a y=1280.
    5. Normalización de audio YouTube Shorts (-14 LUFS).
    6. Aceleración nativa VideoToolbox en Apple Silicon M4.
    """
    temp_dir = input_video.parent
    base_name = input_video.stem
    width, height = get_video_dimensions(input_video)
    is_already_vertical = (height > width)
    is_vertical = force_short_format or is_already_vertical

    fg_h = 1600
    fg_y = 160
    fg_bottom = fg_y + fg_h

    print(f"[*] Ensamblando vídeo con Zoom & Crop Maximizado ({fg_h}px / 83.3% alto) (Vertical: {is_vertical})...")

    # 1. Viñeta y sombras de unión
    vignette_png = temp_dir / f"{base_name}_vignette.png"
    create_subtle_vignette(vignette_png, fg_top=fg_y, fg_bottom=fg_bottom)

    # 2. Subtítulos dinámicos flotantes
    cues = parse_srt_file(srt_subtitles) if srt_subtitles else []
    sub_cues = cues[:80]
    sub_pngs = []
    for idx, cue in enumerate(sub_cues):
        sub_png = temp_dir / f"{base_name}_sub_{idx}.png"
        rendered = render_modern_floating_subtitle(cue["text"], is_vertical=is_vertical, output_path=sub_png)
        if rendered:
            sub_pngs.append((sub_png, cue["start"], cue["end"]))

    # 3. Construcción del comando FFmpeg
    cmd = ["ffmpeg", "-y", "-i", str(input_video)]
    input_idx = 1

    # Audio doblado si existe
    if dub_audio and dub_audio.exists():
        cmd.extend(["-i", str(dub_audio)])
        dub_idx = input_idx
        input_idx += 1
        audio_filter = f"[0:a]volume=0.20[bg_a];[bg_a][{dub_idx}:a]amix=inputs=2:duration=first,loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
    else:
        audio_filter = "[0:a]loudnorm=I=-14:LRA=7:TP=-1.5[aout]"

    # Viñeta discreta
    cmd.extend(["-i", str(vignette_png)])
    vignette_idx = input_idx
    input_idx += 1

    # Subtítulos como inputs
    sub_inputs_start = input_idx
    for sp, _, _ in sub_pngs:
        cmd.extend(["-i", str(sp)])
        input_idx += 1

    filter_chains = []

    # A) Base de vídeo: ZOOM & CROP MAXIMIZADO (83.3% del alto)
    if is_vertical and not is_already_vertical:
        # Fondo: desenfoque velvet 1080x1920 con boxblur suave
        # Primer plano: ampliado a 1600px de alto, centrado y cortando laterales para llenar el 83.3% del frame
        v_base = (
            "[0:v]split[v1][v2];"
            "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.06:contrast=1.05:saturation=1.2[bg];"
            f"[v2]scale=-2:{fg_h},crop=1080:{fg_h}:(iw-1080)/2:0,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
            f"[bg][fg]overlay=0:{fg_y}[v_framed]"
        )
    elif is_vertical:
        v_base = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[v_framed]"
    else:
        v_base = "[0:v]unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[v_framed]"
    
    filter_chains.append(v_base)
    current_v = "v_framed"

    # B) Superponer Viñeta sutil y sombras de unión
    filter_chains.append(f"[{current_v}][{vignette_idx}:v]overlay=0:0[v_vignetted]")
    current_v = "v_vignetted"

    # C) Superponer Subtítulos modernos flotantes (centrados horizontalmente en zona segura y=1280)
    sub_y = "1280" if is_vertical else "H-h-90"
    for s_idx, (_, start_s, end_s) in enumerate(sub_pngs):
        in_id = sub_inputs_start + s_idx
        next_v = f"v_sub_{s_idx}"
        filter_chains.append(
            f"[{current_v}][{in_id}:v]overlay=(W-w)/2:{sub_y}:enable='between(t,{start_s:.2f},{end_s:.2f})'[{next_v}]"
        )
        current_v = next_v

    filter_chains.append(f"[{current_v}]null[v_body]")

    if audio_filter:
        filter_chains.append(audio_filter)

    cmd.extend(["-filter_complex", ";".join(filter_chains)])
    cmd.extend(["-map", "[v_body]"])
    cmd.extend(["-c:v", FFMPEG_VIDEO_CODEC, "-b:v", FFMPEG_BITRATE])

    if audio_filter:
        cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])

    cmd.append(str(output_video))

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[✓] Vídeo exportado con éxito -> {output_video.name}")
    except subprocess.CalledProcessError as e:
        print(f"[!] Error de renderizado FFmpeg: {e.stderr.strip() if e.stderr else e}")
        return False

    # Limpieza de imágenes temporales
    for sp, _, _ in sub_pngs:
        try:
            sp.unlink()
        except OSError:
            pass
    if vignette_png.exists():
        try:
            vignette_png.unlink()
        except OSError:
            pass

    return True
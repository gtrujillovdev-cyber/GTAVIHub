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
    Divide frases en ráfagas dinámicas de 2-3 palabras (ritmo viral TikTok / Shorts).
    Garantiza que nunca se solapen en el tiempo.
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
        next_t = cur_t + c_dur
        res.append({
            "start": round(cur_t, 2),
            "end": round(next_t - 0.02, 2),
            "text": " ".join(c)
        })
        cur_t = next_t
    return res

def calculate_word_timing(words: List[str], start_t: float, end_t: float) -> List[Dict[str, Any]]:
    """
    Calcula los intervalos de tiempo palabra por palabra ponderados fonéticamente.
    Garantiza una separación estricta de 0.02s para que NUNCA se pisen.
    """
    total_dur = max(0.3, end_t - start_t)
    weights = [len(w) + 1 for w in words]
    total_weight = sum(weights)
    
    timings = []
    cur_t = start_t
    for idx, (w, wt) in enumerate(zip(words, weights)):
        w_dur = total_dur * (wt / total_weight)
        next_t = cur_t + w_dur
        if idx == len(words) - 1:
            next_t = end_t
        timings.append({
            "word_idx": idx,
            "word": w,
            "start": round(cur_t, 2),
            "end": round(next_t - 0.02, 2)
        })
        cur_t = next_t
    return timings

def parse_srt_file(srt_path: Path) -> List[Dict[str, Any]]:
    """
    Parsea y desduplica subtítulos SRT eliminando el 'rolling buffer' de YouTube:
    1. Filtra micro-bloques de transición (< 0.25s).
    2. Elimina líneas repetidas del bloque anterior.
    3. Asegura estricta monotonicidad temporal (cero solapamientos entre frases).
    4. Devuelve micro-ráfagas limpias de 2-3 palabras.
    """
    if not srt_path.exists():
        return []
    
    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().replace("\r\n", "\n")

    blocks = content.strip().split("\n\n")
    raw_cues = []
    last_text = ""

    for b in blocks:
        lines = [line.strip() for line in b.split("\n") if line.strip()]
        if len(lines) >= 3 and "-->" in lines[1]:
            start_str, end_str = lines[1].split("-->")
            start_sec = parse_time(start_str)
            end_sec = parse_time(end_str)
            
            # Descartar micro-glitches de 10-100ms
            if (end_sec - start_sec) < 0.25:
                continue

            text_lines = [clean_text_no_emoji(l) for l in lines[2:] if clean_text_no_emoji(l)]
            if not text_lines:
                continue

            # Desduplicar el buffer rodante de YouTube (teleprompter acumulativo)
            new_lines = [tl for tl in text_lines if tl not in last_text]
            if not new_lines:
                full_t = " ".join(text_lines)
                if full_t.startswith(last_text) and len(full_t) > len(last_text):
                    added = full_t[len(last_text):].strip()
                    if added:
                        new_lines = [added]
                else:
                    continue

            final_text = " ".join(new_lines).strip()
            if not final_text:
                continue

            last_text = " ".join(text_lines).strip()
            raw_cues.append({
                "start": start_sec,
                "end": end_sec,
                "text": final_text
            })

    # Asegurar orden estrictamente secuencial y sin solapamiento
    all_bursts = []
    last_end = 0.0
    for c in raw_cues:
        start = max(c["start"], last_end + 0.03)
        end = max(c["end"], start + 0.6)
        bursts = split_cue_into_micro_bursts(c["text"], start, end, max_words=3)
        for b in bursts:
            if b["start"] < last_end:
                b["start"] = round(last_end + 0.02, 2)
            if b["end"] <= b["start"]:
                b["end"] = round(b["start"] + 0.45, 2)
            all_bursts.append(b)
            last_end = b["end"]

    return all_bursts

def render_karaoke_subtitle_state(words: List[str], active_idx: int, is_vertical: bool, output_path: Path) -> bool:
    """
    Renderiza un estado Karaoke palabra por palabra:
    - La línea permanece 100% fija y estable horizontalmente.
    - La palabra activa se ilumina en Amarillo Eléctrico (#FFE500) con trazo reforzado.
    - Las palabras inactivas permanecen en Blanco Puro (#FFFFFF).
    - CERO cajas oscuras ni marcos.
    """
    if not words:
        return False

    max_w = 720 if is_vertical else 1100
    font_size = 58 if is_vertical else 42
    font = get_best_font(size=font_size)

    temp_img = Image.new("RGBA", (1, 1))
    d_temp = ImageDraw.Draw(temp_img)

    # Ajustar si supera ancho máximo seguro
    while font_size > 34:
        test_w = sum(d_temp.textbbox((0, 0), w, font=font)[2] - d_temp.textbbox((0, 0), w, font=font)[0] for w in words)
        test_w += 18 * (len(words) - 1)
        if test_w <= max_w:
            break
        font_size -= 4
        font = get_best_font(size=font_size)

    space_w = 18
    word_widths = [d_temp.textbbox((0, 0), w, font=font)[2] - d_temp.textbbox((0, 0), w, font=font)[0] for w in words]
    total_w = sum(word_widths) + space_w * (len(words) - 1)
    sample_bb = font.getbbox("AY")
    line_h = (sample_bb[3] - sample_bb[1]) + 20

    box_w = int(total_w + 50)
    box_h = int(line_h + 24)

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cur_x = 25
    cur_y = 10

    for idx, w in enumerate(words):
        ww = word_widths[idx]
        is_active = (idx == active_idx)
        text_color = (255, 229, 0, 255) if is_active else (240, 240, 245, 255)
        stroke_w = 4 if is_active else 3

        # Sombra de profundidad 3D
        d.text((cur_x + 3, cur_y + 4), w, font=font, fill=(0, 0, 0, 220))
        # Trazo negro nítido
        d.text((cur_x, cur_y), w, font=font, fill=text_color, stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
        
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

    for y in range(fg_top):
        alpha = int(110 * (1 - (y / fg_top)))
        d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    for i in range(25):
        alpha = int(75 * (1 - (i / 25)))
        d.line([(0, fg_top - i), (w, fg_top - i)], fill=(0, 0, 0, alpha))
        d.line([(0, fg_top + i), (w, fg_top + i)], fill=(0, 0, 0, alpha // 2))

    for i in range(25):
        alpha = int(75 * (1 - (i / 25)))
        d.line([(0, fg_bottom - i), (w, fg_bottom - i)], fill=(0, 0, 0, alpha // 2))
        d.line([(0, fg_bottom + i), (w, fg_bottom + i)], fill=(0, 0, 0, alpha))

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
    Ensamblaje viral definitivo con KARAOKE DINÁMICO palabra por palabra y ANTI-COLISIÓN:
    1. Zoom & Crop Maximizado (83.3% de pantalla):
       - Primer plano ampliado a 1080x1600 (y=160 a y=1760), cortando laterales para centrar acción.
       - Fondo velvet blur (boxblur 25:5) reducido a 160px superior e inferior.
       - Filtro unsharp para nitidez 4K en caras y texturas.
    2. Subtítulos Karaoke Dinámicos Anti-Solapamiento:
       - Resaltado activo palabra por palabra en Amarillo Neón sin repetición ni pisado.
       - Sincronización temporal estrictamente secuencial y no solapada.
       - Centrados a y=1280 (zona segura sobre los botones de Shorts/TikTok/Reels).
    3. Normalización de audio YouTube Shorts (-14 LUFS).
    4. CERO retraso: El contenido arranca DIRECTAMENTE a 0.0s.
    5. Aceleración nativa VideoToolbox en Apple Silicon M4.
    """
    temp_dir = input_video.parent
    base_name = input_video.stem
    width, height = get_video_dimensions(input_video)
    is_already_vertical = (height > width)
    is_vertical = force_short_format or is_already_vertical

    fg_h = 1600
    fg_y = 160
    fg_bottom = fg_y + fg_h

    print(f"[*] Ensamblando vídeo con Karaoke Dinámico Anti-Solapamiento y Zoom 83.3% (Vertical: {is_vertical})...")

    # 1. Viñeta y sombras de unión
    vignette_png = temp_dir / f"{base_name}_vignette.png"
    create_subtle_vignette(vignette_png, fg_top=fg_y, fg_bottom=fg_bottom)

    # 2. Generación de estados de Karaoke palabra por palabra (sin solapamiento)
    cues = parse_srt_file(srt_subtitles) if srt_subtitles else []
    sub_cues = cues[:45]
    sub_pngs = []
    global_sub_idx = 0

    for cue in sub_cues:
        cleaned = clean_text_no_emoji(cue["text"]).upper()
        words = cleaned.split()
        if not words:
            continue

        timings = calculate_word_timing(words, cue["start"], cue["end"])
        for tw in timings:
            active_w_idx = tw["word_idx"]
            sub_png = temp_dir / f"{base_name}_ksub_{global_sub_idx}.png"
            rendered = render_karaoke_subtitle_state(
                words=words,
                active_idx=active_w_idx,
                is_vertical=is_vertical,
                output_path=sub_png
            )
            if rendered:
                sub_pngs.append((sub_png, tw["start"], tw["end"]))
                global_sub_idx += 1

    print(f"[*] {len(sub_pngs)} estados de Karaoke dinámico desduplicados generados.")

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

    # Subtítulos Karaoke como inputs
    sub_inputs_start = input_idx
    for sp, _, _ in sub_pngs:
        cmd.extend(["-i", str(sp)])
        input_idx += 1

    filter_chains = []

    # A) Base de vídeo: ZOOM & CROP MAXIMIZADO (83.3% del alto)
    if is_vertical and not is_already_vertical:
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

    # C) Superponer Subtítulos Karaoke palabra por palabra (estrictamente secuenciales a y=1280)
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
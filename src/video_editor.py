import os
import re
import json
import random
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .config import BASE_DIR, FFMPEG_VIDEO_CODEC, FFMPEG_BITRATE, FFMPEG_THREADS, SUBTITLE_OFFSET, is_quant_busy
from .emoji_renderer import (
    split_text_and_emojis,
    measure_composite_line,
    draw_composite_line,
    clean_text_preserve_emojis,
    render_emoji_image,
    get_best_emoji_font
)

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

def _probe_duration(media_path: Path) -> float:
    """Obtiene la duración exacta en segundos de un archivo multimedia usando ffprobe."""
    if not media_path or not media_path.exists():
        return 0.0
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(media_path)],
            capture_output=True, text=True, timeout=8
        )
        return float(res.stdout.strip()) if res.stdout.strip() else 0.0
    except Exception:
        return 0.0


def detect_horizontal_split_screen(video_path: Path, sample_time: float = 3.0) -> bool:
    """
    Detecta empíricamente si un vídeo horizontal (16:9) es una comparativa lado-a-lado 50/50
    (ej. 30 FPS vs 60 FPS, PS5 vs Xbox) analizando la discontinuidad vertical exacta en x = width // 2.
    """
    import statistics
    import tempfile
    w, h = get_video_dimensions(video_path)
    if h >= w or w < 320 or h < 200:
        return False

    tmp_frame = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tmp_frame = Path(tf.name)
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(sample_time), "-i", str(video_path), "-frames:v", "1", str(tmp_frame)],
            capture_output=True, timeout=8
        )
        if not tmp_frame.exists() or tmp_frame.stat().st_size < 1000:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "0.5", "-i", str(video_path), "-frames:v", "1", str(tmp_frame)],
                capture_output=True, timeout=8
            )
        if not tmp_frame.exists() or tmp_frame.stat().st_size < 1000:
            return False

        img = Image.open(tmp_frame).convert("RGB")
        iw, ih = img.size
        px = img.load()
        mid = iw // 2
        col_stats = []
        y_start, y_end = int(ih * 0.15), int(ih * 0.85)
        for x in range(max(1, mid - 40), min(iw - 1, mid + 40)):
            row_diffs = [
                abs(px[x, y][0] - px[x - 1, y][0])
                + abs(px[x, y][1] - px[x - 1, y][1])
                + abs(px[x, y][2] - px[x - 1, y][2])
                for y in range(y_start, y_end, 4)
            ]
            if row_diffs:
                edge_frac = sum(1 for d in row_diffs if d > 20) / len(row_diffs)
                col_stats.append((x, sum(row_diffs), edge_frac))

        if not col_stats:
            return False
        med = statistics.median(d for _, d, _ in col_stats)
        med_frac = statistics.median(f for _, _, f in col_stats)
        center_candidates = [(d, f) for x, d, f in col_stats if abs(x - mid) <= 3]
        if not center_candidates:
            return False
        center_peak, center_frac = max(center_candidates, key=lambda t: t[0])
        # Un split-screen 50/50 real genera discontinuidad continua a lo largo de >=45% de la altura
        return (
            center_frac >= 0.45
            and center_frac > med_frac * 2.0
            and center_peak > max(3500, med * 3.0)
        )
    except Exception:
        return False
    finally:
        if tmp_frame and tmp_frame.exists():
            try:
                tmp_frame.unlink()
            except OSError:
                pass

def get_viral_display_font(size: int = 68):
    """
    Tipografía display condensada de marca para titulares virales en Shorts/TikTok/Reels.
    Prioridad: Anton-Regular (assets/fonts) -> Montserrat-Black -> Impact -> Helvetica Condensed Black.
    """
    viral_configs = [
        (str(BASE_DIR / "assets" / "fonts" / "Anton-Regular.ttf"), 0),
        (str(BASE_DIR / "assets" / "fonts" / "Montserrat-Black.ttf"), 0),
        ("/System/Library/Fonts/Supplemental/Impact.ttf", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 9),
        ("/System/Library/Fonts/Supplemental/Arial Black.ttf", 0),
    ]
    for path, idx in viral_configs:
        if os.path.exists(path):
            try:
                if path.endswith(".ttc"):
                    return ImageFont.truetype(path, size, index=idx)
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return get_best_font(size)


def get_best_font(size: int = 58):
    """
    Obtiene la tipografía oficial de marca (Montserrat Black) o fallback macOS.
    """
    font_configs = [
        (str(BASE_DIR / "assets" / "fonts" / "Montserrat-Black.ttf"), 0),
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
    """
    Limpia texto de subtítulos garantizando legibilidad total:
    1. Reemplaza tags HTML/VTT (<c>, </c>, <font>, etc.) por espacio para evitar palabras fusionadas.
    2. Reemplaza entidades HTML (&nbsp;, etc.) por espacio.
    3. Separa palabras fusionadas por camelCase o mayúsculas adyacentes.
    4. Elimina emojis y símbolos raros que provocan cajas rotas '[]' en Pillow.
    5. Normaliza espacios múltiples.
    """
    if not text:
        return ""
    # 1. Tags HTML/VTT reemplazados por espacio (evita "filtrado<c>un" -> "filtradoun")
    text = re.sub(r'<[^>]+>', ' ', text)
    # 2. Entidades HTML
    text = re.sub(r'&[a-zA-Z0-9#]+;', ' ', text)
    # 3. Separar palabras pegadas (minúscula seguida de mayúscula: "filtradoUn" -> "filtrado Un")
    text = re.sub(r'([a-zñáéíóú])([A-ZÑÁÉÍÓÚ])', r'\1 \2', text)
    # 4. Limpieza de caracteres no deseados
    cleaned = re.sub(r'[^\w\s\d¡!¿?,\.:\'-áéíóúÁÉÍÓÚñÑüÜ]', '', text)
    return " ".join(cleaned.split()).strip()

def split_cue_into_micro_bursts(text: str, start: float, end: float, max_words: int = 3) -> List[Dict[str, Any]]:
    """
    Divide frases en micro-ráfagas de 2-3 palabras estilo Hormozi / MrBeast,
    garantizando SINCRONIZACIÓN PERFECTA (cero desfase temporal con la voz):
    La suma de duraciones de las ráfagas coincide proporcionalmente con el habla real [start, end].
    """
    words = text.split()
    if not words:
        return []

    actual_dur = max(0.4, end - start)
    # Acotar a duración razonable de locución si el caption se extiende artificialmente en pausas
    max_reasonable = max(0.9, len(words) * 0.58)
    effective_dur = min(actual_dur, max_reasonable)

    if len(words) <= max_words:
        return [{"start": round(start, 2), "end": round(start + effective_dur, 2), "text": text}]

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

    chunk_weights = [sum(len(w) for w in c) + len(c) for c in chunks]
    total_weight = sum(chunk_weights)

    res = []
    cur_t = start
    for idx, (c, wt) in enumerate(zip(chunks, chunk_weights)):
        if idx == len(chunks) - 1:
            next_t = start + effective_dur
        else:
            c_dur = effective_dur * (wt / total_weight)
            next_t = cur_t + c_dur
        res.append({
            "start": round(cur_t, 2),
            "end": round(next_t, 2),
            "text": " ".join(c)
        })
        cur_t = next_t

    return res

def calculate_word_timing(words: List[str], start_t: float, end_t: float) -> List[Dict[str, Any]]:
    """
    Calcula los intervalos de tiempo palabra por palabra ponderados fonéticamente.
    Garantiza continuidad fluida sin micro-parpadeos entre palabras contiguas.
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
            "end": round(next_t, 2)
        })
        cur_t = next_t
    return timings

def parse_srt_file(srt_path: Path, offset_seconds: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Parsea y desduplica subtítulos SRT eliminando el 'rolling buffer' de YouTube
    y calibrando al milisegundo el retardo de ASR captions:
    1. Aplica compensación temporal negativa (SUBTITLE_OFFSET) para sincronizar con fonemas.
    2. Filtra micro-bloques de transición (< 0.25s).
    3. Desduplica repeticiones rodantes de YouTube sin amputar palabras válidas.
    4. Asegura estricta monotonicidad temporal (cero solapamientos entre frases).
    5. Devuelve micro-ráfagas limpias de 2-3 palabras perfectamente sincronizadas.
    """
    if not srt_path.exists():
        return []

    effective_offset = SUBTITLE_OFFSET if offset_seconds is None else offset_seconds

    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().replace("\r\n", "\n")

    try:
        from .downloader import deroll_and_clean_srt_content
        content = deroll_and_clean_srt_content(content)
    except Exception:
        pass

    blocks = content.strip().split("\n\n")
    raw_cues = []
    last_text = ""

    for b in blocks:
        lines = [line.strip() for line in b.split("\n") if line.strip()]
        if len(lines) >= 3 and "-->" in lines[1]:
            start_str, end_str = lines[1].split("-->")
            raw_start = parse_time(start_str)
            raw_end = parse_time(end_str)

            # Descartar micro-glitches de 10-100ms
            if (raw_end - raw_start) < 0.25:
                continue

            # Calibración milimétrica: compensar retraso de YouTube ASR captions
            start_sec = max(0.0, raw_start + effective_offset)
            end_sec = max(start_sec + 0.35, raw_end + effective_offset)

            text_lines = [clean_text_no_emoji(l) for l in lines[2:] if clean_text_no_emoji(l)]
            if not text_lines:
                continue

            # Desduplicar el buffer rodante de YouTube de forma segura
            last_clean = last_text.strip().lower()
            new_lines = []
            for tl in text_lines:
                tl_clean = tl.strip().lower()
                if tl_clean and tl_clean != last_clean:
                    new_lines.append(tl)

            if not new_lines:
                full_t = " ".join(text_lines).strip()
                if full_t.lower().startswith(last_clean) and len(full_t) > len(last_clean):
                    added = full_t[len(last_clean):].strip()
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

    # Asegurar orden estrictamente secuencial y sincronización fija al habla real
    all_bursts = []
    for c in raw_cues:
        c_start = c["start"]
        c_end = c["end"]
        if c_end <= c_start:
            continue

        # Evitar solapamientos con la ráfaga anterior
        if all_bursts and all_bursts[-1]["end"] > c_start:
            prev_start = all_bursts[-1]["start"]
            if c_start > prev_start + 0.2:
                all_bursts[-1]["end"] = round(c_start - 0.02, 2)
            else:
                c_start = round(all_bursts[-1]["end"] + 0.02, 2)
                if c_end <= c_start:
                    continue

        bursts = split_cue_into_micro_bursts(c["text"], c_start, c_end, max_words=3)
        for b in bursts:
            if b["end"] > b["start"]:
                all_bursts.append(b)

    return all_bursts

def get_emoji_font(size: int = 40):
    """Carga la tipografía nativa de emojis a color de Apple en macOS de forma segura sin invalid pixel size."""
    font, _ = get_best_emoji_font(size)
    return font

EMOJI_KEYWORDS = {
    # Personajes & Lore de GTA 6
    "lucia": "💃",
    "jason": "🧢",
    "caiman": "🐊",
    "caimán": "🐊",
    "cocodrilo": "🐊",
    "mud": "🚜",
    "joker": "🃏",
    # Geografía & Leonida
    "mapa": "🗺️",
    "map": "🗺️",
    "leonida": "🗺️",
    "vice": "🌴",
    "miami": "🌴",
    "playa": "🏖️",
    "beach": "🏖️",
    # Filtraciones & Alertas
    "filtracion": "🚨",
    "filtración": "🚨",
    "filtrado": "🚨",
    "leak": "🚨",
    "leaks": "🚨",
    "secreto": "🔍",
    "secretos": "🔍",
    "secret": "🔍",
    "easter": "🥚",
    "misterio": "👀",
    # Reacciones & Virabilidad
    "loco": "🤯",
    "flipar": "🤯",
    "flipas": "🤯",
    "broma": "😂",
    "risa": "😂",
    "bomba": "💥",
    "bombazo": "💥",
    "impacto": "💥",
    # Jugabilidad & Acción
    "dinero": "💰",
    "millones": "💰",
    "atraco": "💰",
    "coche": "🏎️",
    "coches": "🏎️",
    "motor": "🏎️",
    "policia": "🚓",
    "policía": "🚓",
    "fuego": "🔥",
    "brutal": "🔥",
    "arma": "🔫",
    "armas": "🔫",
    "tiroteo": "🔫",
    "rockstar": "⭐",
    "trailer": "🎬",
    "tráiler": "🎬",
    "juego": "🎮",
    "gameplay": "🎮",
    "graficos": "✨",
    "gráficos": "✨",
    "fisicas": "🌊",
    "físicas": "🌊",
    "agua": "🌊"
}

HOT_PINK_KEYWORDS = {
    "loco", "flipas", "filtracion", "filtración", "leak", "leaks", "broma",
    "increible", "increíble", "bomba", "bombazo", "lucia", "jason", "vice",
    "leonida", "trailer", "tráiler", "rage", "gellhorn", "brutal", "secreto",
    "alucinante", "exclusiva", "confirmado"
}

def render_top_hook_headline(hook_text: str, output_path: Path) -> bool:
    """Renderiza una potente y espectacular tarjeta de gancho superior estilo Broadcast Viral (0.0 a 2.5s) con soporte composite de emojis."""
    raw_lines = [l.strip() for l in (hook_text or "").splitlines() if l.strip()]
    cleaned_explicit = []
    for rl in raw_lines:
        c = clean_text_preserve_emojis(rl).upper().replace("¿", "").replace("?", "").strip()
        c = " ".join(c.split())
        if c:
            cleaned_explicit.append(c)

    if not cleaned_explicit:
        return False

    if len(cleaned_explicit) >= 2:
        line1 = cleaned_explicit[0]
        line2 = " ".join(cleaned_explicit[1:])
    else:
        clean_hook = cleaned_explicit[0]
        # Mantener unidos términos compuestos (GTA 6, GTA VI, RAGE 9) al dividir en dos líneas
        protected = re.sub(r"\b(GTA|RAGE)\s+(6|VI|9|V|5)\b", r"\1_\2", clean_hook)
        words = [w.replace("_", " ") for w in protected.split()]
        if len(words) >= 4:
            mid = (len(words) + 1) // 2
            line1 = " ".join(words[:mid])
            line2 = " ".join(words[mid:])
        elif len(words) == 3:
            line1 = words[0]
            line2 = " ".join(words[1:])
        else:
            line1 = ""
            line2 = clean_hook

    tokens1 = split_text_and_emojis(line1) if line1 else []
    tokens2 = split_text_and_emojis(line2)

    pad_x = 32
    pad_y = 8
    spacing = 8 if line1 else 0
    size1 = 56
    size2 = 72

    while True:
        font1 = get_viral_display_font(size=size1)
        font2 = get_viral_display_font(size=size2)
        w1, h1 = measure_composite_line(tokens1, font1, emoji_size=size1) if line1 else (0, 0)
        w2, h2 = measure_composite_line(tokens2, font2, emoji_size=max(36, size2 - 4))
        content_w = max(w1, w2)
        box_w = int(content_w + pad_x * 2)
        if box_w <= 980 or (size1 <= 36 and size2 <= 44):
            break
        size1 = max(36, size1 - 2)
        size2 = max(44, size2 - 3)

    box_h = int(h1 + h2 + spacing + pad_y * 2 + 12)

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Tipografía pura de alto impacto (sin caja de botón ni bordes artificiales)
    cur_y = pad_y
    if line1:
        x1 = pad_x + (content_w - w1) / 2
        draw_composite_line(img, d, tokens1, int(x1 + 4), int(cur_y + 4), font1, fill_color=(0, 0, 0, 235), stroke_width=0, emoji_size=size1)
        draw_composite_line(img, d, tokens1, int(x1), int(cur_y), font1, fill_color=(255, 255, 255, 255), stroke_color=(0, 0, 0, 255), stroke_width=5, emoji_size=size1)
        cur_y += h1 + spacing

    em2 = max(36, size2 - 4)
    x2 = pad_x + (content_w - w2) / 2
    draw_composite_line(img, d, tokens2, int(x2 + 4), int(cur_y + 4), font2, fill_color=(0, 0, 0, 235), stroke_width=0, emoji_size=em2)
    draw_composite_line(img, d, tokens2, int(x2), int(cur_y), font2, fill_color=(255, 210, 63, 255), stroke_color=(0, 0, 0, 255), stroke_width=5, emoji_size=em2)

    img.save(output_path, "PNG")
    return True

def render_retention_hook(output_path: Path, text: str = "ESPERA A VER ESTO") -> bool:
    """
    Renderiza una micro-tarjeta de retención (segundo gancho) para mostrar entre 5.0-7.0s.
    Más pequeña y sutil que el hook principal, diseñada para frenar el swipe a mitad de Short.
    """
    clean = clean_text_preserve_emojis(text).upper()
    if not clean:
        return False

    font = get_best_font(size=38)
    tokens = split_text_and_emojis(clean)
    tw, th = measure_composite_line(tokens, font, emoji_size=38)

    pad_x, pad_y = 36, 14
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle(
        [(0, 0), (box_w - 1, box_h - 1)],
        radius=18,
        fill=(8, 8, 14, 200),
        outline=(0, 240, 255, 180),
        width=2
    )
    draw_composite_line(img, d, tokens, pad_x, pad_y, font, fill_color=(0, 240, 255, 255), stroke_color=(0, 0, 0, 255), stroke_width=2, emoji_size=38)

    img.save(output_path, "PNG")
    return True


def render_persistent_context_badge(output_path: Path, text: str = "GTA 6 • VICE CITY", archetype: str = "") -> bool:
    """
    Titular contextual viral de alto impacto (sin caja de botón):
    - Tipografía display condensada (Impact / Helvetica Condensed Black).
    - Auto-escalado dinámico para llenar ~940px del ancho 1080px en 1 o 2 líneas balanceadas.
    - Color de acento dinámico según el arquetipo del clip + trazo grueso y sombra profunda.
    """
    clean = clean_text_preserve_emojis(text).replace("•", " ").strip().upper()[:38]
    clean = " ".join(clean.split())
    if not clean:
        clean = "GTA 6 VICE CITY"

    accent_palette = {
        "gameplay_puro": (0, 240, 255),
        "reaccion_streamer": (255, 75, 165),
        "analisis_tecnico": (255, 215, 75),
        "filtracion_misterio": (195, 130, 255),
        "noticia_oficial": (255, 95, 95),
        "humor_parodia": (90, 255, 150),
    }
    accent = accent_palette.get((archetype or "").strip().lower(), (0, 240, 255))

    # Dividir en 2 líneas balanceadas si supera 18 caracteres para maximizar tamaño visual
    words = clean.split()
    if len(clean) > 18 and len(words) >= 3:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
        max_font, min_font, max_h = 62, 42, 130
    else:
        lines = [clean]
        max_font, min_font, max_h = 78, 46, 110

    max_w = 960
    font_size = max_font
    while True:
        font = get_viral_display_font(size=font_size)
        measured = []
        for ln in lines:
            tks = split_text_and_emojis(ln)
            lw, lh = measure_composite_line(tks, font, emoji_size=font_size)
            measured.append((tks, lw, lh))
        total_w = max(m[1] for m in measured)
        line_gap = 6 if len(lines) > 1 else 0
        total_h = sum(m[2] for m in measured) + line_gap * max(0, len(lines) - 1)
        if (total_w <= max_w and total_h <= max_h) or font_size <= min_font:
            break
        font_size -= 2

    canvas_w = max(total_w + 48, 320)
    underline_h = 5
    canvas_h = total_h + 24 + underline_h

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cur_y = 6
    for idx, (tks, lw, lh) in enumerate(measured):
        x = int((canvas_w - lw) / 2)
        color = (255, 255, 255, 255) if (len(lines) == 1 or idx == 0) else (accent[0], accent[1], accent[2], 255)
        draw_composite_line(img, d, tks, x + 4, cur_y + 4, font, fill_color=(0, 0, 0, 235), stroke_width=0, emoji_size=font_size)
        draw_composite_line(img, d, tks, x, cur_y, font, fill_color=color, stroke_color=(0, 0, 0, 255), stroke_width=4, emoji_size=font_size)
        cur_y += lh + (6 if len(lines) > 1 else 0)

    # Barra de acento neón sutil centrada bajo el titular
    bar_w = min(int(total_w * 0.55), 420)
    bar_x = int((canvas_w - bar_w) / 2)
    bar_y = cur_y + 8
    d.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + underline_h)], radius=3, fill=(accent[0], accent[1], accent[2], 235))

    img.save(output_path, "PNG")
    return True


def render_karaoke_subtitle_state(words: List[str], active_idx: int, is_vertical: bool, output_path: Path) -> bool:
    """
    Renderiza subtítulos Pop Broadcast limpios y transparentes (estilo Shorts/TikTok viral):
    - Sin caja/píldora oscura detrás (no tapa la acción del gameplay).
    - Tipografía Heavy grande (font_size=70, pop=78) con trazo negro grueso y sombra paralela.
    - La frase permanece 100% fija horizontalmente (cero jitter).
    - Palabra activa destacada en Amarillo Neón / Verde Flúor / Rosa Neón con glow sutil.
    """
    if not words:
        return False

    # Limpiar puntuación residual colgante (puntos, comas) para estética moderna de subtítulos
    display_words = [re.sub(r'[.,;:]+$', '', w).strip() for w in words]
    display_words = [w for w in display_words if w]
    if not display_words:
        return False

    max_w = 920 if is_vertical else 1040
    font_size = 70 if is_vertical else 50
    font = get_best_font(size=font_size)

    temp_img = Image.new("RGBA", (1, 1))
    d_temp = ImageDraw.Draw(temp_img)

    space_w = 24

    # Ajustar tamaño de fuente dinámicamente si supera el ancho máximo seguro
    while font_size > 40:
        test_w = sum(d_temp.textbbox((0, 0), w, font=font)[2] - d_temp.textbbox((0, 0), w, font=font)[0] for w in display_words)
        test_w += space_w * (len(display_words) - 1)
        if test_w <= max_w:
            break
        font_size -= 4
        font = get_best_font(size=font_size)

    pop_font = get_best_font(size=font_size + 8)
    from .emoji_renderer import is_color_emoji_supported
    has_emoji_support = is_vertical and is_color_emoji_supported()

    # Asignar casilla fija a cada palabra con el ancho máximo (normal o pop) para cero jitter
    cell_widths = []
    for w in display_words:
        bb_normal = d_temp.textbbox((0, 0), w, font=font)
        w_norm = bb_normal[2] - bb_normal[0]
        bb_pop = d_temp.textbbox((0, 0), w, font=pop_font)
        w_pop = bb_pop[2] - bb_pop[0]
        cell_widths.append(max(w_norm, w_pop) + 8)

    total_w = sum(cell_widths) + space_w * (len(display_words) - 1)
    sample_bb = pop_font.getbbox("AYÁÉÍÓÚÑjg")
    text_h = sample_bb[3]

    # Altura adicional para emoji si aplica
    emoji_room = 46 if has_emoji_support else 0

    pad_x = 34
    pad_y = 18
    box_w = int(total_w + pad_x * 2)
    box_h = int(text_h + pad_y * 2 + emoji_room + 18)

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pill_top = emoji_room

    # Detectar palabra activa y sus propiedades
    raw_active_word = display_words[active_idx] if 0 <= active_idx < len(display_words) else ""
    clean_active = re.sub(r'[^a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]', '', raw_active_word).lower()
    active_emoji = EMOJI_KEYWORDS.get(clean_active) if has_emoji_support else None
    is_hot_pink = clean_active in HOT_PINK_KEYWORDS
    is_green_pop = clean_active in {"gta", "gta6", "6", "vi", "leonida", "vice", "dinero", "gratis", "reservaste", "precarga"}

    if is_hot_pink:
        active_color = (255, 59, 154, 255)   # Rosa Vice City
        glow_color = (255, 59, 154, 110)
    else:
        active_color = (255, 210, 63, 255)   # Oro Rockstar unificado (sin verde chillón)
        glow_color = (255, 210, 63, 100)

    base_y = pill_top + pad_y

    # 1. Resplandor sutil (glow) detrás de la palabra activa
    glow = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d_glow = ImageDraw.Draw(glow)
    cur_x = pad_x
    for idx, w in enumerate(display_words):
        cw = cell_widths[idx]
        if idx == active_idx:
            bb_pop = d_temp.textbbox((0, 0), w, font=pop_font)
            ww_pop = bb_pop[2] - bb_pop[0]
            draw_x = cur_x + (cw - ww_pop) / 2
            d_glow.text((draw_x, base_y - 2), w, font=pop_font, fill=glow_color, stroke_width=10, stroke_fill=glow_color)
        cur_x += cw + space_w

    glow = glow.filter(ImageFilter.GaussianBlur(5))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    # 2. Dibujar texto con borde negro grueso de alto contraste y sombra paralela limpia (0 cajas)
    cur_x = pad_x
    for idx, w in enumerate(display_words):
        cw = cell_widths[idx]
        is_active = (idx == active_idx)
        current_font = pop_font if is_active else font
        text_color = active_color if is_active else (255, 255, 255, 255)
        stroke_w = 8 if is_active else 6

        bb_w = d_temp.textbbox((0, 0), w, font=current_font)
        ww_act = bb_w[2] - bb_w[0]
        draw_x = cur_x + (cw - ww_act) / 2
        draw_y = base_y - (3 if is_active else 0)

        # Sombra paralela intensa para legibilidad absoluta sobre cielo/carretera/luces
        d.text((draw_x + 3, draw_y + 5), w, font=current_font, fill=(0, 0, 0, 235), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 210))
        # Trazo negro nítido + Relleno vibrante
        d.text((draw_x, draw_y), w, font=current_font, fill=text_color, stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))

        # Emoji contextual flotante encima si aplica
        if is_active and active_emoji:
            emo_img = render_emoji_image(active_emoji, target_size=42)
            if emo_img:
                emoji_x = int(cur_x + (cw - emo_img.width) / 2)
                emoji_y = max(2, pill_top - emo_img.height - 2)
                img.alpha_composite(emo_img, (emoji_x, emoji_y))

        cur_x += cw + space_w

    img.save(output_path, "PNG")
    return True

def create_subtle_vignette(output_png: Path, fg_top: int = 160, fg_bottom: int = 1760, is_cinema: bool = False) -> bool:
    """
    Genera gradientes cinemáticos con sombras de unión de tarjeta:
    - Viñetas en extremos superior e inferior.
    - En modo cinema: sombras suaves y sutil borde OLED en fg_top y fg_bottom.
    """
    w, h = 1080, 1920
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if is_cinema:
        # Cabecera editorial oscura limpia (elimina el aspecto lavado de franja superior)
        top_limit = max(1, fg_top)
        for y in range(top_limit):
            alpha = int(235 - 55 * (y / top_limit))
            d.line([(0, y), (w, y)], fill=(7, 9, 15, alpha))

        # Sombra suave hacia el vídeo para transición orgánica
        for i in range(32):
            alpha = int(150 * (1 - (i / 32)))
            if fg_top + i < h:
                d.line([(0, fg_top + i), (w, fg_top + i)], fill=(7, 9, 15, alpha))

        if fg_bottom < h - 5:
            for i in range(25):
                alpha = int(130 * (1 - (i / 25)))
                if fg_bottom + i < h:
                    d.line([(0, fg_bottom + i), (w, fg_bottom + i)], fill=(0, 0, 0, alpha))
            bot_start = max(fg_bottom, 1740)
            bot_range = max(1, h - bot_start)
            for y in range(bot_range):
                alpha = int(120 * (y / bot_range))
                d.line([(0, bot_start + y), (w, bot_start + y)], fill=(0, 0, 0, alpha))
        else:
            # Degradado inferior sutil para legibilidad de UI sin cortar imagen
            for y in range(220):
                alpha = int(135 * (y / 220))
                d.line([(0, h - 220 + y), (w, h - 220 + y)], fill=(0, 0, 0, alpha))
    else:
        for y in range(160):
            alpha = int(90 * (1 - (y / 160)))
            d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
        for y in range(180):
            alpha = int(110 * (y / 180))
            d.line([(0, 1920 - 180 + y), (w, 1920 - 180 + y)], fill=(0, 0, 0, alpha))

    # Micro-watermark editorial de marca sutil en esquina superior derecha
    try:
        wm_font = get_best_font(size=22)
        d.text((w - 225, 16), "@GTAVIHUBEXTRA", font=wm_font, fill=(255, 255, 255, 95))
    except Exception:
        pass

    img.save(output_png, "PNG")
    return True

def render_final_video(
    input_video: Path,
    output_video: Path,
    srt_subtitles: Optional[Path] = None,
    dub_audio: Optional[Path] = None,
    force_short_format: bool = False,
    hook_text: str = "",
    is_official_content: bool = False,
    archetype: str = "",
    format_preset: Optional[str] = None,
    context_badge: str = ""
) -> bool:
    """
    Ensamblaje viral definitivo con KARAOKE GLOW, GANCHO SUPERIOR (0-2.5s) y ENCUADRE INTELIGENTE:
    1. Formato D (Pro-Cinema 83.3% / 1080x1600):
       - Máxima inmersión visual para físicas RAGE 9, gameplay puro, tiroteos y choques.
    2. Formato C (Smart Frame 4:5 / 1080x1350):
       - Encuadre editorial balanceado para comparativas, noticias oficiales y lore.
    3. Formato Vertical Nativo 9:16:
       - Si el vídeo ya es vertical nativo, se escala a pantalla completa (1080x1920).
    4. Gancho Superior de Contexto (0.0s a 2.5s) y Subtítulos Karaoke Dinámicos con Halo Neón.
    5. Normalización de audio YouTube Shorts (-14 LUFS).
    6. Aceleración nativa VideoToolbox en Apple Silicon e Intel.
    """
    temp_dir = input_video.parent
    base_name = input_video.stem
    width, height = get_video_dimensions(input_video)
    is_already_vertical = (height > width)
    is_vertical = force_short_format or is_already_vertical

    # Determinar preset: SPLIT (comparativa 50/50 apilada), D (Pro-Cinema 83.3%), C (4:5 70.3%) o FIT
    effective_preset = (format_preset or "").upper()
    if is_vertical and not is_already_vertical and effective_preset in ("", "AUTO", "FIT"):
        # Detectar automáticamente comparativas reales 50/50 lado-a-lado para apilarlas a pantalla completa
        if detect_horizontal_split_screen(input_video):
            effective_preset = "SPLIT"

    if not effective_preset or effective_preset == "AUTO":
        effective_preset = "FIT"

    if is_vertical and not is_already_vertical:
        if effective_preset == "SPLIT":
            # Formato SPLIT: Comparativa 50/50 lado-a-lado convertida a dos paneles 1080x900 apilados (93.8% cobertura)
            fg_w = 1080
            fg_h = 1808
            fg_y = 48
            fg_bottom = 1856
            is_cinema_layout = True
            hook_y_expr = "740"
            ret_y_expr = "740"
            sub_y = "1520"
            print("[*] Modo Formato SPLIT Apilado 50/50 (93.8% cobertura): 2x 1080x900 @ y=48 / y=956.")
        elif effective_preset == "FIT":
            # Formato FIT (16:9 completo sin recorte lateral, reservado a casos extremos)
            fg_w = 1080
            fg_h = 608
            fg_y = 610
            fg_bottom = 1218
            is_cinema_layout = True
            hook_y_expr = "340"
            ret_y_expr = "400"
            sub_y = "1260"
            print(f"[*] Modo Formato FIT 16:9 Completo (sin recorte lateral): {fg_w}x{fg_h} @ y={fg_y} con Velvet Canvas.")
        elif effective_preset == "D":
            # Formato D Alpha (89.1% cobertura Edge-to-Bottom):
            # 1080x1710 anclado abajo (y=210..1920) sin franja borrosa inferior, cabecera editorial limpia arriba.
            fg_w = 1080
            fg_h = 1710
            fg_y = 210
            fg_bottom = 1920
            is_cinema_layout = True
            hook_y_expr = "28"
            ret_y_expr = "28"
            sub_y = "1280"
            print(f"[*] Modo Formato D Pro-Cinema (89.1% cobertura Edge-to-Bottom): {fg_w}x{fg_h} @ y={fg_y}.")
        else:
            # Formato C (Smart Frame Inmersivo 4:5, 70.3% de cobertura):
            # 1080x1350 centrado a y=285 con Ambient Canvas (2.2x más área visual que FIT).
            fg_w = 1080
            fg_h = 1350
            fg_y = 285
            fg_bottom = 1635
            is_cinema_layout = True
            # Safe Zone Shorts & TikTok: hook a y=100, subtítulos a y=1240
            hook_y_expr = "100"
            ret_y_expr = "160"
            sub_y = "1240"
            print(f"[*] Modo Formato C Smart Frame 4:5 (70.3% cobertura): {fg_w}x{fg_h} @ y={fg_y} con Ambient Canvas.")
    else:
        # Formato Vertical Nativo 9:16 (1080x1920)
        fg_w = 1080
        fg_h = 1920
        fg_y = 0
        fg_bottom = 1920
        is_cinema_layout = False
        hook_y_expr = "110"
        ret_y_expr = "210"
        sub_y = "1240" if is_vertical else "H-h-90"
        print(f"[*] Modo Vertical Nativo 9:16: Pantalla completa sin deformación (Vertical: {is_vertical}).")

    # 1. Viñeta y sombras de unión
    vignette_png = temp_dir / f"{base_name}_vignette.png"
    create_subtle_vignette(vignette_png, fg_top=fg_y, fg_bottom=fg_bottom, is_cinema=is_cinema_layout)

    # 2. Gancho textual superior (0 a 2.8s) y Badge persistente editorial (>= 2.8s)
    # En vídeo vertical nativo (is_already_vertical) o SPLIT (toca arriba), mantener limpio arriba.
    hook_png = None
    badge_png = None
    if hook_text and is_vertical and not is_already_vertical:
        hook_png = temp_dir / f"{base_name}_hook.png"
        rendered_hook = render_top_hook_headline(hook_text, hook_png)
        if not rendered_hook:
            hook_png = None

        if effective_preset != "SPLIT":
            hook_lines = [ln.strip() for ln in hook_text.splitlines() if ln.strip()]
            badge_label = (context_badge or "").strip()
            if not badge_label:
                # Si no hay context_badge explícito, preferir la 2ª línea (más específica) si existe
                badge_label = hook_lines[1] if len(hook_lines) >= 2 else (hook_lines[0] if hook_lines else "GTA 6 • VICE CITY")
            badge_png = temp_dir / f"{base_name}_badge.png"
            if not render_persistent_context_badge(badge_png, text=badge_label, archetype=archetype):
                badge_png = None

    # 2b. Micro-tarjeta genérica de los 5.0s desactivada por defecto en estándar Alpha (evita parpadeos y frases cliché)
    retention_png = None

    # 3. Generación de estados de Karaoke palabra por palabra
    # En audio doblado neural, la sincronía fonética es directa (offset=0.0s).
    # En audio original en inglés con YouTube ASR, se mantiene SUBTITLE_OFFSET (-0.45s).
    effective_sub_offset = 0.0 if (dub_audio and dub_audio.exists()) else None
    cues = parse_srt_file(srt_subtitles, offset_seconds=effective_sub_offset) if srt_subtitles else []
    sub_cues = cues[:250]
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

    print(f"[*] {len(sub_pngs)} estados de Karaoke dinámico con glow generados.")

    # 4. Medir duraciones para evitar cortes de audio/voz al final
    v_dur = _probe_duration(input_video)
    dub_dur = _probe_duration(dub_audio) if (dub_audio and dub_audio.exists()) else 0.0
    pad_sec = 0.0
    if dub_dur > v_dur + 0.15:
        pad_sec = round(dub_dur - v_dur + 0.45, 2)
        print(f"[*] Locución doblada ({dub_dur:.1f}s) supera metraje ({v_dur:.1f}s). Extendiendo vídeo con tpad={pad_sec:.1f}s para evitar corte abrupto.")
    total_dur = round(v_dur + pad_sec, 2) if pad_sec > 0.0 else None

    # Construcción del comando FFmpeg
    cmd = ["ffmpeg", "-y", "-i", str(input_video)]
    input_idx = 1

    # Audio doblado con Ducking Dinámico Inteligente
    dub_idx = None
    if dub_audio and dub_audio.exists():
        cmd.extend(["-i", str(dub_audio)])
        dub_idx = input_idx
        input_idx += 1

    # Banda Sonora Ambiental: Solo activa si está explícitamente configurada en .env (para no ensuciar el sonido in-game)
    ambient_idx = None
    ambient_dir = BASE_DIR / "assets" / "audio" / "ambient_beats"
    enable_ambient = os.getenv("ENABLE_AMBIENT_BEATS", "false").lower() in ("true", "1")
    if enable_ambient and ambient_dir.exists():
        ambient_tracks = [p for p in ambient_dir.glob("*.mp3") if p.is_file()] + [p for p in ambient_dir.glob("*.wav") if p.is_file()]
        if ambient_tracks:
            chosen_ambient = random.choice(ambient_tracks)
            cmd.extend(["-stream_loop", "-1", "-i", str(chosen_ambient)])
            ambient_idx = input_idx
            input_idx += 1
            print(f"[*] Mezclando pista ambiental sutil: {chosen_ambient.name} (-22 dB)")

    # Micro-SFX de impacto inicial en t=0.0s para frenar el scroll sin cargar CPU
    sfx_idx = None
    sfx_file = BASE_DIR / "assets" / "audio" / "sfx" / "hook_impact.wav"
    if hook_png and is_vertical and sfx_file.exists():
        cmd.extend(["-i", str(sfx_file)])
        sfx_idx = input_idx
        input_idx += 1

    # Construcción de la cadena de mezcla de audio (Voice-Over: original atenuado al 6% + Doblaje ES dominante + Ambiente)
    if dub_idx is not None:
        if pad_sec > 0.0:
            fade_start = max(0.0, total_dur - 0.35)
            if ambient_idx is not None:
                audio_filter = (
                    f"[{ambient_idx}:a]volume=0.06[amb];"
                    f"[0:a]volume=0.06[orig_base];"
                    f"[{dub_idx}:a]asplit=2[sc][voice];"
                    f"[orig_base][sc]sidechaincompress=threshold=0.015:ratio=12:attack=10:release=250[orig_ducked];"
                    f"[orig_ducked][amb]amix=inputs=2:duration=longest:normalize=false[bed];"
                    f"[bed][voice]amix=inputs=2:duration=longest:normalize=false,afade=t=out:st={fade_start:.2f}:d=0.35[a_mix]"
                )
            else:
                audio_filter = (
                    f"[0:a]volume=0.06[orig_base];"
                    f"[{dub_idx}:a]asplit=2[sc][voice];"
                    f"[orig_base][sc]sidechaincompress=threshold=0.015:ratio=12:attack=10:release=250[orig_ducked];"
                    f"[orig_ducked][voice]amix=inputs=2:duration=longest:normalize=false,afade=t=out:st={fade_start:.2f}:d=0.35[a_mix]"
                )
        else:
            if ambient_idx is not None:
                audio_filter = (
                    f"[{ambient_idx}:a]volume=0.06[amb];"
                    f"[0:a]volume=0.06[orig_base];"
                    f"[{dub_idx}:a]asplit=2[sc][voice];"
                    f"[orig_base][sc]sidechaincompress=threshold=0.015:ratio=12:attack=10:release=250[orig_ducked];"
                    f"[orig_ducked][amb]amix=inputs=2:duration=first:normalize=false[bed];"
                    f"[bed][voice]amix=inputs=2:duration=first:normalize=false[a_mix]"
                )
            else:
                audio_filter = (
                    f"[0:a]volume=0.06[orig_base];"
                    f"[{dub_idx}:a]asplit=2[sc][voice];"
                    f"[orig_base][sc]sidechaincompress=threshold=0.015:ratio=12:attack=10:release=250[orig_ducked];"
                    f"[orig_ducked][voice]amix=inputs=2:duration=first:normalize=false[a_mix]"
                )
    else:
        # Modo Subtítulos Estándar / Gameplay: Audio original limpio + ambient beat sutil si activo
        if ambient_idx is not None:
            audio_filter = (
                f"[{ambient_idx}:a]volume=0.08[amb];"
                f"[0:a]highpass=f=60,lowpass=f=15500[a_eq];"
                f"[a_eq][amb]amix=inputs=2:duration=first:normalize=false[a_mix]"
            )
        else:
            audio_filter = "[0:a]highpass=f=60,lowpass=f=15500[a_mix]"

    if sfx_idx is not None:
        audio_filter += (
            f";[{sfx_idx}:a]volume=0.16[sfx_hook];"
            f"[a_mix][sfx_hook]amix=inputs=2:duration=first:normalize=false,loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
        )
    else:
        audio_filter += ";[a_mix]loudnorm=I=-14:LRA=7:TP=-1.5[aout]"

    # Viñeta discreta
    cmd.extend(["-i", str(vignette_png)])
    vignette_idx = input_idx
    input_idx += 1

    # Gancho superior si existe
    hook_idx = None
    if hook_png and hook_png.exists():
        cmd.extend(["-i", str(hook_png)])
        hook_idx = input_idx
        input_idx += 1

    # Badge contextual persistente si existe
    badge_idx = None
    if badge_png and badge_png.exists():
        cmd.extend(["-i", str(badge_png)])
        badge_idx = input_idx
        input_idx += 1

    # Segundo gancho de retención si existe
    retention_idx = None
    if retention_png and retention_png.exists():
        cmd.extend(["-i", str(retention_png)])
        retention_idx = input_idx
        input_idx += 1

    # Subtítulos Karaoke como inputs
    sub_inputs_start = input_idx
    for sp, _, _ in sub_pngs:
        cmd.extend(["-i", str(sp)])
        input_idx += 1

    filter_chains = []

    # A) Base de vídeo:
    if is_vertical and not is_already_vertical:
        if effective_preset == "SPLIT":
            # Comparativa lado-a-lado 50/50 convertida en 2 paneles 1080x900 apilados (preserva etiquetas superiores)
            v_base = (
                "[0:v]split=3[v1][vl_in][vr_in];"
                "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:5,eq=brightness=-0.28:contrast=1.06:saturation=1.12[bg];"
                "[vl_in]crop=iw/2:ih:0:0,scale=1080:900:force_original_aspect_ratio=increase,crop=1080:900:(iw-1080)/2:0,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.10[vtop];"
                "[vr_in]crop=iw/2:ih:iw/2:0,scale=1080:900:force_original_aspect_ratio=increase,crop=1080:900:(iw-1080)/2:0,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.10[vbot];"
                "[bg][vtop]overlay=0:48[v_split_top];"
                "[v_split_top][vbot]overlay=0:956[v_framed]"
            )
        elif effective_preset == "FIT":
            # Formato FIT: 16:9 completo sin recorte lateral sobre Velvet Blur reactivo
            v_base = (
                "[0:v]split[v1][v2];"
                "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:5,eq=brightness=-0.14:contrast=1.06:saturation=1.18[bg];"
                f"[v2]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease,pad={fg_w}:{fg_h}:(ow-iw)/2:(oh-ih)/2:color=black,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
                f"[bg][fg]overlay=0:{fg_y}[v_framed]"
            )
        else:
            # Formato D / C: Plano recortado inmersivo sobre fondo Velvet Blur
            v_base = (
                "[0:v]split[v1][v2];"
                "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:5,eq=brightness=-0.14:contrast=1.06:saturation=1.18[bg];"
                f"[v2]scale={fg_w}:{fg_h}:force_original_aspect_ratio=increase,crop={fg_w}:{fg_h},unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
                f"[bg][fg]overlay=0:{fg_y}[v_framed]"
            )
    elif is_vertical:
        # Formato C (Nativo Vertical 9:16): Pantalla completa sin bandas
        v_base = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[v_framed]"
    else:
        v_base = "[0:v]unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[v_framed]"
    
    filter_chains.append(v_base)
    filter_chains.append("[v_framed]setsar=1[v_sar]")
    current_v = "v_sar"

    # B) Superponer Viñeta sutil y sombras de unión
    filter_chains.append(f"[{current_v}][{vignette_idx}:v]overlay=0:0[v_vignetted]")
    current_v = "v_vignetted"

    # C) Superponer Gancho Superior (0.0 a 2.8s)
    if hook_idx is not None:
        filter_chains.append(f"[{current_v}][{hook_idx}:v]overlay=(W-w)/2:{hook_y_expr}:enable='between(t,0,2.8)'[v_hooked]")
        current_v = "v_hooked"

    # C1) Superponer Titular contextual viral (>= 2.8s, pausado brevemente en 5.0-7.2s si hay retención)
    if badge_idx is not None:
        badge_enable = "gte(t,2.8)*lt(t,5.0)+gte(t,7.2)" if retention_idx is not None else "gte(t,2.8)"
        filter_chains.append(f"[{current_v}][{badge_idx}:v]overlay=(W-w)/2:28:enable='{badge_enable}'[v_badged]")
        current_v = "v_badged"

    # C2) Superponer segundo gancho de retención (5.0 a 7.2s) — frena el swipe mid-scroll
    if retention_idx is not None:
        filter_chains.append(f"[{current_v}][{retention_idx}:v]overlay=(W-w)/2:54:enable='between(t,5.0,7.2)'[v_retained]")
        current_v = "v_retained"

    # D) Superponer Subtítulos Karaoke palabra por palabra
    for s_idx, (_, start_s, end_s) in enumerate(sub_pngs):
        in_id = sub_inputs_start + s_idx
        next_v = f"v_sub_{s_idx}"
        # Transición limpia al frame gte*lt (evita parpadeo y solapamiento entre estados consecutivos)
        filter_chains.append(
            f"[{current_v}][{in_id}:v]overlay=(W-w)/2:{sub_y}:enable='gte(t,{start_s:.2f})*lt(t,{end_s:.2f})'[{next_v}]"
        )
        current_v = next_v

    if pad_sec > 0.0:
        filter_chains.append(f"[{current_v}]tpad=stop_mode=clone:stop_duration={pad_sec}[v_body]")
    else:
        filter_chains.append(f"[{current_v}]null[v_body]")

    if audio_filter:
        filter_chains.append(audio_filter)

    cmd.extend(["-filter_complex", ";".join(filter_chains)])
    cmd.extend(["-map", "[v_body]"])
    if total_dur is not None:
        cmd.extend(["-t", str(total_dur)])
    cmd.extend([
        "-c:v", FFMPEG_VIDEO_CODEC,
        "-b:v", FFMPEG_BITRATE,
        "-maxrate", "6500k",
        "-bufsize", "9000k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart"
    ])

    # Protocolo de Coexistencia: Limitar hilos de CPU para no asfixiar a GaTDSEQ
    threads_to_use = 1 if is_quant_busy() else FFMPEG_THREADS
    if is_quant_busy():
        print("[Coexistencia GaTDSEQ] Proceso cuantitativo activo en el Mac. Limitando FFmpeg a 1 hilo de CPU.")
    cmd.extend(["-threads", str(threads_to_use)])

    if audio_filter:
        cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])

    cmd.append(str(output_video))

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
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
    for extra_png in (vignette_png, hook_png, badge_png, retention_png):
        if extra_png and extra_png.exists():
            try:
                extra_png.unlink()
            except OSError:
                pass

    return True
import os
import re
import json
import random
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .config import (
    BASE_DIR, FFMPEG_VIDEO_CODEC, FFMPEG_BITRATE, FFMPEG_THREADS, SUBTITLE_OFFSET,
    is_quant_busy, ENABLE_4K_SHORTS, CANVAS_WIDTH, CANVAS_HEIGHT, FFMPEG_MAXRATE, FFMPEG_BUFSIZE
)
from .emoji_renderer import (
    split_text_and_emojis,
    measure_composite_line,
    draw_composite_line,
    clean_text_preserve_emojis,
    render_emoji_image,
    get_best_emoji_font
)
from .translator import truncate_on_word_boundary

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


def _has_audio_stream(media_path: Path) -> bool:
    """Comprueba con ffprobe si el archivo multimedia tiene al menos una pista de audio."""
    if not media_path or not media_path.exists():
        return False
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(media_path)],
            capture_output=True, text=True, timeout=8
        )
        return "audio" in (res.stdout or "").lower()
    except Exception:
        return False


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
    "alucinante", "exclusiva", "confirmado", "arma", "legendaria", "oculta", "pistola"
}

def render_top_hook_headline(hook_text: str, output_path: Path, scale_factor: float = 1.0) -> bool:
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

    pad_x = int(32 * scale_factor)
    pad_y = int(8 * scale_factor)
    spacing = int(8 * scale_factor) if line1 else 0
    size1 = int(56 * scale_factor)
    size2 = int(72 * scale_factor)
    max_box_w = int(980 * scale_factor)
    min_s1 = int(36 * scale_factor)
    min_s2 = int(44 * scale_factor)
    step1 = max(1, int(2 * scale_factor))
    step2 = max(1, int(3 * scale_factor))

    while True:
        font1 = get_viral_display_font(size=size1)
        font2 = get_viral_display_font(size=size2)
        w1, h1 = measure_composite_line(tokens1, font1, emoji_size=size1) if line1 else (0, 0)
        w2, h2 = measure_composite_line(tokens2, font2, emoji_size=max(int(36 * scale_factor), size2 - int(4 * scale_factor)))
        content_w = max(w1, w2)
        box_w = int(content_w + pad_x * 2)
        if box_w <= max_box_w or (size1 <= min_s1 and size2 <= min_s2):
            break
        size1 = max(min_s1, size1 - step1)
        size2 = max(min_s2, size2 - step2)

    box_h = int(h1 + h2 + spacing + pad_y * 2 + int(12 * scale_factor))

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Detectar qué línea lleva la palabra clave que realmente engancha (no resaltar al azar siempre la línea 2)
    def _hook_power_score(txt_line: str) -> float:
        if not txt_line:
            return -1.0
        power_kws = {
            "arma", "legendaria", "secreto", "secretos", "oculta", "oculto", "gratis",
            "dinero", "millones", "60fps", "30fps", "fps", "ps5", "pro", "rage", "9",
            "oficial", "confirmado", "filtrado", "estrellas", "persecucion", "persecución",
            "mision", "misión", "prologo", "prólogo", "easter", "egg", "fisicas", "físicas",
            "comparativa", "diferencia", "tiroteo", "atraco", "mapa", "truco", "bug", "error"
        }
        toks = [re.sub(r"[^a-záéíóúñü0-9]", "", w.lower()) for w in txt_line.split()]
        score = sum(3.0 for t in toks if t in power_kws)
        score += sum(2.0 for t in toks if any(ch.isdigit() for ch in t))
        # Penalizar si es principalmente ubicación/relleno ("en leonida", "de gta 6")
        if any(w in ("en", "de", "del") for w in toks[:1]):
            score -= 1.5
        return score

    highlight_line1 = bool(line1) and (_hook_power_score(line1) > _hook_power_score(line2))
    c_line1 = (255, 210, 63, 255) if highlight_line1 else (255, 255, 255, 255)
    c_line2 = (255, 255, 255, 255) if highlight_line1 else (255, 210, 63, 255)

    # Tipografía pura de alto impacto (sin caja de botón ni bordes artificiales)
    cur_y = pad_y
    stroke_w = max(2, int(5 * scale_factor))
    shadow_offset = max(2, int(4 * scale_factor))
    if line1:
        x1 = pad_x + (content_w - w1) / 2
        draw_composite_line(img, d, tokens1, int(x1 + shadow_offset), int(cur_y + shadow_offset), font1, fill_color=(0, 0, 0, 235), stroke_width=0, emoji_size=size1)
        draw_composite_line(img, d, tokens1, int(x1), int(cur_y), font1, fill_color=c_line1, stroke_color=(0, 0, 0, 255), stroke_width=stroke_w, emoji_size=size1)
        cur_y += h1 + spacing

    em2 = max(int(36 * scale_factor), size2 - int(4 * scale_factor))
    x2 = pad_x + (content_w - w2) / 2
    draw_composite_line(img, d, tokens2, int(x2 + shadow_offset), int(cur_y + shadow_offset), font2, fill_color=(0, 0, 0, 235), stroke_width=0, emoji_size=em2)
    draw_composite_line(img, d, tokens2, int(x2), int(cur_y), font2, fill_color=c_line2, stroke_color=(0, 0, 0, 255), stroke_width=stroke_w, emoji_size=em2)

    img.save(output_path, "PNG")
    return True

def render_retention_hook(output_path: Path, text: str = "ESPERA A VER ESTO", scale_factor: float = 1.0) -> bool:
    """
    Renderiza una micro-tarjeta de retención (segundo gancho) para mostrar entre 5.0-7.0s.
    Más pequeña y sutil que el hook principal, diseñada para frenar el swipe a mitad de Short.
    """
    clean = clean_text_preserve_emojis(text).upper()
    if not clean:
        return False

    font_sz = int(38 * scale_factor)
    font = get_best_font(size=font_sz)
    tokens = split_text_and_emojis(clean)
    tw, th = measure_composite_line(tokens, font, emoji_size=font_sz)

    pad_x, pad_y = int(36 * scale_factor), int(14 * scale_factor)
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle(
        [(0, 0), (box_w - 1, box_h - 1)],
        radius=int(18 * scale_factor),
        fill=(8, 8, 14, 200),
        outline=(0, 240, 255, 180),
        width=max(1, int(2 * scale_factor))
    )
    draw_composite_line(img, d, tokens, pad_x, pad_y, font, fill_color=(0, 240, 255, 255), stroke_color=(0, 0, 0, 255), stroke_width=max(1, int(2 * scale_factor)), emoji_size=font_sz)

    img.save(output_path, "PNG")
    return True


def render_persistent_context_badge(output_path: Path, text: str = "GTA 6 • VICE CITY", archetype: str = "", scale_factor: float = 1.0) -> bool:
    """
    Titular contextual viral de alto impacto (sin caja de botón):
    - Tipografía display condensada (Impact / Helvetica Condensed Black).
    - Auto-escalado dinámico para llenar el ancho disponible en 1 o 2 líneas balanceadas.
    - Color de acento dinámico según el arquetipo del clip + trazo grueso y sombra profunda.
    """
    clean = truncate_on_word_boundary(
        clean_text_preserve_emojis(text).replace("•", " ").strip().upper(),
        44,
    )
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

    # Dividir en 2 líneas visualmente equilibradas (por ancho de caracteres, sin partir palabras)
    words = clean.split()
    if len(clean) > 18 and len(words) >= 2:
        best_split = 1
        best_diff = 10**9
        for i in range(1, len(words)):
            l1 = " ".join(words[:i])
            l2 = " ".join(words[i:])
            diff = abs(len(l1) - len(l2))
            if diff < best_diff:
                best_diff = diff
                best_split = i
        lines = [" ".join(words[:best_split]), " ".join(words[best_split:])]
        max_font, min_font, max_h = int(62 * scale_factor), int(42 * scale_factor), int(130 * scale_factor)
    else:
        lines = [clean]
        max_font, min_font, max_h = int(78 * scale_factor), int(46 * scale_factor), int(110 * scale_factor)

    max_w = int(960 * scale_factor)
    font_size = max_font
    font_step = max(1, int(2 * scale_factor))
    while True:
        font = get_viral_display_font(size=font_size)
        measured = []
        for ln in lines:
            tks = split_text_and_emojis(ln)
            lw, lh = measure_composite_line(tks, font, emoji_size=font_size)
            measured.append((tks, lw, lh))
        total_w = max(m[1] for m in measured)
        line_gap = int(6 * scale_factor) if len(lines) > 1 else 0
        total_h = sum(m[2] for m in measured) + line_gap * max(0, len(lines) - 1)
        if (total_w <= max_w and total_h <= max_h) or font_size <= min_font:
            break
        font_size -= font_step

    canvas_w = max(total_w + int(48 * scale_factor), int(320 * scale_factor))
    underline_h = max(2, int(5 * scale_factor))
    canvas_h = total_h + int(24 * scale_factor) + underline_h

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cur_y = int(6 * scale_factor)
    stroke_w = max(2, int(4 * scale_factor))
    shadow_offset = max(2, int(4 * scale_factor))
    for idx, (tks, lw, lh) in enumerate(measured):
        x = int((canvas_w - lw) / 2)
        color = (255, 255, 255, 255) if (len(lines) == 1 or idx == 0) else (accent[0], accent[1], accent[2], 255)
        draw_composite_line(img, d, tks, x + shadow_offset, cur_y + shadow_offset, font, fill_color=(0, 0, 0, 235), stroke_width=0, emoji_size=font_size)
        draw_composite_line(img, d, tks, x, cur_y, font, fill_color=color, stroke_color=(0, 0, 0, 255), stroke_width=stroke_w, emoji_size=font_size)
        cur_y += lh + (int(6 * scale_factor) if len(lines) > 1 else 0)

    # Barra de acento neón sutil centrada bajo el titular
    bar_w = min(int(total_w * 0.55), int(420 * scale_factor))
    bar_x = int((canvas_w - bar_w) / 2)
    bar_y = cur_y + int(8 * scale_factor)
    d.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + underline_h)], radius=max(2, int(3 * scale_factor)), fill=(accent[0], accent[1], accent[2], 235))

    img.save(output_path, "PNG")
    return True


def build_karaoke_bursts_from_words(
    groq_words: List[Dict[str, Any]],
    max_words: int = 3
) -> List[Dict[str, Any]]:
    """
    Agrupa timestamps palabra-por-palabra reales (ej. Groq Whisper) en micro-ráfagas
    de 2-3 palabras garantizando estricta monotonicidad temporal sin solapamientos.
    """
    if not groq_words:
        return []

    cleaned = []
    for item in groq_words:
        txt = clean_text_no_emoji(str(item.get("word", ""))).upper().strip()
        if not txt:
            continue
        start_t = float(item.get("start", 0.0))
        end_t = max(start_t + 0.08, float(item.get("end", start_t + 0.25)))
        cleaned.append({"word": txt, "start": start_t, "end": end_t})

    if not cleaned:
        return []

    bursts: List[Dict[str, Any]] = []
    for i in range(0, len(cleaned), max_words):
        chunk = cleaned[i : i + max_words]
        words = [c["word"] for c in chunk]
        timings = []
        for idx, c in enumerate(chunk):
            w_start = c["start"]
            w_end = c["end"]
            if idx + 1 < len(chunk):
                next_start = chunk[idx + 1]["start"]
                if next_start > w_start + 0.06:
                    w_end = min(w_end, next_start)
            timings.append({
                "word_idx": idx,
                "start": round(w_start, 3),
                "end": round(max(w_start + 0.06, w_end), 3),
            })
        bursts.append({"words": words, "timings": timings})

    # Monotonicidad global entre ráfagas consecutivas
    for b_idx in range(len(bursts) - 1):
        cur_last = bursts[b_idx]["timings"][-1]
        nxt_first = bursts[b_idx + 1]["timings"][0]
        if cur_last["end"] > nxt_first["start"]:
            cur_last["end"] = round(max(cur_last["start"] + 0.05, nxt_first["start"]), 3)

    return bursts


def render_brand_watermark_pill(
    output_path: Path,
    brand_text: str = "@GTAVIHubExtra",
    scale_factor: float = 1.0
) -> bool:
    """
    Renderiza la marca de agua de canal Vice City con el icónico Testarossa y 'GTA6X'.
    Usa el asset de alta gama 'assets/watermark_gta6x_testarossa.png' si existe,
    con fallback procedural vectorizado.
    """
    custom_asset = BASE_DIR / "assets" / "watermark_gta6x_testarossa.png"
    if custom_asset.exists():
        try:
            wm_img = Image.open(custom_asset).convert("RGBA")
            target_w = max(180, int(230 * scale_factor))
            target_h = int(target_w * (wm_img.height / max(1, wm_img.width)))
            resized = wm_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            resized.save(output_path, "PNG")
            return True
        except Exception as e:
            print(f"[!] Aviso cargando asset de marca de agua: {e}")

    clean_brand = (brand_text or "@GTAVIHubExtra").strip()
    font_size = max(18, int(26 * scale_factor))
    font = get_viral_display_font(size=font_size)

    temp_img = Image.new("RGBA", (1, 1))
    d_temp = ImageDraw.Draw(temp_img)
    bbox = d_temp.textbbox((0, 0), clean_brand, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad_x = int(18 * scale_factor)
    pad_y = int(8 * scale_factor)
    canvas_w = tw + pad_x * 2
    canvas_h = th + pad_y * 2

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = max(6, int(10 * scale_factor))
    # Cápsula semi-transparente oscura con borde neón sutil
    d.rounded_rectangle(
        [(0, 0), (canvas_w - 1, canvas_h - 1)],
        radius=radius,
        fill=(10, 10, 16, 175),
        outline=(255, 0, 127, 210),
        width=max(1, int(2 * scale_factor)),
    )
    # Texto de marca blanco nítido con trazo fino
    d.text(
        (pad_x, pad_y - int(2 * scale_factor)),
        clean_brand,
        font=font,
        fill=(255, 255, 255, 240),
        stroke_fill=(0, 0, 0, 220),
        stroke_width=max(1, int(1.5 * scale_factor))
    )
    img.save(output_path, "PNG")
    return True


def render_follow_cta_pill(
    output_path: Path,
    text: str = "SIGUE PARA + SECRETOS DE LEONIDA",
    scale_factor: float = 1.0
) -> bool:
    """
    Renderiza una píldora CTA Vice City de alto contraste para los últimos 2.5s
    del vídeo, orientada a multiplicar la conversión a seguidores sin tapar subtítulos.
    """
    clean_cta = (text or "SIGUE PARA + SECRETOS DE LEONIDA").strip().upper()
    if not clean_cta:
        return False

    font_size = int(34 * scale_factor)
    min_font = max(14, int(20 * scale_factor))
    max_w = int(880 * scale_factor)
    step = max(1, int(2 * scale_factor))
    tokens = split_text_and_emojis(clean_cta)
    while True:
        font = get_viral_display_font(size=font_size)
        tw, th = measure_composite_line(tokens, font, emoji_size=font_size)
        if tw <= max_w or font_size <= min_font:
            break
        font_size -= step

    pad_x = int(32 * scale_factor)
    pad_y = int(16 * scale_factor)
    canvas_w = tw + pad_x * 2
    canvas_h = th + pad_y * 2

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = max(10, int(18 * scale_factor))
    d.rounded_rectangle(
        [(0, 0), (canvas_w - 1, canvas_h - 1)],
        radius=radius,
        fill=(14, 14, 24, 225),
        outline=(255, 0, 127, 245),
        width=max(2, int(3 * scale_factor)),
    )
    stroke_w = max(1, int(2 * scale_factor))
    draw_composite_line(
        img, d, tokens, pad_x, pad_y, font,
        fill_color=(255, 255, 255, 255),
        stroke_color=(0, 0, 0, 235),
        stroke_width=stroke_w,
        emoji_size=font_size,
    )
    img.save(output_path, "PNG")
    return True


def render_karaoke_subtitle_state(words: List[str], active_idx: int, is_vertical: bool, output_path: Path, scale_factor: float = 1.0, caspahz_style: bool = False) -> bool:
    """
    Renderiza subtítulos Pop Broadcast limpios y transparentes (estilo Shorts/TikTok viral):
    - Sin caja/píldora oscura detrás (no tapa la acción del gameplay).
    - Tipografía Heavy grande con trazo negro grueso y sombra paralela.
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

    max_w = int((740 if is_vertical else 1040) * scale_factor)
    font_size = int((70 if is_vertical else 50) * scale_factor)
    font = get_best_font(size=font_size)

    temp_img = Image.new("RGBA", (1, 1))
    d_temp = ImageDraw.Draw(temp_img)

    space_w = int(24 * scale_factor)
    min_font = int(40 * scale_factor)
    font_step = max(2, int(4 * scale_factor))

    # Ajustar tamaño de fuente dinámicamente si supera el ancho máximo seguro
    while font_size > min_font:
        test_w = sum(d_temp.textbbox((0, 0), w, font=font)[2] - d_temp.textbbox((0, 0), w, font=font)[0] for w in display_words)
        test_w += space_w * (len(display_words) - 1)
        if test_w <= max_w:
            break
        font_size -= font_step
        font = get_best_font(size=font_size)

    pop_font = get_best_font(size=font_size + max(4, int(8 * scale_factor)))
    from .emoji_renderer import is_color_emoji_supported
    has_emoji_support = is_vertical and is_color_emoji_supported()

    # Asignar casilla fija a cada palabra con el ancho máximo (normal o pop) para cero jitter
    cell_widths = []
    cell_pad = max(4, int(8 * scale_factor))
    for w in display_words:
        bb_normal = d_temp.textbbox((0, 0), w, font=font)
        w_norm = bb_normal[2] - bb_normal[0]
        bb_pop = d_temp.textbbox((0, 0), w, font=pop_font)
        w_pop = bb_pop[2] - bb_pop[0]
        cell_widths.append(max(w_norm, w_pop) + cell_pad)

    total_w = sum(cell_widths) + space_w * (len(display_words) - 1)
    sample_bb = pop_font.getbbox("AYÁÉÍÓÚÑjg")
    text_h = sample_bb[3]

    # Altura adicional para emoji si aplica
    emoji_room = int(46 * scale_factor) if has_emoji_support else 0

    pad_x = int(34 * scale_factor)
    pad_y = int(18 * scale_factor)
    box_w = int(total_w + pad_x * 2)
    box_h = int(text_h + pad_y * 2 + emoji_room + int(18 * scale_factor))

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pill_top = emoji_room

    # Detectar palabra activa y sus propiedades
    raw_active_word = display_words[active_idx] if 0 <= active_idx < len(display_words) else ""
    clean_active = re.sub(r'[^a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]', '', raw_active_word).lower()
    active_emoji = EMOJI_KEYWORDS.get(clean_active) if has_emoji_support else None
    is_hot_pink = clean_active in HOT_PINK_KEYWORDS
    is_filler_word = clean_active in {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
        "en", "y", "o", "a", "con", "por", "para", "que", "se", "su", "es", "son",
        "lo", "le", "les", "me", "te", "nos", "este", "esta", "esto", "ese", "esa",
        "muy", "mas", "más", "pero", "si", "sí", "ya"
    }

    if caspahz_style:
        is_money_or_num = ("$" in raw_active_word) or clean_active in {
            "dinero", "money", "cash", "mil", "hora", "hour", "dolar", "dolares", "dólar", "dólares"
        }
        is_caspahz_gold = clean_active in {
            "oro", "gold", "gratis", "free", "coche", "supercoche", "supercar", "rolls", "royce",
            "arma", "weapon", "legendaria", "legendary", "secreto", "secret", "oculta", "mapa",
            "ubicacion", "ubicación", "location", "glitch", "truco", "metodo", "método"
        }
        if is_money_or_num:
            active_color = (0, 255, 59, 255)      # Verde neón dinero estilo Caspahz
            glow_color = (0, 255, 59, 70)
        elif is_caspahz_gold:
            active_color = (255, 230, 0, 255)     # Amarillo brillante estilo Caspahz
            glow_color = (255, 230, 0, 70)
        else:
            active_color = (255, 255, 255, 255)   # Blanco puro limpio estilo Caspahz
            glow_color = (0, 0, 0, 0)
    elif is_hot_pink:
        active_color = (255, 59, 154, 255)   # Rosa Vice City para palabras gancho
        glow_color = (255, 59, 154, 115)
    elif is_filler_word:
        active_color = (235, 240, 255, 255)  # Conectores en blanco limpio (no resaltar relleno al azar)
        glow_color = (255, 255, 255, 45)
    else:
        active_color = (255, 210, 63, 255)   # Oro Rockstar para palabras de contenido real
        glow_color = (255, 210, 63, 100)

    base_y = pill_top + pad_y

    # 1. Resplandor sutil (glow) detrás de la palabra activa
    glow = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d_glow = ImageDraw.Draw(glow)
    cur_x = pad_x
    glow_stroke = max(5, int(10 * scale_factor))
    for idx, w in enumerate(display_words):
        cw = cell_widths[idx]
        if idx == active_idx:
            bb_pop = d_temp.textbbox((0, 0), w, font=pop_font)
            ww_pop = bb_pop[2] - bb_pop[0]
            draw_x = cur_x + (cw - ww_pop) / 2
            d_glow.text((draw_x, base_y - max(1, int(2 * scale_factor))), w, font=pop_font, fill=glow_color, stroke_width=glow_stroke, stroke_fill=glow_color)
        cur_x += cw + space_w

    glow_blur = max(3, int(5 * scale_factor))
    glow = glow.filter(ImageFilter.GaussianBlur(glow_blur))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    # 2. Dibujar texto con borde negro grueso de alto contraste y sombra paralela limpia (0 cajas)
    cur_x = pad_x
    shadow_x = max(2, int(3 * scale_factor))
    shadow_y = max(3, int(5 * scale_factor))
    for idx, w in enumerate(display_words):
        cw = cell_widths[idx]
        is_active = (idx == active_idx)
        current_font = pop_font if is_active else font
        text_color = active_color if is_active else (255, 255, 255, 255)
        stroke_w = int((8 if is_active else 6) * scale_factor)

        bb_w = d_temp.textbbox((0, 0), w, font=current_font)
        ww_act = bb_w[2] - bb_w[0]
        draw_x = cur_x + (cw - ww_act) / 2
        draw_y = base_y - (max(2, int(3 * scale_factor)) if is_active else 0)

        # Sombra paralela intensa para legibilidad absoluta sobre cielo/carretera/luces
        d.text((draw_x + shadow_x, draw_y + shadow_y), w, font=current_font, fill=(0, 0, 0, 235), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 210))
        # Trazo negro nítido + Relleno vibrante
        d.text((draw_x, draw_y), w, font=current_font, fill=text_color, stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))

        # Emoji contextual flotante encima si aplica
        if is_active and active_emoji:
            emo_img = render_emoji_image(active_emoji, target_size=int(42 * scale_factor))
            if emo_img:
                emoji_x = int(cur_x + (cw - emo_img.width) / 2)
                emoji_y = max(2, pill_top - emo_img.height - 2)
                img.alpha_composite(emo_img, (emoji_x, emoji_y))

        cur_x += cw + space_w

    img.save(output_path, "PNG")
    return True

def create_subtle_vignette(output_png: Path, fg_top: int = 160, fg_bottom: int = 1760, is_cinema: bool = False, w: int = CANVAS_WIDTH, h: int = CANVAS_HEIGHT) -> bool:
    """
    Genera gradientes cinemáticos con sombras de unión de tarjeta:
    - Viñetas en extremos superior e inferior adaptables a resolución 4K o 1080p.
    - En modo cinema: sombras suaves y sutil borde OLED en fg_top y fg_bottom.
    """
    scale_x = w / 1080.0
    scale_y = h / 1920.0
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if is_cinema:
        # Cabecera editorial oscura limpia (elimina el aspecto lavado de franja superior)
        top_limit = max(1, fg_top)
        for y in range(top_limit):
            alpha = int(235 - 55 * (y / top_limit))
            d.line([(0, y), (w, y)], fill=(7, 9, 15, alpha))

        # Sombra suave hacia el vídeo para transición orgánica
        shadow_h = int(32 * scale_y)
        for i in range(shadow_h):
            alpha = int(150 * (1 - (i / max(1, shadow_h))))
            if fg_top + i < h:
                d.line([(0, fg_top + i), (w, fg_top + i)], fill=(7, 9, 15, alpha))

        if fg_bottom < h - int(5 * scale_y):
            bot_fade = int(25 * scale_y)
            for i in range(bot_fade):
                alpha = int(130 * (1 - (i / max(1, bot_fade))))
                if fg_bottom + i < h:
                    d.line([(0, fg_bottom + i), (w, fg_bottom + i)], fill=(0, 0, 0, alpha))
            bot_start = max(fg_bottom, int(1740 * scale_y))
            bot_range = max(1, h - bot_start)
            for y in range(bot_range):
                alpha = int(120 * (y / bot_range))
                d.line([(0, bot_start + y), (w, bot_start + y)], fill=(0, 0, 0, alpha))
        else:
            # Degradado inferior sutil para legibilidad de UI sin cortar imagen
            bottom_grad = int(220 * scale_y)
            for y in range(bottom_grad):
                alpha = int(135 * (y / max(1, bottom_grad)))
                d.line([(0, h - bottom_grad + y), (w, h - bottom_grad + y)], fill=(0, 0, 0, alpha))
    else:
        top_v = int(160 * scale_y)
        for y in range(top_v):
            alpha = int(90 * (1 - (y / max(1, top_v))))
            d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
        bot_v = int(180 * scale_y)
        for y in range(bot_v):
            alpha = int(110 * (y / max(1, bot_v)))
            d.line([(0, h - bot_v + y), (w, h - bot_v + y)], fill=(0, 0, 0, alpha))

    img.save(output_png, "PNG")
    return True

def ensure_non_map_first_frame(video_path: Path, temp_dir: Path) -> Path:
    """
    Verifica con Gemini Vision si el frame 0 (0.2s) es una pantalla de mapa/menú estático.
    Si lo es, antepone un corte visual de 1.5s con la recompensa/acción (coche, arma, personaje)
    para que Frame 0 enganche al instante y el mapa salga después (t >= 1.5s).
    """
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return video_path
    samples = []
    try:
        from google.genai import types
        from .translator import get_gemini_client, generate_content_with_retry, clean_srt_response

        sample_times = [0.2, 4.0, 7.5, 11.0]
        contents = []
        valid_times = []
        for idx, t in enumerate(sample_times):
            jpg = temp_dir / f"_f0check_{video_path.stem}_{idx}.jpg"
            cmd = [
                "ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
                "-vframes", "1", "-q:v", "5", "-vf", "scale=480:-1", str(jpg)
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=8)
            if r.returncode == 0 and jpg.exists():
                samples.append(jpg)
                valid_times.append(t)
                contents.append(types.Part.from_bytes(data=jpg.read_bytes(), mime_type="image/jpeg"))

        if len(valid_times) < 2:
            return video_path

        prompt = (
            "Te paso 4 frames de un clip de GTA 6 en orden (Frame 0=0.2s, Frame 1=4.0s, Frame 2=7.5s, Frame 3=11.0s). "
            "¿El Frame 0 muestra una pantalla de MAPA / minimapa grande / menú de pausa en lugar de gameplay puro? "
            "Si es así, elige el índice (1, 2 o 3) que muestre GAMEPLAY PURO (coche, arma, personaje o recompensa) y CERO mapa en pantalla. "
            'Responde SOLO JSON: {"frame_0_is_map": true/false, "best_action_idx": 2}'
        )
        contents.append(prompt)
        client = get_gemini_client()
        resp = generate_content_with_retry(client=client, contents=contents)
        data = json.loads(clean_srt_response(resp.text or "{}"))
        if not data.get("frame_0_is_map"):
            return video_path

        act_idx = int(data.get("best_action_idx", 1))
        if act_idx < 1 or act_idx >= len(valid_times):
            act_idx = 1
        hook_t = valid_times[act_idx]

        # Anteponer 1.5s del momento de acción/recompensa al inicio manteniendo el audio original sincronizado
        out_path = temp_dir / f"{video_path.stem}_f0hook.mp4"
        cmd_hook = [
            "ffmpeg", "-y", "-threads", "1",
            "-ss", f"{hook_t:.2f}", "-t", "1.5", "-i", str(video_path),
            "-i", str(video_path),
            "-filter_complex",
            "[0:v]setpts=PTS-STARTPTS[vh];[1:v]setpts=PTS-STARTPTS[vm];[vh][vm]concat=n=2:v=1:a=0[vout]",
            "-map", "[vout]", "-map", "1:a?",
            "-c:v", "h264_videotoolbox" if os.uname().sysname == "Darwin" else "libx264",
            "-b:v", "8M", "-c:a", "copy", "-shortest", str(out_path)
        ]
        res_h = subprocess.run(cmd_hook, capture_output=True, timeout=45)
        if res_h.returncode == 0 and out_path.exists() and out_path.stat().st_size > 10000:
            print(f"[✓ Frame 0 Shield] Mapa detectado en 0.2s -> Antepuesto gancho visual de recompensa (t={hook_t:.1f}s) en Frame 0.")
            return out_path
    except Exception as e:
        print(f"[Frame 0 Shield] Aviso no bloqueante: {e}")
    finally:
        for s in samples:
            try:
                s.unlink(missing_ok=True)
            except Exception:
                pass
    return video_path


def inject_first_frame_cover(video_path: Path, cover_image_path: Path, duration_sec: float = 0.12) -> bool:
    """
    Inyecta una portada estática de `duration_sec` (0.12s = ~4 frames) al inicio exacto (Frame 0)
    del vídeo renderizado para que el feed de YouTube Shorts / TikTok muestre una portada limpia estilo Caspahz.
    """
    if not video_path.exists() or not cover_image_path.exists():
        return False
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", str(video_path)
            ],
            capture_output=True, text=True, timeout=10
        )
        if probe.returncode != 0:
            return False
        streams = json.loads(probe.stdout or "{}").get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not v_stream:
            return False
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        width = int(v_stream.get("width", 1080))
        height = int(v_stream.get("height", 1920))
        fps_str = v_stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/", 1)
            fps_val = float(num) / max(1.0, float(den))
        else:
            fps_val = float(fps_str)
        fps_val = max(24.0, min(60.0, fps_val))

        threads = "1" if is_quant_busy() else "2"
        vcodec = "h264_videotoolbox" if os.uname().sysname == "Darwin" else "libx264"
        tmp_out = video_path.with_name(f"{video_path.stem}_caspahz_cov.mp4")

        if has_audio:
            filter_complex = (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps_val:.3f},format=yuv420p[vc];"
                f"[1:v]setsar=1,fps={fps_val:.3f},format=yuv420p[vm];"
                f"[vc][2:a][vm][1:a]concat=n=2:v=1:a=1[vout][aout]"
            )
            cmd = [
                "ffmpeg", "-y", "-threads", threads,
                "-loop", "1", "-t", f"{duration_sec:.2f}", "-i", str(cover_image_path),
                "-i", str(video_path),
                "-f", "lavfi", "-t", f"{duration_sec:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", vcodec, "-b:v", "8M", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(tmp_out)
            ]
        else:
            filter_complex = (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps_val:.3f},format=yuv420p[vc];"
                f"[1:v]setsar=1,fps={fps_val:.3f},format=yuv420p[vm];"
                f"[vc][vm]concat=n=2:v=1:a=0[vout]"
            )
            cmd = [
                "ffmpeg", "-y", "-threads", threads,
                "-loop", "1", "-t", f"{duration_sec:.2f}", "-i", str(cover_image_path),
                "-i", str(video_path),
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-c:v", vcodec, "-b:v", "8M",
                "-movflags", "+faststart", str(tmp_out)
            ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 10000:
            tmp_out.replace(video_path)
            print(f"[✓ Caspahz Cover] Portada inyectada en Frame 0 ({duration_sec:.2f}s @ {width}x{height}).")
            return True
        if tmp_out.exists():
            tmp_out.unlink(missing_ok=True)
    except Exception as e:
        print(f"[Caspahz Cover] Aviso inyectando Frame 0: {e}")
    return False


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
    context_badge: str = "",
    cached_dimensions: Optional[Tuple[int, int]] = None,
    caspahz_style: bool = False
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
    if cached_dimensions:
        width, height = cached_dimensions
    else:
        width, height = get_video_dimensions(input_video)
    is_already_vertical = (height > width)
    is_vertical = force_short_format or is_already_vertical

    canvas_w = CANVAS_WIDTH
    canvas_h = CANVAS_HEIGHT
    scale_factor = canvas_w / 1080.0

    # Determinar preset: SPLIT (comparativa 50/50 apilada), D (Pro-Cinema 83.3%), C (4:5 70.3%) o FIT
    effective_preset = (format_preset or "").upper()
    if is_vertical and not is_already_vertical and effective_preset in ("", "AUTO", "FIT"):
        # Detectar automáticamente comparativas reales 50/50 lado-a-lado para apilarlas a pantalla completa
        if detect_horizontal_split_screen(input_video):
            effective_preset = "SPLIT"

    if not effective_preset or effective_preset == "AUTO":
        effective_preset = "FIT"

    y1, y2 = int(48 * scale_factor), int(956 * scale_factor)
    panel_h = int(900 * scale_factor)
    if is_vertical and not is_already_vertical:
        if effective_preset == "SPLIT":
            # Formato SPLIT: Comparativa 50/50 lado-a-lado convertida a dos paneles apilados (93.8% cobertura)
            fg_w = canvas_w
            panel_h = int(900 * scale_factor)
            fg_h = int(1808 * scale_factor)
            fg_y = int(48 * scale_factor)
            y1 = int(48 * scale_factor)
            y2 = int(956 * scale_factor)
            fg_bottom = int(1856 * scale_factor)
            is_cinema_layout = True
            hook_y_expr = str(int(740 * scale_factor))
            ret_y_expr = str(int(740 * scale_factor))
            sub_y = str(int(1520 * scale_factor))
            print(f"[*] Modo Formato SPLIT Apilado 50/50 (93.8% cobertura): 2x {canvas_w}x{panel_h} @ y={y1} / y={y2}.")
        elif effective_preset == "FIT":
            # Formato FIT (16:9 completo sin recorte lateral, reservado a casos extremos)
            fg_w = canvas_w
            fg_h = int(608 * scale_factor)
            fg_y = int(610 * scale_factor)
            fg_bottom = int(1218 * scale_factor)
            is_cinema_layout = True
            hook_y_expr = str(int(340 * scale_factor))
            ret_y_expr = str(int(400 * scale_factor))
            sub_y = str(int(1260 * scale_factor))
            print(f"[*] Modo Formato FIT 16:9 Completo (sin recorte lateral): {fg_w}x{fg_h} @ y={fg_y} con Velvet Canvas.")
        elif effective_preset == "D":
            # Formato D Alpha (89.1% cobertura Edge-to-Bottom):
            # Anclado abajo sin franja borrosa inferior, cabecera editorial limpia arriba.
            fg_w = canvas_w
            fg_h = int(1710 * scale_factor)
            fg_y = int(210 * scale_factor)
            fg_bottom = canvas_h
            is_cinema_layout = True
            hook_y_expr = str(int(175 * scale_factor))
            ret_y_expr = str(int(175 * scale_factor))
            sub_y = str(int(1260 * scale_factor))
            print(f"[*] Modo Formato D Pro-Cinema (89.1% cobertura Edge-to-Bottom): {fg_w}x{fg_h} @ y={fg_y} ({canvas_w}x{canvas_h}).")
        else:
            # Formato C (Smart Frame Inmersivo 4:5, 70.3% de cobertura):
            # Centrado con Ambient Canvas (2.2x más área visual que FIT).
            fg_w = canvas_w
            fg_h = int(1350 * scale_factor)
            fg_y = int(285 * scale_factor)
            fg_bottom = int(1635 * scale_factor)
            is_cinema_layout = True
            hook_y_expr = str(int(175 * scale_factor))
            ret_y_expr = str(int(190 * scale_factor))
            sub_y = str(int(1240 * scale_factor))
            print(f"[*] Modo Formato C Smart Frame 4:5 (70.3% cobertura): {fg_w}x{fg_h} @ y={fg_y} con Ambient Canvas.")
    else:
        # Formato Vertical Nativo 9:16
        fg_w = canvas_w
        fg_h = canvas_h
        fg_y = 0
        fg_bottom = canvas_h
        is_cinema_layout = False
        hook_y_expr = str(int(175 * scale_factor))
        ret_y_expr = str(int(210 * scale_factor))
        sub_y = str(int(1240 * scale_factor)) if is_vertical else "H-h-90"
        print(f"[*] Modo Vertical Nativo 9:16: Pantalla completa sin deformación (Vertical: {is_vertical}, {canvas_w}x{canvas_h}).")

    # 1. Viñeta y sombras de unión
    vignette_png = temp_dir / f"{base_name}_vignette.png"
    create_subtle_vignette(vignette_png, fg_top=fg_y, fg_bottom=fg_bottom, is_cinema=is_cinema_layout, w=canvas_w, h=canvas_h)

    # 2. Gancho textual superior (0 a 2.8s) y Badge persistente editorial (>= 2.8s)
    # En estilo Caspahz, vídeo vertical nativo (is_already_vertical) o SPLIT, mantener 100% limpio arriba (sin titulares cambiantes).
    hook_png = None
    badge_png = None
    if hook_text and is_vertical and not is_already_vertical and not caspahz_style:
        hook_png = temp_dir / f"{base_name}_hook.png"
        rendered_hook = render_top_hook_headline(hook_text, hook_png, scale_factor=scale_factor)
        if not rendered_hook:
            hook_png = None

        if effective_preset != "SPLIT":
            hook_lines = [ln.strip() for ln in hook_text.splitlines() if ln.strip()]
            badge_label = (context_badge or "").strip()
            if not badge_label:
                # Si no hay context_badge explícito, preferir la 2ª línea (más específica) si existe
                badge_label = hook_lines[1] if len(hook_lines) >= 2 else (hook_lines[0] if hook_lines else "GTA 6 • VICE CITY")
            badge_png = temp_dir / f"{base_name}_badge.png"
            if not render_persistent_context_badge(badge_png, text=badge_label, archetype=archetype, scale_factor=scale_factor):
                badge_png = None

    # 2b. Micro-tarjeta genérica de los 5.0s desactivada por defecto en estándar Alpha (evita parpadeos y frases cliché)
    retention_png = None

    # 2c. Píldora CTA de seguimiento en los últimos 2.5s (desactivada en estilo Caspahz limpio)
    cta_png = None
    enable_follow_cta = os.getenv("ENABLE_FOLLOW_CTA", "true").lower() in ("true", "1", "yes")
    if enable_follow_cta and is_vertical and not caspahz_style:
        cta_text = os.getenv("FOLLOW_CTA_TEXT", "➕ SIGUE PARA + SECRETOS DE LEONIDA")
        cta_png = temp_dir / f"{base_name}_cta.png"
        if not render_follow_cta_pill(cta_png, text=cta_text, scale_factor=scale_factor):
            cta_png = None

    # 2d. Marca de agua de canal semi-transparente (visibilidad e insistencia de marca permanente)
    watermark_png = None
    enable_watermark = os.getenv("ENABLE_BRAND_WATERMARK", "true").lower() in ("true", "1", "yes")
    if enable_watermark and is_vertical:
        brand_handle = os.getenv("BRAND_WATERMARK_TEXT", "@GTAVIHubExtra")
        watermark_png = temp_dir / f"{base_name}_brand_wm.png"
        if not render_brand_watermark_pill(watermark_png, brand_text=brand_handle, scale_factor=scale_factor):
            watermark_png = None

    # 3. Generación de estados de Karaoke palabra por palabra
    # Prioridad 1 ($0): Timestamps exactos de Groq Whisper sobre el doblaje si GROQ_API_KEY está configurada.
    # Fallback determinista: parse_srt_file() + calculate_word_timing() (nunca detiene el render).
    sub_pngs = []
    global_sub_idx = 0
    groq_bursts: List[Dict[str, Any]] = []
    enable_groq_sync = os.getenv("ENABLE_GROQ_SYNC", "true").lower() in ("true", "1", "yes")
    if enable_groq_sync and srt_subtitles and dub_audio and dub_audio.exists() and (os.getenv("GROQ_API_KEY") or "").strip():
        try:
            from .dubber import get_word_timestamps_groq
            groq_words = get_word_timestamps_groq(dub_audio, language="es")
            if groq_words:
                groq_bursts = build_karaoke_bursts_from_words(groq_words, max_words=3)
        except Exception as e:
            print(f"[!] [Groq Sync] Fallback a cálculo SRT estándar: {e}")

    if groq_bursts:
        for burst in groq_bursts[:250]:
            words = burst["words"]
            for tw in burst["timings"]:
                sub_png = temp_dir / f"{base_name}_ksub_{global_sub_idx}.png"
                rendered = render_karaoke_subtitle_state(
                    words=words,
                    active_idx=tw["word_idx"],
                    is_vertical=is_vertical,
                    output_path=sub_png,
                    scale_factor=scale_factor,
                    caspahz_style=caspahz_style
                )
                if rendered:
                    sub_pngs.append((sub_png, tw["start"], tw["end"]))
                    global_sub_idx += 1
    else:
        # En audio doblado neural, la sincronía fonética es directa (offset=0.0s).
        # En audio original en inglés con YouTube ASR, se mantiene SUBTITLE_OFFSET (-0.45s).
        effective_sub_offset = 0.0 if (dub_audio and dub_audio.exists()) else None
        cues = parse_srt_file(srt_subtitles, offset_seconds=effective_sub_offset) if srt_subtitles else []
        sub_cues = cues[:250]

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
                    output_path=sub_png,
                    scale_factor=scale_factor,
                    caspahz_style=caspahz_style
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
    has_orig_audio = _has_audio_stream(input_video)
    if dub_idx is not None:
        if not has_orig_audio:
            if ambient_idx is not None:
                fade_tail = f",afade=t=out:st={max(0.0, total_dur - 0.35):.2f}:d=0.35" if pad_sec > 0.0 else ""
                audio_filter = (
                    f"[{ambient_idx}:a]volume=0.06[amb];"
                    f"[{dub_idx}:a]aresample=async=1[voice];"
                    f"[voice][amb]amix=inputs=2:duration=first:normalize=false{fade_tail}[a_mix]"
                )
            else:
                if pad_sec > 0.0:
                    fade_start = max(0.0, total_dur - 0.35)
                    audio_filter = f"[{dub_idx}:a]afade=t=out:st={fade_start:.2f}:d=0.35[a_mix]"
                else:
                    audio_filter = f"[{dub_idx}:a]anull[a_mix]"
        elif pad_sec > 0.0:
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

    # Píldora CTA de seguimiento (últimos 2.5s)
    cta_idx = None
    if cta_png and cta_png.exists():
        cmd.extend(["-i", str(cta_png)])
        cta_idx = input_idx
        input_idx += 1

    # Marca de agua de canal semi-transparente
    watermark_idx = None
    if watermark_png and watermark_png.exists():
        cmd.extend(["-i", str(watermark_png)])
        watermark_idx = input_idx
        input_idx += 1

    # Subtítulos Karaoke como inputs
    sub_inputs_start = input_idx
    for sp, _, _ in sub_pngs:
        cmd.extend(["-i", str(sp)])
        input_idx += 1

    filter_chains = []

    # A) Base de vídeo:
    if is_vertical and not is_already_vertical:
        bg_scale_w = 270
        bg_scale_h = 480
        if effective_preset == "SPLIT":
            # Comparativa lado-a-lado 50/50 convertida en 2 paneles apilados (preserva etiquetas superiores)
            v_base = (
                "[0:v]split=3[v1][vl_in][vr_in];"
                f"[v1]scale={bg_scale_w}:{bg_scale_h},boxblur=10:2,scale={canvas_w}:{canvas_h}:flags=bilinear,eq=brightness=-0.28:contrast=1.06:saturation=1.12[bg];"
                f"[vl_in]crop=iw/2:ih:0:0,scale={canvas_w}:{panel_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{panel_h}:(iw-{canvas_w})/2:0,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.10[vtop];"
                f"[vr_in]crop=iw/2:ih:iw/2:0,scale={canvas_w}:{panel_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{panel_h}:(iw-{canvas_w})/2:0,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.10[vbot];"
                f"[bg][vtop]overlay=0:{y1}[v_split_top];"
                f"[v_split_top][vbot]overlay=0:{y2}[v_framed]"
            )
        elif effective_preset == "FIT":
            # Formato FIT: 16:9 completo sin recorte lateral sobre Velvet Blur reactivo
            v_base = (
                "[0:v]split[v1][v2];"
                f"[v1]scale={bg_scale_w}:{bg_scale_h},boxblur=10:2,scale={canvas_w}:{canvas_h}:flags=bilinear,setsar=1,eq=brightness=-0.14:contrast=1.06:saturation=1.18[bg];"
                f"[v2]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease,pad={fg_w}:{fg_h}:(ow-iw)/2:(oh-ih)/2:color=black,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
                f"[bg][fg]overlay=0:{fg_y}[v_framed]"
            )
        else:
            # Formato D / C: Plano recortado inmersivo sobre fondo Velvet Blur + acabado Vice City HDR
            v_base = (
                "[0:v]split[v1][v2];"
                f"[v1]scale={bg_scale_w}:{bg_scale_h},boxblur=10:2,scale={canvas_w}:{canvas_h}:flags=bilinear,setsar=1,eq=brightness=-0.14:contrast=1.06:saturation=1.18[bg];"
                f"[v2]scale={fg_w}:{fg_h}:force_original_aspect_ratio=increase,crop={fg_w}:{fg_h},unsharp=3:3:0.75:3:3:0.0,eq=contrast=1.09:saturation=1.18[fg];"
                f"[bg][fg]overlay=0:{fg_y}[v_framed]"
            )
    elif is_vertical:
        # Formato C (Nativo Vertical 9:16): Pantalla completa sin bandas + acabado Vice City HDR
        v_base = f"[0:v]scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{canvas_h},unsharp=3:3:0.75:3:3:0.0,eq=contrast=1.09:saturation=1.18[v_framed]"
    else:
        v_base = "[0:v]unsharp=3:3:0.75:3:3:0.0,eq=contrast=1.09:saturation=1.18[v_framed]"
    
    filter_chains.append(v_base)
    filter_chains.append("[v_framed]setsar=1[v_sar]")
    current_v = "v_sar"

    # B) Superponer Viñeta sutil y sombras de unión
    filter_chains.append(f"[{current_v}][{vignette_idx}:v]overlay=0:0[v_vignetted]")
    current_v = "v_vignetted"

    # C) Superponer Gancho Superior (0.0 a 2.4s — entrada más ágil para retención)
    if hook_idx is not None:
        filter_chains.append(f"[{current_v}][{hook_idx}:v]overlay=(W-w)/2:{hook_y_expr}:enable='between(t,0,2.4)'[v_hooked]")
        current_v = "v_hooked"

    # C1) Superponer Titular contextual viral (>= 2.4s, pausado en últimos 2.5s si hay CTA de cierre)
    effective_total_dur = total_dur if total_dur is not None else max(4.0, v_dur)
    cta_start = max(3.0, round(effective_total_dur - 2.5, 2))
    cta_active = (cta_idx is not None) and (effective_total_dur >= 5.5)

    if badge_idx is not None:
        if retention_idx is not None and cta_active:
            badge_enable = f"(gte(t,2.4)*lt(t,5.0)+gte(t,7.2))*lt(t,{cta_start:.2f})"
        elif retention_idx is not None:
            badge_enable = "gte(t,2.4)*lt(t,5.0)+gte(t,7.2)"
        elif cta_active:
            badge_enable = f"gte(t,2.4)*lt(t,{cta_start:.2f})"
        else:
            badge_enable = "gte(t,2.4)"
        badge_y = int(178 * scale_factor)
        filter_chains.append(f"[{current_v}][{badge_idx}:v]overlay=(W-w)/2:{badge_y}:enable='{badge_enable}'[v_badged]")
        current_v = "v_badged"

    # C2) Superponer segundo gancho de retención (5.0 a 7.2s) — frena el swipe mid-scroll
    if retention_idx is not None:
        ret_y = int(190 * scale_factor)
        filter_chains.append(f"[{current_v}][{retention_idx}:v]overlay=(W-w)/2:{ret_y}:enable='between(t,5.0,7.2)'[v_retained]")
        current_v = "v_retained"

    # C3) Píldora CTA de seguimiento en los últimos 2.5s (zona editorial superior, cero choque con subtítulos)
    if cta_active:
        cta_y = int(178 * scale_factor)
        filter_chains.append(f"[{current_v}][{cta_idx}:v]overlay=(W-w)/2:{cta_y}:enable='gte(t,{cta_start:.2f})'[v_cta]")
        current_v = "v_cta"

    # C4) Marca de agua de canal persistente y discreta (esquina superior derecha debajo de cabecera UI iOS/YT)
    if watermark_idx is not None:
        wm_x = f"W-w-{int(34 * scale_factor)}"
        wm_y = int(178 * scale_factor)
        filter_chains.append(f"[{current_v}][{watermark_idx}:v]overlay={wm_x}:{wm_y}[v_branded]")
        current_v = "v_branded"

    # D) Superponer Subtítulos Karaoke palabra por palabra (margen derecho libre para botones Like/Guardar)
    sub_x_expr = f"(W-w)/2-{int(45 * scale_factor)}" if is_vertical else "(W-w)/2"
    for s_idx, (_, start_s, end_s) in enumerate(sub_pngs):
        in_id = sub_inputs_start + s_idx
        next_v = f"v_sub_{s_idx}"
        # Transición limpia al frame gte*lt (evita parpadeo y solapamiento entre estados consecutivos)
        filter_chains.append(
            f"[{current_v}][{in_id}:v]overlay={sub_x_expr}:{sub_y}:enable='gte(t,{start_s:.2f})*lt(t,{end_s:.2f})'[{next_v}]"
        )
        current_v = next_v

    # E) Barra de progreso neón Vice City (3px en el borde superior, coste ~0 CPU)
    enable_progress_bar = os.getenv("ENABLE_PROGRESS_BAR", "true").lower() in ("true", "1", "yes")
    if enable_progress_bar and is_vertical and effective_total_dur > 1.0:
        bar_h = max(3, int(4 * scale_factor))
        filter_chains.append(f"color=c=0xFF007F:s={canvas_w}x{bar_h},format=rgba[pbar]")
        filter_chains.append(
            f"[{current_v}][pbar]overlay=x='-W+(W*min(1,t/{effective_total_dur:.2f}))':y=0:shortest=1[v_pbar]"
        )
        current_v = "v_pbar"

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
        "-maxrate", FFMPEG_MAXRATE,
        "-bufsize", FFMPEG_BUFSIZE,
        "-pix_fmt", "yuv420p",
        "-map_metadata", "-1",
        "-movflags", "+faststart"
    ])

    # Protocolo de Coexistencia: Limitar hilos de CPU para no asfixiar a GaTDSEQ
    threads_to_use = 1 if is_quant_busy() else FFMPEG_THREADS
    if is_quant_busy():
        print("[Coexistencia GaTDSEQ] Proceso cuantitativo activo en el Mac. Limitando FFmpeg a 1 hilo de CPU.")
    cmd.extend([
        "-threads", str(threads_to_use),
        "-filter_threads", str(threads_to_use),
        "-filter_complex_threads", str(threads_to_use),
    ])

    if audio_filter:
        cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])

    cmd.append(str(output_video))

    render_ok = False
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=360)
        print(f"[✓] Vídeo exportado con éxito -> {output_video.name}")
        render_ok = True
    except subprocess.TimeoutExpired:
        print("[!] Timeout de 360s renderizando vídeo FFmpeg.")
        if output_video.exists():
            output_video.unlink(missing_ok=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Error de renderizado FFmpeg: {e.stderr.strip() if e.stderr else e}")
        if output_video.exists():
            output_video.unlink(missing_ok=True)
    finally:
        # Limpieza garantizada de imágenes temporales (incluso si falla o expira el render)
        for sp, _, _ in sub_pngs:
            try:
                sp.unlink(missing_ok=True)
            except OSError:
                pass
        for extra_png in (vignette_png, hook_png, badge_png, retention_png, cta_png):
            if extra_png and extra_png.exists():
                try:
                    extra_png.unlink(missing_ok=True)
                except OSError:
                    pass

    return render_ok


def apply_seamless_loop(video_path: Path, crossfade_sec: float = 0.4) -> bool:
    """
    Aplica un crossfade visual entre el final y el inicio del video
    para crear la ilusion de bucle continuo en YouTube Shorts.
    Modifica el archivo in-place. Retorna True si exitoso.
    """
    if not video_path.exists():
        return False

    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0
        if duration < 8.0:
            return False

        cf = min(crossfade_sec, duration * 0.08)
        temp_out = video_path.parent / f"{video_path.stem}_loop.mp4"
        threads = 1 if is_quant_busy() else FFMPEG_THREADS

        # Estrategia: duplicar el video y hacer xfade entre el final de la primera copia
        # y el inicio de la segunda, luego cortar a la duracion original
        cmd = [
            "ffmpeg", "-y", "-threads", str(threads),
            "-i", str(video_path),
            "-i", str(video_path),
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={cf}:offset={duration - cf}[vout];"
            f"[0:a][1:a]acrossfade=d={cf}[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-t", str(duration),
            "-c:v", FFMPEG_VIDEO_CODEC,
            "-b:v", FFMPEG_BITRATE,
            "-maxrate", FFMPEG_MAXRATE,
            "-bufsize", FFMPEG_BUFSIZE,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(temp_out)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and temp_out.exists() and temp_out.stat().st_size > 1000:
            video_path.unlink(missing_ok=True)
            temp_out.rename(video_path)
            print(f"[Seamless Loop] Crossfade de {cf:.2f}s aplicado para bucle continuo.")
            return True
        else:
            temp_out.unlink(missing_ok=True)
            return False
    except Exception as e:
        print(f"[Seamless Loop] Info: {e}")
        return False
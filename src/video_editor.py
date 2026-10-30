import os
import re
import json
import random
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .config import BASE_DIR, FFMPEG_VIDEO_CODEC, FFMPEG_BITRATE, FFMPEG_THREADS, SUBTITLE_OFFSET, is_quant_busy

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
    """Carga la tipografía nativa de emojis a color de Apple en macOS."""
    for p in ["/System/Library/Fonts/Apple Color Emoji.ttc", "/System/Library/Fonts/Supplemental/Apple Color Emoji.ttc"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return None

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
    """Renderiza una potente y espectacular tarjeta de gancho superior estilo Broadcast Viral (0.0 a 2.5s)."""
    clean_hook = clean_text_no_emoji(hook_text).upper()
    if not clean_hook:
        return False
    
    words = clean_hook.split()
    if len(words) >= 4:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
    elif len(words) == 3:
        line1 = words[0]
        line2 = " ".join(words[1:])
    else:
        line1 = ""
        line2 = clean_hook

    font1 = get_best_font(size=46)
    font2 = get_best_font(size=60)
    d_temp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    if line1:
        bb1 = d_temp.textbbox((0, 0), line1, font=font1)
        w1 = bb1[2] - bb1[0]
        h1 = bb1[3] - bb1[1]
    else:
        w1, h1 = 0, 0

    bb2 = d_temp.textbbox((0, 0), line2, font=font2)
    w2 = bb2[2] - bb2[0]
    h2 = bb2[3] - bb2[1]

    content_w = max(w1, w2)
    pad_x = 52
    pad_y = 20
    spacing = 14 if line1 else 0
    box_w = int(content_w + pad_x * 2)
    box_h = int(h1 + h2 + spacing + pad_y * 2)

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Tarjeta de cristal ahumado estilo eSports / YouTube Gaming con resplandor dorado
    d.rounded_rectangle(
        [(0, 0), (box_w - 1, box_h - 1)],
        radius=24,
        fill=(8, 8, 14, 230),
        outline=(255, 230, 0, 160),
        width=3
    )

    cur_y = pad_y
    if line1:
        x1 = pad_x + (content_w - w1) / 2
        # Sombra profunda
        d.text((x1 + 3, cur_y + 3), line1, font=font1, fill=(0, 0, 0, 240))
        # Línea 1: Blanco Puro con trazo negro
        d.text((x1, cur_y), line1, font=font1, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))
        cur_y += h1 + spacing

    x2 = pad_x + (content_w - w2) / 2
    # Sombra profunda
    d.text((x2 + 3, cur_y + 4), line2, font=font2, fill=(0, 0, 0, 240))
    # Línea 2: Amarillo Eléctrico Neón (#FFE600) con trazo negro de impacto
    d.text((x2, cur_y), line2, font=font2, fill=(255, 230, 0, 255), stroke_width=4, stroke_fill=(0, 0, 0, 255))

    img.save(output_path, "PNG")
    return True

def render_retention_hook(output_path: Path, text: str = "ESPERA A VER ESTO") -> bool:
    """
    Renderiza una micro-tarjeta de retención (segundo gancho) para mostrar entre 5.0-7.0s.
    Más pequeña y sutil que el hook principal, diseñada para frenar el swipe a mitad de Short.
    """
    clean = clean_text_no_emoji(text).upper()
    if not clean:
        return False

    font = get_best_font(size=38)
    d_temp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = d_temp.textbbox((0, 0), clean, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]

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
    d.text((pad_x, pad_y), clean, font=font, fill=(0, 240, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))

    img.save(output_path, "PNG")
    return True

def render_karaoke_subtitle_state(words: List[str], active_idx: int, is_vertical: bool, output_path: Path) -> bool:
    """
    Renderiza un estado Karaoke palabra por palabra nivel Broadcast Viral:
    - Píldora de contraste con fondo oscuro sutil (100% de legibilidad en cualquier fondo).
    - Cubre limpiamente subtítulos preexistentes en inglés si los hubiera.
    - La frase permanece 100% fija y estable horizontalmente (cero temblores/jitter).
    - Tipografía grande y de impacto (font_size=64, pop=72) para lectura instantánea en móvil.
    - La palabra activa se resalta en Amarillo (#FFE600) o Rosa Neón (#FF2D87).
    - Las palabras inactivas de la frase permanecen en Blanco Puro (#FFFFFF).
    - Espaciado amplio y márgenes laterales generosos (pad_x=48) para que ninguna letra toque los bordes.
    """
    if not words:
        return False

    # Limpiar puntuación residual colgante (puntos, comas) para estética moderna de subtítulos
    display_words = [re.sub(r'[.,;:]+$', '', w).strip() for w in words]
    display_words = [w for w in display_words if w]
    if not display_words:
        return False

    max_w = 900 if is_vertical else 1000
    font_size = 64 if is_vertical else 48
    font = get_best_font(size=font_size)

    temp_img = Image.new("RGBA", (1, 1))
    d_temp = ImageDraw.Draw(temp_img)

    space_w = 28

    # Ajustar tamaño de fuente dinámicamente si supera el ancho máximo seguro
    while font_size > 38:
        test_w = sum(d_temp.textbbox((0, 0), w, font=font)[2] - d_temp.textbbox((0, 0), w, font=font)[0] for w in display_words)
        test_w += space_w * (len(display_words) - 1)
        if test_w <= max_w:
            break
        font_size -= 4
        font = get_best_font(size=font_size)

    pop_font = get_best_font(size=font_size + 6)
    emoji_font = get_emoji_font(size=44) if is_vertical else None

    # Asignar casilla fija a cada palabra con el ancho máximo (normal o pop) para cero jitter y cero colisiones
    cell_widths = []
    for w in display_words:
        bb_normal = d_temp.textbbox((0, 0), w, font=font)
        w_norm = bb_normal[2] - bb_normal[0]
        bb_pop = d_temp.textbbox((0, 0), w, font=pop_font)
        w_pop = bb_pop[2] - bb_pop[0]
        cell_widths.append(max(w_norm, w_pop) + 6)

    total_w = sum(cell_widths) + space_w * (len(display_words) - 1)
    sample_bb = font.getbbox("AY")
    text_h = (sample_bb[3] - sample_bb[1])

    # Altura adicional para emoji si aplica
    emoji_room = 46 if (is_vertical and emoji_font) else 0

    pad_x = 48
    pad_y = 20
    box_w = int(total_w + pad_x * 2)
    box_h = int(text_h + pad_y * 2 + emoji_room + 10)

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 1. Píldora de Contraste Traslúcida (Dark Pill Backdrop con borde suave)
    pill_top = emoji_room
    d.rounded_rectangle(
        [(0, pill_top), (box_w - 1, box_h - 1)],
        radius=22,
        fill=(10, 10, 16, 220),
        outline=(255, 255, 255, 50),
        width=2
    )

    # Detectar palabra activa y sus propiedades
    raw_active_word = display_words[active_idx] if 0 <= active_idx < len(display_words) else ""
    clean_active = re.sub(r'[^a-zA-ZáéíóúñÁÉÍÓÚÑ]', '', raw_active_word).lower()
    active_emoji = EMOJI_KEYWORDS.get(clean_active) if emoji_font else None
    is_hot_pink = clean_active in HOT_PINK_KEYWORDS

    active_color = (255, 45, 135, 255) if is_hot_pink else (255, 230, 0, 255)
    glow_color = (255, 45, 135, 140) if is_hot_pink else (255, 230, 0, 140)

    base_y = pill_top + pad_y

    # 2. Resplandor sutil (glow) para la palabra activa
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

    glow = glow.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    # 3. Dibujar las palabras de la frase perfectamente centradas en su casilla fija
    cur_x = pad_x
    for idx, w in enumerate(display_words):
        cw = cell_widths[idx]
        is_active = (idx == active_idx)
        current_font = pop_font if is_active else font
        text_color = active_color if is_active else (255, 255, 255, 255)
        stroke_w = 5 if is_active else 4

        bb_w = d_temp.textbbox((0, 0), w, font=current_font)
        ww_act = bb_w[2] - bb_w[0]
        draw_x = cur_x + (cw - ww_act) / 2
        draw_y = base_y - (2 if is_active else 0)

        # Sombra de profundidad 3D
        d.text((draw_x + 3, draw_y + 4), w, font=current_font, fill=(0, 0, 0, 240))
        # Trazo negro nítido + Relleno de color
        d.text((draw_x, draw_y), w, font=current_font, fill=text_color, stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))

        # Emoji contextual flotante encima si aplica
        if is_active and active_emoji and emoji_font:
            emoji_x = int(cur_x + (cw - 44) / 2)
            emoji_y = max(2, pill_top - 42)
            try:
                d.text((emoji_x, emoji_y), active_emoji, font=emoji_font, embedded_color=True)
            except Exception:
                pass

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
        top_limit = max(1, min(180, fg_top))
        for y in range(top_limit):
            alpha = int(120 * (1 - (y / top_limit)))
            d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

        # Sombras de unión superior e inferior
        for i in range(25):
            alpha = int(130 * (1 - (i / 25)))
            if fg_top - i >= 0:
                d.line([(0, fg_top - i), (w, fg_top - i)], fill=(0, 0, 0, alpha))
            if fg_bottom + i < h:
                d.line([(0, fg_bottom + i), (w, fg_bottom + i)], fill=(0, 0, 0, alpha))

        # Borde sutil blanco translúcido
        d.line([(0, fg_top), (w, fg_top)], fill=(255, 255, 255, 30), width=2)
        d.line([(0, fg_bottom), (w, fg_bottom)], fill=(255, 255, 255, 30), width=2)

        bot_start = max(fg_bottom, 1740)
        bot_range = max(1, h - bot_start)
        for y in range(bot_range):
            alpha = int(120 * (y / bot_range))
            d.line([(0, bot_start + y), (w, bot_start + y)], fill=(0, 0, 0, alpha))
    else:
        for y in range(160):
            alpha = int(90 * (1 - (y / 160)))
            d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
        for y in range(180):
            alpha = int(110 * (y / 180))
            d.line([(0, 1920 - 180 + y), (w, 1920 - 180 + y)], fill=(0, 0, 0, alpha))

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
    archetype: str = ""
) -> bool:
    """
    Ensamblaje viral definitivo con KARAOKE GLOW, GANCHO SUPERIOR (0-2.5s) y ENCUADRE INTELIGENTE:
    1. Formato C (Nativo Vertical 9:16) Prioritario:
       - Si el vídeo ya es vertical, se escala a pantalla completa nativa sin deformar.
    2. Formato B (Full Frame Cinema con 0% de recorte):
       - EXCLUSIVO para tráilers y comunicados oficiales de Rockstar Games o análisis técnicos clave
         donde recortar arruina los detalles de la pantalla panorámica.
    3. Reencuadre vertical dinámico para clips no oficiales.
    4. Gancho Superior de Contexto (0.0s a 2.5s) y Subtítulos Karaoke Dinámicos con Halo Neón.
    5. Normalización de audio YouTube Shorts (-14 LUFS).
    6. Aceleración nativa VideoToolbox en Apple Silicon e Intel.
    """
    temp_dir = input_video.parent
    base_name = input_video.stem
    width, height = get_video_dimensions(input_video)
    is_already_vertical = (height > width)
    is_vertical = force_short_format or is_already_vertical

    if is_vertical and not is_already_vertical:
        if is_official_content:
            # Modo Cinema Full-Frame (0% Recorte Lateral):
            # Preserva exactamente el 100% del plano horizontal original (1080x608 a 16:9) centrado a y=656
            # con Ambient Blur reactivo para trailers oficiales, comparativas y análisis técnicos.
            fg_w = 1080
            fg_h = 608
            fg_y = 656
            fg_bottom = fg_y + fg_h
            is_cinema_layout = True
            print(f"[*] Modo Cinema Full-Frame (0% recorte lateral): {fg_w}x{fg_h} @ y={fg_y} con Ambient Canvas.")
        else:
            # Modo Encuadre Dinámico Inteligente (Dynamic Smart Crop para gameplay y streamers):
            # Llena con fuerza el área central a 1080x1080, preservando el foco de acción y dejando
            # zonas seguras arriba para el gancho (y=120) y abajo para subtítulos (y=1520).
            fg_w = 1080
            fg_h = 1080
            fg_y = 420
            fg_bottom = fg_y + fg_h
            is_cinema_layout = True
            print(f"[*] Modo Encuadre Dinámico Inteligente: Vídeo adaptado a {fg_w}x{fg_h} @ y={fg_y} (recorte moderado).")
    else:
        # Formato C (Vertical Nativo 9:16):
        fg_w = 1080
        fg_h = 1920
        fg_y = 0
        fg_bottom = 1920
        is_cinema_layout = False
        print(f"[*] Modo Vertical Nativo 9:16: Pantalla completa sin deformación (Vertical: {is_vertical}).")

    # 1. Viñeta y sombras de unión
    vignette_png = temp_dir / f"{base_name}_vignette.png"
    create_subtle_vignette(vignette_png, fg_top=fg_y, fg_bottom=fg_bottom, is_cinema=is_cinema_layout)

    # 2. Gancho textual superior (0 a 2.5s)
    hook_png = None
    if hook_text and is_vertical:
        hook_png = temp_dir / f"{base_name}_hook.png"
        rendered_hook = render_top_hook_headline(hook_text, hook_png)
        if not rendered_hook:
            hook_png = None

    # 2b. Segundo gancho de retención (5.0 a 7.0s) — adaptativo al arquetipo del contenido
    # Solo se aplica en arquetipos donde el viewer necesita un empujón extra para quedarse.
    # En humor/parodia y reacciones el ritmo natural ya retiene; insertar texto lo rompe.
    retention_png = None
    _archetypes_need_retention = {"filtracion_misterio", "analisis_tecnico", "noticia_oficial"}
    if hook_text and is_vertical and archetype in _archetypes_need_retention:
        retention_png = temp_dir / f"{base_name}_retention.png"
        _retention_by_archetype = {
            "filtracion_misterio": ["OJO CON ESTO", "MIRA BIEN", "EL DETALLE CLAVE"],
            "analisis_tecnico": ["ATENCION A ESTO", "COMPARA BIEN", "FIJATE AQUI"],
            "noticia_oficial": ["ESTO ES OFICIAL", "CONFIRMADO", "ATENCION"],
        }
        _phrases = _retention_by_archetype.get(archetype, ["MIRA ESTO"])
        rendered_ret = render_retention_hook(retention_png, text=random.choice(_phrases))
        if not rendered_ret:
            retention_png = None

    # 3. Generación de estados de Karaoke palabra por palabra
    cues = parse_srt_file(srt_subtitles) if srt_subtitles else []
    sub_cues = cues[:120]
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

    # 4. Construcción del comando FFmpeg
    cmd = ["ffmpeg", "-y", "-i", str(input_video)]
    input_idx = 1

    # Audio doblado con Ducking Dinámico Inteligente
    dub_idx = None
    if dub_audio and dub_audio.exists():
        cmd.extend(["-i", str(dub_audio)])
        dub_idx = input_idx
        input_idx += 1

    # Banda Sonora Ambiental Sutil (Synthwave / Vice City Beats) a -22 dB
    ambient_idx = None
    ambient_dir = BASE_DIR / "assets" / "audio" / "ambient_beats"
    if ambient_dir.exists():
        ambient_tracks = [p for p in ambient_dir.glob("*.mp3") if p.is_file()] + [p for p in ambient_dir.glob("*.wav") if p.is_file()]
        if ambient_tracks:
            chosen_ambient = random.choice(ambient_tracks)
            cmd.extend(["-stream_loop", "-1", "-i", str(chosen_ambient)])
            ambient_idx = input_idx
            input_idx += 1
            print(f"[*] Mezclando pista ambiental sutil: {chosen_ambient.name} (-22 dB)")

    # Construcción de la cadena de mezcla de audio (Voice-Over: Inglés atenuado de fondo + Doblaje en Español + Ambiente)
    if dub_idx is not None:
        # Modo Voice-Over Profesional:
        # 1. El audio original en inglés se baja a un nivel base suave (volume=0.12 / -18.4 dB).
        # 2. Cuando habla la voz en español, el sidechain comprime agresivamente (ratio=8, threshold=0.02),
        #    reduciendo la voz inglesa al ~3.5% (-29 dB) para que se perciba sutilmente de fondo sin competir ni molestar.
        if ambient_idx is not None:
            audio_filter = (
                f"[{ambient_idx}:a]volume=0.06[amb];"
                f"[0:a]volume=0.12[orig_base];"
                f"[{dub_idx}:a]asplit=2[sc][voice];"
                f"[orig_base][sc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=300[orig_ducked];"
                f"[orig_ducked][amb]amix=inputs=2:duration=first:normalize=false[bed];"
                f"[bed][voice]amix=inputs=2:duration=first:normalize=false,loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
            )
        else:
            audio_filter = (
                f"[0:a]volume=0.12[orig_base];"
                f"[{dub_idx}:a]asplit=2[sc][voice];"
                f"[orig_base][sc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=300[orig_ducked];"
                f"[orig_ducked][voice]amix=inputs=2:duration=first:normalize=false,loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
            )
    else:
        # Modo Subtítulos Estándar (Shorts Hormozi): Audio original intacto y limpio + ambient beat sutil (-22 dB)
        if ambient_idx is not None:
            audio_filter = (
                f"[{ambient_idx}:a]volume=0.08[amb];"
                f"[0:a][amb]amix=inputs=2:duration=first,loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
            )
        else:
            audio_filter = f"[0:a]loudnorm=I=-14:LRA=7:TP=-1.5[aout]"

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
        if is_official_content:
            # Cinema Full-Frame (0% recorte horizontal): escala preservando 16:9 con ambient glow
            v_base = (
                "[0:v]split[v1][v2];"
                "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:5,eq=brightness=-0.15:contrast=1.05:saturation=1.2[bg];"
                f"[v2]scale=1080:-2,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
                f"[bg][fg]overlay=0:{fg_y}[v_framed]"
            )
        else:
            # Encuadre dinámico inteligente para gameplay y streamer
            v_base = (
                "[0:v]split[v1][v2];"
                "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:5,eq=brightness=-0.12:contrast=1.05:saturation=1.15[bg];"
                f"[v2]scale=-2:{fg_h},crop=1080:{fg_h}:(iw-1080)/2:0,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[fg];"
                f"[bg][fg]overlay=0:{fg_y}[v_framed]"
            )
    elif is_vertical:
        # Formato C (Nativo Vertical 9:16): Pantalla completa sin bandas
        v_base = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[v_framed]"
    else:
        v_base = "[0:v]unsharp=3:3:0.6:3:3:0.0,eq=contrast=1.06:saturation=1.12[v_framed]"
    
    filter_chains.append(v_base)
    current_v = "v_framed"

    # B) Superponer Viñeta sutil y sombras de unión
    filter_chains.append(f"[{current_v}][{vignette_idx}:v]overlay=0:0[v_vignetted]")
    current_v = "v_vignetted"

    # C) Superponer Gancho Superior (0.0 a 2.5s)
    if hook_idx is not None:
        filter_chains.append(f"[{current_v}][{hook_idx}:v]overlay=(W-w)/2:120:enable='between(t,0,2.5)'[v_hooked]")
        current_v = "v_hooked"

    # C2) Superponer segundo gancho de retención (5.0 a 7.0s) — frena el swipe mid-scroll
    if retention_idx is not None:
        filter_chains.append(f"[{current_v}][{retention_idx}:v]overlay=(W-w)/2:220:enable='between(t,5.0,7.0)'[v_retained]")
        current_v = "v_retained"

    # D) Superponer Subtítulos Karaoke palabra por palabra
    # Safe Zone vertical (Instagram Reels / TikTok / YouTube Shorts):
    # En vídeos horizontales adaptados: y=1460 (centrado en el tercio inferior libre, sin tapar interfaz).
    # En vídeos verticales nativos: y=1200.
    sub_y = "1460" if (is_vertical and not is_already_vertical) else ("1200" if is_vertical else "H-h-90")
    for s_idx, (_, start_s, end_s) in enumerate(sub_pngs):
        in_id = sub_inputs_start + s_idx
        next_v = f"v_sub_{s_idx}"
        # Transición limpia al frame gte*lt (evita parpadeo y solapamiento entre estados consecutivos)
        filter_chains.append(
            f"[{current_v}][{in_id}:v]overlay=(W-w)/2:{sub_y}:enable='gte(t,{start_s:.2f})*lt(t,{end_s:.2f})'[{next_v}]"
        )
        current_v = next_v

    filter_chains.append(f"[{current_v}]null[v_body]")

    if audio_filter:
        filter_chains.append(audio_filter)

    cmd.extend(["-filter_complex", ";".join(filter_chains)])
    cmd.extend(["-map", "[v_body]"])
    cmd.extend(["-c:v", FFMPEG_VIDEO_CODEC, "-b:v", FFMPEG_BITRATE])

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
    if hook_png and hook_png.exists():
        try:
            hook_png.unlink()
        except OSError:
            pass

    return True
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List
from .config import TEMP_DIR

def find_tesseract_binary() -> Optional[str]:
    """Localiza el binario de tesseract en las rutas habituales de macOS/Linux."""
    for path in ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"]:
        if Path(path).exists() and Path(path).is_file():
            return path
    which_path = shutil.which("tesseract")
    return which_path

def is_interesting_gameplay_text(text: str) -> bool:
    """
    Filtra si el texto extraído del HUD o subtítulos del juego es interesante y relevante.
    Ignora marcas de agua, nombres de canales, 'subscribe', o números aislados.
    """
    if not text:
        return False
    t = text.lower().strip()
    if len(t) < 8 or len(t) > 120:
        return False
    # Descartar marcas de agua comunes
    junk = ["subscribe", "suscríbete", "like", "follow", "tiktok", "instagram", "youtube", "discord", "watermark", "@"]
    if any(j in t for j in junk):
        return False
    # Debe contener palabras reales, no solo ruido de OCR
    words = [w for w in re.findall(r'[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}', t)]
    return len(words) >= 2

def extract_text_from_frame(frame_path: Path, tesseract_bin: str) -> str:
    """Ejecuta tesseract sobre un fotograma y extrae texto limpio."""
    try:
        cmd = [
            tesseract_bin,
            str(frame_path),
            "stdout",
            "--oem", "1",
            "-l", "spa+eng"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
        return " ".join(lines)
    except Exception:
        return ""

def extract_gameplay_text(
    video_path: Path,
    max_chars: int = 120
) -> Optional[str]:
    """
    Extrae texto del gameplay (subtítulos embebidos en el juego, misiones, diálogos o HUD)
    usando muestreo inteligente de fotogramas vía FFmpeg y OCR.
    Si el texto tiene menos de 120 caracteres y es interesante, lo devuelve para su uso en subtítulos.
    """
    if not video_path.exists():
        return None

    tess = find_tesseract_binary()
    if not tess:
        return None

    # Muestrear 3 puntos clave del vídeo (20%, 50%, 75%)
    frames_dir = TEMP_DIR / f"ocr_{video_path.stem}"
    frames_dir.mkdir(parents=True, exist_ok=True)

    candidates: List[str] = []
    try:
        # Obtener duración del vídeo con ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
        dur = float(probe_res.stdout.strip()) if probe_res.stdout.strip() else 15.0

        sample_times = [max(1.0, dur * 0.2), max(2.0, dur * 0.5), max(3.0, dur * 0.75)]

        for idx, t_sec in enumerate(sample_times):
            frame_png = frames_dir / f"frame_{idx}.png"
            # Extraer la mitad inferior del fotograma (donde suelen residir subtítulos y diálogos del juego)
            # o el fotograma completo optimizado para OCR
            cmd_frame = [
                "ffmpeg", "-y",
                "-ss", f"{t_sec:.2f}",
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", "crop=in_w:in_h*0.45:0:in_h*0.55",  # Recorte inferior 45%
                str(frame_png)
            ]
            subprocess.run(cmd_frame, capture_output=True, timeout=10)
            if frame_png.exists():
                raw_text = extract_text_from_frame(frame_png, tess)
                clean_text = " ".join(raw_text.split())
                if is_interesting_gameplay_text(clean_text) and len(clean_text) <= max_chars:
                    candidates.append(clean_text)

        if candidates:
            # Seleccionar el candidato más completo o representativo
            candidates.sort(key=lambda s: len(s), reverse=True)
            return candidates[0]

    except Exception:
        pass
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)

    return None

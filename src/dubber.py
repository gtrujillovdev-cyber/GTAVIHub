import re
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
import edge_tts
from .config import DEFAULT_TTS_VOICE
from .translator import purge_audio_descriptors
from .downloader import deroll_and_clean_srt_content

def deduplicate_phrase_repetitions(text: str) -> str:
    """
    Elimina repeticiones contiguas de frases o cláusulas (tartamudeo residual por ASR):
    Ej: 'parece que quien está detrás de, parece que quien está detrás de la cuenta'
    -> 'parece que quien está detrás de la cuenta'
    """
    words = text.split()
    if len(words) < 4:
        return text

    i = 0
    cleaned_words = []
    while i < len(words):
        matched = False
        # Buscar repeticiones de bloques contiguos de 8 hasta 2 palabras
        for chunk_len in range(min(8, (len(words) - i) // 2), 1, -1):
            chunk1 = [w.lower().strip('.,!?;:"\'') for w in words[i : i + chunk_len]]
            chunk2 = [w.lower().strip('.,!?;:"\'') for w in words[i + chunk_len : i + 2 * chunk_len]]
            if chunk1 == chunk2:
                matched = True
                i += chunk_len
                break
        if not matched:
            cleaned_words.append(words[i])
            i += 1

    return " ".join(cleaned_words)

def parse_first_cue_start(srt_path: Path) -> float:
    """Detecta el segundo exacto en el que empieza a hablar el primer personaje en el SRT."""
    if not srt_path.exists():
        return 0.0
    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "-->" in line:
                    start_str = line.split("-->")[0].strip()
                    # Parse HH:MM:SS,mmm o MM:SS,mmm
                    clean_str = start_str.replace(",", ".")
                    parts = clean_str.split(":")
                    if len(parts) == 3:
                        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    elif len(parts) == 2:
                        return float(parts[0]) * 60 + float(parts[1])
    except Exception:
        pass
    return 0.0

def extract_text_from_srt(srt_path: Path) -> str:
    """Extrae todo el texto limpio y desduplicado de un archivo SRT eliminando tartamudeo y rolling buffers."""
    if not srt_path.exists():
        return ""
    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 1. Purgar rolling buffer a nivel de bloques SRT
    derolled = deroll_and_clean_srt_content(content)

    blocks = [b.strip() for b in derolled.strip().split("\n\n") if b.strip()]
    clean_lines = []
    seen_history = []

    for b in blocks:
        lines = b.split("\n")
        if len(lines) < 2:
            continue
        text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        for l in text_lines:
            sanitized = purge_audio_descriptors(l.strip())
            if not sanitized:
                continue
            l_norm = " ".join(sanitized.lower().strip('.,!?;:"\'').split())
            if any(l_norm == prev for prev in seen_history[-4:]):
                continue
            clean_lines.append(sanitized)
            seen_history.append(l_norm)

    raw_joined = " ".join(clean_lines)
    # 2. Purgar cualquier repetición de n-gramas residual (tartamudeo)
    return deduplicate_phrase_repetitions(raw_joined)

async def _synthesize_async(text: str, output_audio: Path, voice: str = DEFAULT_TTS_VOICE):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_audio))

def generate_voiceover(srt_path: Path, output_audio_path: Path, voice: str = DEFAULT_TTS_VOICE) -> bool:
    """
    Sintetiza la pista de voz en español usando Edge-TTS (0 recursos locales)
    y sincroniza el arranque al milisegundo exacto de la primera frase del SRT.
    """
    text = extract_text_from_srt(srt_path)
    if not text:
        print("[!] No se encontró texto para sintetizar voz.")
        return False

    first_start = parse_first_cue_start(srt_path)
    raw_tts_path = output_audio_path.with_name(f"{output_audio_path.stem}_raw.mp3")

    print(f"[*] Sintetizando locución en español con voz '{voice}'...")
    try:
        asyncio.run(_synthesize_async(text, raw_tts_path, voice))
        
        # Si la primera locución empieza tras un silencio en el vídeo original (ej. intro),
        # retrasamos el audio con adelay para mantener sincronía perfecta con los labios/acción.
        if first_start > 0.15:
            delay_ms = int(first_start * 1000)
            print(f"[*] Sincronizando inicio de doblaje: insertando delay inicial de {first_start:.2f}s ({delay_ms}ms)...")
            cmd_delay = [
                "ffmpeg", "-y",
                "-i", str(raw_tts_path),
                "-af", f"adelay={delay_ms}|{delay_ms}",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                str(output_audio_path)
            ]
            res = subprocess.run(cmd_delay, capture_output=True)
            if res.returncode == 0 and output_audio_path.exists():
                raw_tts_path.unlink(missing_ok=True)
            else:
                raw_tts_path.rename(output_audio_path)
        else:
            raw_tts_path.rename(output_audio_path)

        print(f"[✓] Audio de voz sincronizado -> {output_audio_path.name}")
        return True
    except Exception as e:
        print(f"[!] Error generando TTS: {e}")
        if raw_tts_path.exists():
            raw_tts_path.unlink(missing_ok=True)
        return False

import re
import asyncio
from pathlib import Path
from typing import Optional
import edge_tts
from .config import DEFAULT_TTS_VOICE

def extract_text_from_srt(srt_path: Path) -> str:
    """Extrae todo el texto limpio de un archivo SRT eliminando numeración y tiempos."""
    if not srt_path.exists():
        return ""
    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    clean_lines = []
    for line in lines:
        line_str = line.strip()
        # Saltar números de bloque o líneas de tiempo
        if re.match(r"^\d+$", line_str) or "-->" in line_str:
            continue
        if line_str:
            clean_lines.append(line_str)

    return " ".join(clean_lines)

async def _synthesize_async(text: str, output_audio: Path, voice: str = DEFAULT_TTS_VOICE):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_audio))

def generate_voiceover(srt_path: Path, output_audio_path: Path, voice: str = DEFAULT_TTS_VOICE) -> bool:
    """Sintetiza la pista de voz en español usando Edge-TTS (0 recursos locales)."""
    text = extract_text_from_srt(srt_path)
    if not text:
        print("[!] No se encontró texto para sintetizar voz.")
        return False

    print(f"[*] Sintetizando locución en español con voz '{voice}'...")
    try:
        asyncio.run(_synthesize_async(text, output_audio_path, voice))
        print(f"[✓] Audio de voz generado -> {output_audio_path.name}")
        return True
    except Exception as e:
        print(f"[!] Error generando TTS: {e}")
        return False

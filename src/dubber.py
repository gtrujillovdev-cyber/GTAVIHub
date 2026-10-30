import re
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
import edge_tts
from .config import DEFAULT_TTS_VOICE

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

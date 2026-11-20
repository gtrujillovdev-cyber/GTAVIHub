import os
import re
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
import edge_tts
from .config import DEFAULT_TTS_VOICE
from .translator import purge_audio_descriptors
from .downloader import deroll_and_clean_srt_content

VOICE_ENHANCER_CHAIN = (
    "highpass=f=80,afftdn=nf=-25,"
    "equalizer=f=180:width_type=o:width=1.5:g=3,"
    "compand=attacks=0.02:decays=0.15:points=-80/-80|-20/-12|0/-3,"
    "loudnorm=I=-14:TP=-1.5:LRA=11"
)

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

async def _synthesize_async(
    text: str,
    output_audio: Path,
    voice: str = DEFAULT_TTS_VOICE,
    rate: str = "+14%",
    pitch: str = "+2Hz"
):
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(str(output_audio))
    except Exception:
        # Fallback seguro sin pitch si una voz concreta de Edge-TTS rechaza el parámetro
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(output_audio))

def _probe_audio_duration(audio_path: Path) -> float:
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True, timeout=8
        )
        return float(res.stdout.strip()) if res.stdout.strip() else 0.0
    except Exception:
        return 0.0


def get_word_timestamps_groq(audio_path: Path, language: str = "es") -> List[Dict[str, Any]]:
    """
    Obtiene timestamps exactos palabra por palabra vía Groq Whisper Free Tier ($0).
    Falla de forma segura devolviendo [] si falta GROQ_API_KEY, hay 429 o error de red,
    permitiendo que el pipeline continúe con calculate_word_timing() sin detenerse.
    """
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key or not audio_path or not Path(audio_path).exists():
        return []

    try:
        import requests
        with open(audio_path, "rb") as f:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (Path(audio_path).name, f, "audio/mpeg")},
                data={
                    "model": os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"),
                    "language": language,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                },
                timeout=12,
            )
        if resp.status_code != 200:
            print(f"[!] [Groq Whisper] HTTP {resp.status_code}: usando fallback determinista.")
            return []
        payload = resp.json()
        raw_words = payload.get("words") or []
        cleaned: List[Dict[str, Any]] = []
        for w in raw_words:
            word_txt = (w.get("word") or "").strip()
            if not word_txt:
                continue
            start_s = float(w.get("start", 0.0))
            end_s = max(start_s + 0.08, float(w.get("end", start_s + 0.25)))
            cleaned.append({"word": word_txt, "start": round(start_s, 3), "end": round(end_s, 3)})
        if cleaned:
            print(f"[✓] [Groq Whisper] {len(cleaned)} timestamps palabra-por-palabra obtenidos ($0).")
        return cleaned
    except Exception as e:
        print(f"[!] [Groq Whisper] Fallback determinista activado ({e}).")
        return []


def generate_voiceover(
    srt_path: Path,
    output_audio_path: Path,
    voice: str = DEFAULT_TTS_VOICE,
    max_duration: Optional[float] = None
) -> bool:
    """
    Sintetiza la pista de voz en español usando Edge-TTS (0 recursos locales)
    con ritmo ágil de Shorts (+14%, +2Hz), mejora acústica FFmpeg y sincronía limpia.
    """
    text = extract_text_from_srt(srt_path)
    if not text:
        print("[!] No se encontró texto para sintetizar voz.")
        return False

    first_start = parse_first_cue_start(srt_path)
    if first_start > 12.0:
        print(f"[!] [Dubber] El primer subtítulo aparece demasiado tarde ({first_start:.1f}s > 12s). Abortando doblaje desfasado.")
        return False
    raw_tts_path = output_audio_path.with_name(f"{output_audio_path.stem}_raw.mp3")

    tts_rate = os.getenv("TTS_RATE", "+14%")
    tts_pitch = os.getenv("TTS_PITCH", "+2Hz")
    enable_enhancer = os.getenv("ENABLE_VOICE_ENHANCER", "true").lower() in ("true", "1", "yes")

    print(f"[*] Sintetizando locución en español con voz '{voice}' (ritmo {tts_rate}, tono {tts_pitch})...")
    try:
        asyncio.run(_synthesize_async(text, raw_tts_path, voice, rate=tts_rate, pitch=tts_pitch))

        filters = []
        raw_dur = _probe_audio_duration(raw_tts_path)
        effective_delay = first_start if first_start > 0.15 else 0.0

        # Ajustar ligeramente el tempo si la locución excede la duración del clip (evita cortes al final)
        if max_duration and raw_dur > 1.0:
            available = max(2.0, float(max_duration) - 0.55 - effective_delay)
            if raw_dur > available:
                speed = min(1.35, max(1.02, raw_dur / available))
                filters.append(f"atempo={speed:.3f}")
                print(f"[*] Ajustando tempo de voz ({raw_dur:.1f}s -> {available:.1f}s, x{speed:.2f}) para encajar sin cortes.")

        if effective_delay > 0.15:
            delay_ms = int(effective_delay * 1000)
            filters.append(f"adelay={delay_ms}|{delay_ms}")
            print(f"[*] Sincronizando inicio de doblaje: delay inicial {effective_delay:.2f}s ({delay_ms}ms)...")

        if enable_enhancer:
            filters.append(VOICE_ENHANCER_CHAIN)

        if filters:
            cmd_fx = [
                "ffmpeg", "-y",
                "-i", str(raw_tts_path),
                "-af", ",".join(filters),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                str(output_audio_path)
            ]
            res = subprocess.run(cmd_fx, capture_output=True)
            if res.returncode == 0 and output_audio_path.exists():
                raw_tts_path.unlink(missing_ok=True)
            else:
                # Fallback seguro sin enhancer si algún filtro fallase en el host
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

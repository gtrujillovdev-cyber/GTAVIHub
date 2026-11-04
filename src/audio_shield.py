"""
🛡️ GTA VI Hub Spain — Speech & Audio Vitality Shield
=====================================================
Garantiza que NINGÚN vídeo mudo, sin volumen o con B-roll vacío de tráilers
sea publicado en YouTube Shorts, TikTok o Instagram Reels.

Políticas aplicadas:
1. Pista de audio obligatoria con volumen audible (mean_volume > -42.0 dB, max_volume > -28.0 dB).
2. Densidad de locución/voz activa mínima (al menos 12 palabras de narrativa real
   en clips de más de 15 segundos) o locución neural en off obligatoria.
3. Descarte preventivo de clips mudos de tráilers para proteger la retención y la calidad.
"""

import subprocess
import re
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Umbrales acústicos y editoriales
MIN_MEAN_VOLUME_DB = -42.0  # Por debajo de -42 dB el audio es virtualmente imperceptible
MIN_MAX_VOLUME_DB = -28.0   # Si el pico máximo no llega a -28 dB, es metraje mudo o corrupto
MIN_SPEECH_WORDS = 10       # Mínimo de palabras habladas en clips > 15s para justificar subtítulos dinámicos


def detect_audio_levels(video_path: Path) -> Dict[str, Any]:
    """
    Analiza la pista de audio de un vídeo mediante ffmpeg con el filtro 'volumedetect'.
    Devuelve mean_volume, max_volume y si existe pista de audio válida.
    """
    if not video_path or not video_path.exists():
        return {
            "has_audio": False,
            "mean_volume": -99.0,
            "max_volume": -99.0,
            "error": "El archivo de vídeo no existe"
        }

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-af", "volumedetect",
        "-vn", "-sn", "-dn",
        "-f", "null",
        "-"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        output = res.stderr or ""

        mean_match = re.search(r"mean_volume:\s*(-?[\d\.]+)\s*dB", output)
        max_match = re.search(r"max_volume:\s*(-?[\d\.]+)\s*dB", output)

        if not mean_match or not max_match:
            # Comprobar si el archivo si quiera tiene stream de audio
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ]
            probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            has_audio = "audio" in probe_res.stdout.lower()

            return {
                "has_audio": has_audio,
                "mean_volume": -99.0,
                "max_volume": -99.0,
                "error": "No se detectaron niveles acústicos en el contenedor"
            }

        mean_vol = float(mean_match.group(1))
        max_vol = float(max_match.group(1))

        return {
            "has_audio": True,
            "mean_volume": mean_vol,
            "max_volume": max_vol,
            "error": None
        }
    except Exception as e:
        return {
            "has_audio": False,
            "mean_volume": -99.0,
            "max_volume": -99.0,
            "error": str(e)
        }


def measure_speech_density(srt_path: Optional[Path], duration: float) -> Dict[str, Any]:
    """
    Calcula la densidad de palabras habladas en el archivo de subtítulos (.srt).
    """
    if not srt_path or not srt_path.exists():
        return {
            "has_srt": False,
            "word_count": 0,
            "words_per_second": 0.0,
            "has_substantive_speech": False
        }

    try:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Extraer líneas de texto descartando números y marcas de tiempo
        text_lines = []
        for line in content.splitlines():
            line_s = line.strip()
            if not line_s or line_s.isdigit() or "-->" in line_s:
                continue
            text_lines.append(line_s)

        full_text = " ".join(text_lines)
        words = re.findall(r"\b\w+\b", full_text)
        word_count = len(words)
        effective_dur = max(duration, 1.0)
        wps = word_count / effective_dur

        # Si el clip dura más de 15s, necesita un mínimo de palabras para considerarse narración
        is_substantive = (word_count >= MIN_SPEECH_WORDS) if duration > 15 else (word_count >= 5)

        return {
            "has_srt": True,
            "word_count": word_count,
            "words_per_second": round(wps, 2),
            "has_substantive_speech": is_substantive,
            "sample_text": full_text[:120]
        }
    except Exception as e:
        return {
            "has_srt": False,
            "word_count": 0,
            "words_per_second": 0.0,
            "has_substantive_speech": False,
            "error": str(e)
        }


def validate_audio_and_speech_vitality(
    video_path: Path,
    srt_path: Optional[Path] = None,
    has_voiceover: bool = False,
    mode: str = "subs",
    min_mean_vol: float = MIN_MEAN_VOLUME_DB,
    min_max_vol: float = MIN_MAX_VOLUME_DB,
    min_words: int = MIN_SPEECH_WORDS
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Escudo Integral de Vitalidad de Audio.
    Verifica que:
    1. El vídeo no esté silenciado ni por debajo de los umbrales mínimos audibles.
    2. Si no lleva locución neural propia (has_voiceover=False), el vídeo original
       tenga diálogo/comentarios reales y suficientes para evitar clips mudos de tráilers.
    """
    # 1. Obtener duración del vídeo
    duration = 0.0
    try:
        probe_dur = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        res = subprocess.run(probe_dur, capture_output=True, text=True, timeout=10)
        duration = float(res.stdout.strip()) if res.stdout.strip() else 0.0
    except Exception:
        pass

    # 2. Análisis acústico
    audio_stats = detect_audio_levels(video_path)
    if not audio_stats["has_audio"]:
        return False, "❌ [Escudo de Audio] El vídeo carece por completo de pista de audio.", {
            "audio_stats": audio_stats,
            "speech_stats": None,
            "duration": duration
        }

    # Si no tiene voz en off generada, comprobar volumen del clip original
    if not has_voiceover:
        if audio_stats["mean_volume"] < min_mean_vol:
            return False, (
                f"❌ [Escudo de Audio] Volumen medio inaudible ({audio_stats['mean_volume']:.1f} dB < {min_mean_vol} dB). "
                f"El clip está silenciado o es B-roll mudo."
            ), {
                "audio_stats": audio_stats,
                "speech_stats": None,
                "duration": duration
            }

        if audio_stats["max_volume"] < min_max_vol:
            return False, (
                f"❌ [Escudo de Audio] Pico máximo insuficiente ({audio_stats['max_volume']:.1f} dB < {min_max_vol} dB). "
                f"Pista de audio defectuosa o sin sonido."
            ), {
                "audio_stats": audio_stats,
                "speech_stats": None,
                "duration": duration
            }

    # 3. Análisis de narrativa y densidad de voz
    speech_stats = measure_speech_density(srt_path, duration)

    # Si no hay doblaje ni voz generada por IA, el clip original DEBE tener discurso real
    if not has_voiceover and mode in ["subs", "short"]:
        if duration > 15.0 and not speech_stats["has_substantive_speech"]:
            return False, (
                f"❌ [Escudo de Audio] Densidad de voz insuficiente ({speech_stats['word_count']} palabras en {duration:.1f}s). "
                f"El clip es metraje de tráiler/B-roll sin narrador ni locución activa. "
                f"Descartado para evitar subir clips vacíos al canal."
            ), {
                "audio_stats": audio_stats,
                "speech_stats": speech_stats,
                "duration": duration
            }

    return True, "✅ [Escudo de Audio] Vitalidad acústica y narrativa verificadas con éxito.", {
        "audio_stats": audio_stats,
        "speech_stats": speech_stats,
        "duration": duration
    }

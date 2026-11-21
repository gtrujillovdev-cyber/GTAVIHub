"""
Stem Separator — Blindaje Anti-Copyright con separacion de pistas de audio.

Usa Demucs (htdemucs) para separar vocals, drums, bass, other del audio.
Permite atenuar/eliminar musica de radio de GTA 6 para evitar Content ID,
preservando voces y SFX.

Incluye fallback FFmpeg ligero para cuando Demucs no esta disponible
o GaTDSEQ esta activo (CPU limitada).
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional

from .config import TEMP_DIR, is_quant_busy

ENABLE_STEM_SEPARATION = os.getenv("ENABLE_STEM_SEPARATION", "false").lower() in ("1", "true", "yes")
DEMUCS_MODEL = os.getenv("DEMUCS_MODEL", "htdemucs")
MUSIC_ATTENUATION_DB = float(os.getenv("MUSIC_ATTENUATION_DB", "-18.0"))


def is_demucs_available() -> bool:
    """Verifica si Demucs esta instalado y funcional."""
    try:
        res = subprocess.run(
            ["python3", "-m", "demucs", "--help"],
            capture_output=True, timeout=10
        )
        return res.returncode == 0
    except Exception:
        return False


def separate_stems(
    audio_path: Path,
    output_dir: Optional[Path] = None,
    model: Optional[str] = None
) -> Optional[Dict[str, Path]]:
    """
    Separa un archivo de audio en 4 stems: vocals, drums, bass, other.
    Retorna dict con paths a cada stem, o None si falla.
    """
    if not audio_path.exists():
        return None

    out_dir = output_dir or (TEMP_DIR / "stems")
    out_dir.mkdir(parents=True, exist_ok=True)
    effective_model = model or DEMUCS_MODEL

    try:
        cmd = [
            "python3", "-m", "demucs",
            "--two-stems", "vocals",  # Solo separar vocals vs accompaniment (mas rapido)
            "-n", effective_model,
            "--out", str(out_dir),
            str(audio_path)
        ]
        print(f"[Stem Separator] Ejecutando Demucs ({effective_model})...")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # 10 min max

        if res.returncode != 0:
            print(f"[Stem Separator] Demucs fallo: {res.stderr[:200]}")
            return None

        # Demucs output: out_dir/model_name/audio_stem/vocals.wav, no_vocals.wav
        stem_base = out_dir / effective_model / audio_path.stem
        stems = {}
        for stem_name in ("vocals", "no_vocals"):
            stem_path = stem_base / f"{stem_name}.wav"
            if stem_path.exists():
                stems[stem_name] = stem_path

        if "vocals" not in stems:
            print("[Stem Separator] No se encontro stem de vocals.")
            return None

        print(f"[Stem Separator] Separacion completada: {list(stems.keys())}")
        return stems

    except subprocess.TimeoutExpired:
        print("[Stem Separator] Timeout (>10 min). Abortando Demucs.")
        return None
    except Exception as e:
        print(f"[Stem Separator] Error: {e}")
        return None


def remix_safe_audio(
    stems: Dict[str, Path],
    output_path: Path,
    music_attenuation_db: Optional[float] = None,
    replacement_beat_path: Optional[Path] = None
) -> bool:
    """
    Mezcla stems preservando vocals+sfx y atenuando musica.
    Opcionalmente inyecta un beat libre de derechos.
    """
    att_db = music_attenuation_db if music_attenuation_db is not None else MUSIC_ATTENUATION_DB
    vocals_path = stems.get("vocals")
    music_path = stems.get("no_vocals")

    if not vocals_path or not vocals_path.exists():
        return False

    filter_parts = []
    inputs = ["-i", str(vocals_path)]
    idx = 1

    if music_path and music_path.exists():
        inputs.extend(["-i", str(music_path)])
        filter_parts.append(f"[{idx}:a]volume={att_db}dB[music_att]")
        mix_inputs = f"[0:a][music_att]"
        idx += 1
    else:
        mix_inputs = "[0:a]"

    if replacement_beat_path and replacement_beat_path.exists():
        inputs.extend(["-i", str(replacement_beat_path)])
        filter_parts.append(f"[{idx}:a]volume=-12dB[beat]")
        if music_path and music_path.exists():
            mix_inputs = f"[0:a][music_att][beat]"
            mix_count = 3
        else:
            mix_inputs = f"[0:a][beat]"
            mix_count = 2
        idx += 1
    else:
        mix_count = 2 if (music_path and music_path.exists()) else 1

    if mix_count > 1:
        filter_parts.append(f"{mix_inputs}amix=inputs={mix_count}:duration=first[out]")
        filter_graph = ";".join(filter_parts)
        output_map = ["-map", "[out]"]
    else:
        filter_graph = ""
        output_map = ["-map", "0:a"]

    cmd = ["ffmpeg", "-y"] + inputs
    if filter_graph:
        cmd.extend(["-filter_complex", filter_graph])
    cmd.extend(output_map)
    cmd.extend(["-acodec", "aac", "-b:a", "192k", str(output_path)])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return res.returncode == 0 and output_path.exists()
    except Exception as e:
        print(f"[Stem Separator] Error en remix: {e}")
        return False


def apply_ffmpeg_music_filter(
    video_path: Path,
    output_audio_path: Path,
    preserve_voice_band: bool = True
) -> bool:
    """
    Fallback ligero: atenua frecuencias musicales (100-500Hz y 2k-16kHz)
    preservando la banda de voz humana (500Hz-2kHz) mediante filtros FFmpeg.
    No requiere Demucs. Funciona incluso con GaTDSEQ activo.
    """
    if preserve_voice_band:
        # Atenuar musica (bandas fuera de voz humana) preservando speech
        af_filter = (
            "highpass=f=80,"
            "equalizer=f=200:t=h:width=200:g=-8,"     # Atenuar bajos/bass
            "equalizer=f=4000:t=h:width=4000:g=-6,"    # Atenuar agudos/musica
            "equalizer=f=8000:t=h:width=6000:g=-10,"   # Atenuar alta frecuencia
            "dynaudnorm=p=0.9:m=10"                     # Normalizar
        )
    else:
        af_filter = "lowpass=f=3000,highpass=f=200,volume=0.4"

    cmd = [
        "ffmpeg", "-y", "-threads", "1",
        "-i", str(video_path),
        "-vn", "-af", af_filter,
        "-acodec", "aac", "-b:a", "128k",
        str(output_audio_path)
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return res.returncode == 0 and output_audio_path.exists()
    except Exception as e:
        print(f"[Stem Separator] Error en filtro FFmpeg: {e}")
        return False


def process_audio_stems(
    video_path: Path,
    video_id: str,
    force_ffmpeg_fallback: bool = False
) -> Optional[Path]:
    """
    Punto de entrada principal. Decide entre Demucs y fallback FFmpeg
    segun disponibilidad de hardware y feature flags.

    Retorna path al audio procesado, o None si no se aplica.
    """
    if not ENABLE_STEM_SEPARATION:
        return None

    output_audio = TEMP_DIR / f"{video_id}_stems_safe.m4a"

    # Si GaTDSEQ activo o se fuerza fallback, usar filtro FFmpeg ligero
    if force_ffmpeg_fallback or is_quant_busy() or not is_demucs_available():
        reason = (
            "GaTDSEQ activo" if is_quant_busy()
            else ("forzado" if force_ffmpeg_fallback else "Demucs no disponible")
        )
        print(f"[Stem Separator] Usando fallback FFmpeg ({reason})...")
        if apply_ffmpeg_music_filter(video_path, output_audio):
            return output_audio
        return None

    # Extraer audio del video
    temp_audio = TEMP_DIR / f"{video_id}_raw_audio.wav"
    try:
        cmd = [
            "ffmpeg", "-y", "-threads", "2",
            "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            str(temp_audio)
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        if not temp_audio.exists():
            return None
    except Exception:
        return None

    # Separar con Demucs
    stems = separate_stems(temp_audio)

    # Limpiar wav temporal
    temp_audio.unlink(missing_ok=True)

    if not stems:
        print("[Stem Separator] Demucs fallo, usando fallback FFmpeg...")
        if apply_ffmpeg_music_filter(video_path, output_audio):
            return output_audio
        return None

    # Remix con musica atenuada
    if remix_safe_audio(stems, output_audio):
        # Limpiar stems temporales
        stems_dir = TEMP_DIR / "stems"
        if stems_dir.exists():
            shutil.rmtree(stems_dir, ignore_errors=True)
        return output_audio

    return None

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# Monetización & Contacto Comercial
BUSINESS_EMAIL = os.getenv("BUSINESS_EMAIL", "gabtru@hotmail.com")
MONETIZATION_AFFILIATE_URL = os.getenv("MONETIZATION_AFFILIATE_URL", "https://linktr.ee/gtavihubspain")
ENABLE_AFFILIATE_CTAS = os.getenv("ENABLE_AFFILIATE_CTAS", "false").lower() in ("1", "true", "yes")
AFFILIATE_CTA_TIKTOK = os.getenv("AFFILIATE_CTA_TIKTOK", "🎮 Saldo PSN/Xbox con descuento & reserva de GTA 6 en link de bio ⬇️")
AFFILIATE_CTA_INSTAGRAM = os.getenv("AFFILIATE_CTA_INSTAGRAM", "🔥 Consigue saldo PSN/Xbox con descuento y hardware para GTA 6 en el link de la bio 🔗")
ENABLE_AUTO_PINNED_COMMENT = os.getenv("ENABLE_AUTO_PINNED_COMMENT", "true").lower() in ("1", "true", "yes")

CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output")).resolve()
TEMP_DIR = Path(os.getenv("TEMP_DIR", BASE_DIR / "temp")).resolve()
LOGS_DIR = BASE_DIR / "logs"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Standard paths (con soporte transparente y retrocompatible)
CHANNELS_FILE = CONFIG_DIR / "channels.json" if (CONFIG_DIR / "channels.json").exists() else (BASE_DIR / "channels.json")
PROCESSED_FILE = DATA_DIR / "processed.json" if (DATA_DIR / "processed.json").exists() else (BASE_DIR / "processed.json")

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Defaults & Duración Dinámica Orgánica (Anti-Fingerprinting)
MAX_VIDEOS_PER_RUN = int(os.getenv("MAX_VIDEOS_PER_RUN", "2"))
DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "es-ES-AlvaroNeural")
AUTO_DUB_ENGLISH = os.getenv("AUTO_DUB_ENGLISH", "false").lower() in ("1", "true", "yes")
SHORT_MIN_DURATION = int(os.getenv("SHORT_MIN_DURATION", "26"))
SHORT_MAX_DURATION = int(os.getenv("SHORT_MAX_DURATION", "52"))
SHORT_TARGET_DURATION = int(os.getenv("SHORT_TARGET_DURATION", "38"))

# FFmpeg Hardware Acceleration (VideoToolbox para Apple Silicon e Intel)
FFMPEG_VIDEO_CODEC = "h264_videotoolbox"
FFMPEG_BITRATE = os.getenv("FFMPEG_BITRATE", "10M")

# Protocolo de Coexistencia de Hardware (GaTDSEQ & Background Friendliness)
FFMPEG_THREADS = int(os.getenv("FFMPEG_THREADS", "2"))
CHECK_QUANT_BUSY = os.getenv("CHECK_QUANT_BUSY", "true").lower() in ("1", "true", "yes")

# Fase de Shorts de Gameplay (Apertura automática a partir del 19 de Noviembre)
GAMEPLAY_RELEASE_DATE = os.getenv("GAMEPLAY_RELEASE_DATE", "2026-11-19")
FORCE_ENABLE_GAMEPLAY = os.getenv("FORCE_ENABLE_GAMEPLAY", "false").lower() in ("1", "true", "yes")

# Modo Ametralladora (Launch Day Engine: Máxima cadencia y aprovechamiento al límite)
LAUNCH_MAX_VIDEOS_PER_RUN = int(os.getenv("LAUNCH_MAX_VIDEOS_PER_RUN", "3"))

def is_gameplay_enabled() -> bool:
    """Verifica si la fase de Shorts de Gameplay está activa (automáticamente desde el 19 de Noviembre o vía override)."""
    if FORCE_ENABLE_GAMEPLAY:
        return True
    try:
        from datetime import datetime
        target = datetime.fromisoformat(GAMEPLAY_RELEASE_DATE)
        return datetime.now() >= target
    except Exception:
        return False

def get_max_videos_per_run() -> int:
    """En fase de lanzamiento pasa a Modo Ametralladora (3 vídeos por tanda en vez de 1-2)."""
    if is_gameplay_enabled():
        return LAUNCH_MAX_VIDEOS_PER_RUN
    return MAX_VIDEOS_PER_RUN

def get_ffmpeg_threads() -> int:
    """Hilos de FFmpeg: 1 si GaTDSEQ esta activo (Modo Cortesia), si no FFMPEG_THREADS (2)."""
    return 1 if is_quant_busy() else FFMPEG_THREADS


def is_quant_busy() -> bool:
    """Detecta si hay un proceso cuantitativo de GaTDSEQ ejecutándose en el equipo."""
    if not CHECK_QUANT_BUSY:
        return False
    try:
        import subprocess
        res = subprocess.run(
            ["pgrep", "-f", "optimize_fleet.py|run_backtest.py|xgboost_gate.py"],
            capture_output=True,
            text=True
        )
        my_pid = str(os.getpid())
        pids = [p for p in res.stdout.strip().split() if p and p != my_pid]
        return len(pids) > 0
    except Exception:
        return False

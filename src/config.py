import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# Monetización & Contacto Comercial
BUSINESS_EMAIL = os.getenv("BUSINESS_EMAIL", "gabtru@hotmail.com")
MONETIZATION_AFFILIATE_URL = os.getenv("MONETIZATION_AFFILIATE_URL", "https://linktr.ee/gtavihubextra")
ENABLE_AFFILIATE_CTAS = os.getenv("ENABLE_AFFILIATE_CTAS", "false").lower() in ("1", "true", "yes")
AFFILIATE_CTA_TIKTOK = os.getenv("AFFILIATE_CTA_TIKTOK", "🎮 Saldo PSN/Xbox con descuento & reserva de GTA 6 en link de bio ⬇️")
AFFILIATE_CTA_INSTAGRAM = os.getenv("AFFILIATE_CTA_INSTAGRAM", "🔥 Consigue saldo PSN/Xbox con descuento y hardware para GTA 6 en el link de la bio 🔗")
ENABLE_AUTO_PINNED_COMMENT = os.getenv("ENABLE_AUTO_PINNED_COMMENT", "true").lower() in ("1", "true", "yes")

def _resolve_project_path(raw: str, default_subdir: str) -> Path:
    """Resuelve rutas relativas respecto a BASE_DIR (inmune al cwd de cron/watchdog)."""
    if not raw:
        return (BASE_DIR / default_subdir).resolve()
    p = Path(raw).expanduser()
    return p.resolve() if p.is_absolute() else (BASE_DIR / p).resolve()

CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = _resolve_project_path(os.getenv("OUTPUT_DIR", ""), "output")
TEMP_DIR = _resolve_project_path(os.getenv("TEMP_DIR", ""), "temp")
LOGS_DIR = BASE_DIR / "logs"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Standard paths (con soporte transparente y retrocompatible)
CHANNELS_FILE = CONFIG_DIR / "channels.json" if (CONFIG_DIR / "channels.json").exists() else (BASE_DIR / "channels.json")
PROCESSED_FILE = DATA_DIR / "processed.json" if (DATA_DIR / "processed.json").exists() else (BASE_DIR / "processed.json")

# Gemini / Hydrogen API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
_raw_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-lite-latest,gemini-flash-latest,gemini-3.5-flash-lite,gemini-3.5-flash,gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = [m.strip() for m in _raw_fallbacks.split(",") if m.strip()]

# Defaults & Duración Orgánica Nativa (Shorts nativos 100% íntegros, sin cortes arbitrarios)
MAX_VIDEOS_PER_RUN = int(os.getenv("MAX_VIDEOS_PER_RUN", "1"))
MAX_DAILY_UPLOADS = int(os.getenv("MAX_DAILY_UPLOADS", "2"))
DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "es-ES-AlvaroNeural")
AUTO_DUB_ENGLISH = os.getenv("AUTO_DUB_ENGLISH", "true").lower() in ("1", "true", "yes")
SHORT_MIN_DURATION = int(os.getenv("SHORT_MIN_DURATION", "10"))
GAMEPLAY_MIN_DURATION = int(os.getenv("GAMEPLAY_MIN_DURATION", "12"))
SHORT_MAX_DURATION = int(os.getenv("SHORT_MAX_DURATION", "58"))
SHORT_TARGET_DURATION = int(os.getenv("SHORT_TARGET_DURATION", "28"))

# Política nocturna para lanzamiento: por defecto Co-Pilot sigue exigiendo confirmación manual
LAUNCH_AUTOPILOT = os.getenv("LAUNCH_AUTOPILOT", "false").lower() in ("1", "true", "yes")
LAUNCH_AUTOPILOT_MIN_SCORE = int(os.getenv("LAUNCH_AUTOPILOT_MIN_SCORE", "65"))

# Ventana de veto en Co-Pilot: si > 0, auto-publica tras N segundos si el operador no veta en Telegram
COPILOT_AUTO_APPROVE_SECONDS = int(os.getenv("COPILOT_AUTO_APPROVE_SECONDS", "60"))

# FFmpeg Hardware Acceleration (VideoToolbox para Apple Silicon e Intel)
FFMPEG_VIDEO_CODEC = "h264_videotoolbox"

# Master 4K Ultra HD para Shorts (2160x3840) con perfil VP9/AV1 en YouTube
ENABLE_4K_SHORTS = os.getenv("ENABLE_4K_SHORTS", "true").lower() in ("1", "true", "yes")
CANVAS_WIDTH = 2160 if ENABLE_4K_SHORTS else 1080
CANVAS_HEIGHT = 3840 if ENABLE_4K_SHORTS else 1920
FFMPEG_BITRATE_4K = os.getenv("FFMPEG_BITRATE_4K", "18000k")
FFMPEG_BITRATE_1080P = os.getenv("FFMPEG_BITRATE_1080P", "4500k")
FFMPEG_BITRATE = os.getenv("FFMPEG_BITRATE", FFMPEG_BITRATE_4K if ENABLE_4K_SHORTS else FFMPEG_BITRATE_1080P)
FFMPEG_MAXRATE = "25000k" if ENABLE_4K_SHORTS else "6500k"
FFMPEG_BUFSIZE = "35000k" if ENABLE_4K_SHORTS else "9000k"

# Sincronización y calibración de subtítulos (offset negativo para compensar el retardo intrínseco de YouTube ASR captions)
SUBTITLE_OFFSET = float(os.getenv("SUBTITLE_OFFSET", "-0.45"))

# Protocolo de Coexistencia de Hardware (GaTDSEQ & Background Friendliness)
FFMPEG_THREADS = int(os.getenv("FFMPEG_THREADS", "2"))
CHECK_QUANT_BUSY = os.getenv("CHECK_QUANT_BUSY", "true").lower() in ("1", "true", "yes")

# Fase de Shorts de Gameplay (Activada por disponibilidad real de gameplay de GTA 6)
GAMEPLAY_RELEASE_DATE = os.getenv("GAMEPLAY_RELEASE_DATE", "2026-11-19")
FORCE_ENABLE_GAMEPLAY = os.getenv("FORCE_ENABLE_GAMEPLAY", "true").lower() in ("1", "true", "yes")

# Cadencia Anti-Spam y Protección de Algoritmo
LAUNCH_MAX_VIDEOS_PER_RUN = int(os.getenv("LAUNCH_MAX_VIDEOS_PER_RUN", "1"))
LAUNCH_MAX_DAILY_UPLOADS = int(os.getenv("LAUNCH_MAX_DAILY_UPLOADS", "4"))

# Feature Flags — Mejoras Alfa (activables individualmente)
ENABLE_QUALITY_GATE = os.getenv("ENABLE_QUALITY_GATE", "true").lower() in ("1", "true", "yes")
ENABLE_SERIES_CLASSIFIER = os.getenv("ENABLE_SERIES_CLASSIFIER", "true").lower() in ("1", "true", "yes")
ENABLE_EXIF_HYGIENE = os.getenv("ENABLE_EXIF_HYGIENE", "true").lower() in ("1", "true", "yes")
ENABLE_MULTIPLATFORM_COPY = os.getenv("ENABLE_MULTIPLATFORM_COPY", "true").lower() in ("1", "true", "yes")
ENABLE_REDDIT_SCOUT = os.getenv("ENABLE_REDDIT_SCOUT", "true").lower() in ("1", "true", "yes")
ENABLE_SEAMLESS_LOOP = os.getenv("ENABLE_SEAMLESS_LOOP", "true").lower() in ("1", "true", "yes")
ENABLE_STEM_SEPARATION = os.getenv("ENABLE_STEM_SEPARATION", "false").lower() in ("1", "true", "yes")
ENABLE_FEEDBACK_LOOP = os.getenv("ENABLE_FEEDBACK_LOOP", "true").lower() in ("1", "true", "yes")

def is_gameplay_enabled() -> bool:
    """Verifica si la fase de Shorts de Gameplay está activa (vía override o desde la fecha objetivo)."""
    if FORCE_ENABLE_GAMEPLAY:
        return True
    try:
        from datetime import datetime
        target = datetime.fromisoformat(GAMEPLAY_RELEASE_DATE)
        return datetime.now() >= target
    except Exception:
        return False

def get_max_videos_per_run() -> int:
    """En launch/gameplay mode usa LAUNCH_MAX_VIDEOS_PER_RUN; el resto del tiempo MAX_VIDEOS_PER_RUN."""
    if is_gameplay_enabled():
        return LAUNCH_MAX_VIDEOS_PER_RUN
    return MAX_VIDEOS_PER_RUN

def get_daily_upload_cap() -> int:
    """Cuota diaria del planificador adaptativo (elevada en fase de gameplay/estreno)."""
    if is_gameplay_enabled():
        return max(MAX_DAILY_UPLOADS, LAUNCH_MAX_DAILY_UPLOADS)
    return MAX_DAILY_UPLOADS

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

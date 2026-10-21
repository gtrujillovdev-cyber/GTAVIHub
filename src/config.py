import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output")).resolve()
TEMP_DIR = Path(os.getenv("TEMP_DIR", BASE_DIR / "temp")).resolve()
PROCESSED_FILE = BASE_DIR / "processed.json"
CHANNELS_FILE = BASE_DIR / "channels.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Defaults
MAX_VIDEOS_PER_RUN = int(os.getenv("MAX_VIDEOS_PER_RUN", "2"))
DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "es-ES-AlvaroNeural")

# FFmpeg Hardware Acceleration (VideoToolbox para Apple Silicon e Intel)
FFMPEG_VIDEO_CODEC = "h264_videotoolbox"
FFMPEG_BITRATE = "6M"

# Protocolo de Coexistencia de Hardware (GaTDSEQ & Background Friendliness)
FFMPEG_THREADS = int(os.getenv("FFMPEG_THREADS", "2"))
CHECK_QUANT_BUSY = os.getenv("CHECK_QUANT_BUSY", "true").lower() in ("1", "true", "yes")

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

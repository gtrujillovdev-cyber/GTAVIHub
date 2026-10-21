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

# FFmpeg Hardware Acceleration for Apple Silicon M4
FFMPEG_VIDEO_CODEC = "h264_videotoolbox"
FFMPEG_BITRATE = "6M"

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# API Keys (never logged or printed)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# Configurable Model Names
STT_PRIMARY_MODEL = os.getenv("STT_PRIMARY_MODEL", "gemini-3.8-flash").strip()
STT_SECONDARY_MODEL = os.getenv("STT_SECONDARY_MODEL", "gemini-3.5-flash").strip()
STT_TERTIARY_MODEL = os.getenv("STT_TERTIARY_MODEL", "whisper-large-v3").strip()

EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "gemini-3.1-flash-lite").strip()
EXTRACTION_FALLBACK_MODEL = os.getenv("EXTRACTION_FALLBACK_MODEL", "gemini-2.5-flash").strip()

# Storage Directories
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

SAMPLES_DIR = BASE_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("VOICE_DB_PATH", str(DATA_DIR / "voice_experience.db")))

# Upload and Audio Constraints
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB limit
MAX_AUDIO_DURATION_SECONDS = 120.0    # 2 minutes limit

def sanitize_message(message: str) -> str:
    """Sanitize any error message or string so API keys are never exposed."""
    s = str(message)
    for key in (GEMINI_API_KEY, GROQ_API_KEY):
        if key and len(key) >= 5:
            s = s.replace(key, "[REDACTED]")
    return s

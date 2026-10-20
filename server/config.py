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
EXTRACTION_FALLBACK_MODEL = os.getenv("EXTRACTION_FALLBACK_MODEL", "gemini-3.6-flash").strip()

# Storage Directories
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

SAMPLES_DIR = BASE_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

import sys

def get_db_path() -> Path:
    """
    Get the active database path.
    Dynamically checks VOICE_DB_PATH so runtime environment variable changes
    (such as test fixtures setting temporary databases) are immediately respected.
    Guards against tests touching the production database.
    """
    real_db_path = (DATA_DIR / "voice_experience.db").resolve()
    env_val = os.getenv("VOICE_DB_PATH")

    is_testing = (
        "PYTEST_CURRENT_TEST" in os.environ
        or "pytest" in sys.modules
        or os.getenv("TESTING", "").lower() in ("1", "true")
    )

    if env_val:
        resolved_path = Path(env_val).resolve()
        if is_testing and resolved_path == real_db_path:
            raise RuntimeError(
                f"Security Guard: Tests are strictly forbidden from accessing the production "
                f"database at {real_db_path}! Set VOICE_DB_PATH to an isolated temporary database."
            )
        return resolved_path

    if is_testing:
        raise RuntimeError(
            f"Security Guard: Tests must never use the production database path ({real_db_path})! "
            "Set VOICE_DB_PATH to an isolated temporary database."
        )

    return real_db_path


def __getattr__(name: str):
    if name == "DB_PATH":
        return get_db_path()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# Upload and Audio Constraints
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB limit
MAX_AUDIO_DURATION_SECONDS = 120.0    # 2 minutes limit

# Stage 4 Search Threshold (calibrated to 0.19)
SEARCH_THRESHOLD = float(os.getenv("SEARCH_THRESHOLD", "0.19"))

def sanitize_message(message: str) -> str:
    """Sanitize any error message or string so API keys are never exposed."""
    s = str(message)
    for key in (GEMINI_API_KEY, GROQ_API_KEY):
        if key and len(key) >= 5:
            s = s.replace(key, "[REDACTED]")
    return s

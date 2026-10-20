import base64
import os
import re
import time
from typing import Dict, Any, Optional
import requests

from server.config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    STT_PRIMARY_MODEL,
    STT_SECONDARY_MODEL,
    STT_TERTIARY_MODEL,
    sanitize_message
)
from server.database import get_cached_transcript, get_connection

GEMINI_STT_PROMPT = (
    "Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, "
    "keep English terms in Latin letters.\n"
    "Transcribe exactly what was said. Do not correct, rephrase, or fix wording. "
    "Do not include timestamps. If a word is unclear, write [unclear] instead of guessing.\n"
    "Domain glossary for spelling guidance: telemetry, pipeline, drift, schema, timestamp, batch, "
    "missing value, NaN, outlier, sensor, distribution, latency, partition, query, memory leak, "
    "index, join, target leakage, stratified split, normalization, train, test, overfit, "
    "scikit-learn, accuracy, preprocessing, cross-validation, feature engineering, confusion matrix, "
    "regression, classification, sampling, annotation, calibration, deployment, inference."
)

GROQ_STT_PROMPT = (
    "Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, "
    "keep English terms in Latin letters."
)

def call_gemini_stt(model: str, ogg_bytes: bytes, max_retries: int = 2) -> Optional[str]:
    """Call Gemini multimodal STT with at most 1 retry (~3s backoff) on 429/503."""
    if not GEMINI_API_KEY:
        return None

    audio_b64 = base64.b64encode(ogg_bytes).decode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "audio/ogg",
                            "data": audio_b64
                        }
                    },
                    {
                        "text": GEMINI_STT_PROMPT
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0
        }
    }

    delays = [3]
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"].strip()
            elif resp.status_code in (429, 503):
                # Backoff and retry
                time.sleep(delays[attempt] if attempt < len(delays) else 3)
                continue
            else:
                # Other non-retryable error
                break
        except requests.RequestException:
            time.sleep(delays[attempt] if attempt < len(delays) else 3)
            continue

    return None

def call_groq_stt(model: str, ogg_bytes: bytes) -> Optional[str]:
    """Call Groq Whisper STT fallback."""
    if not GROQ_API_KEY:
        return None

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "User-Agent": "VoiceOfExperience/1.0"
    }
    files = {
        "file": ("audio.ogg", ogg_bytes, "audio/ogg")
    }
    data = {
        "model": model,
        "prompt": GROQ_STT_PROMPT,
        "language": "ar",
        "temperature": 0.0
    }

    try:
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        if resp.status_code == 200:
            result = resp.json()
            return result.get("text", "").strip()
    except requests.RequestException:
        pass

    return None

def strip_leading_timestamp(text: str) -> str:
    """
    Strip leading mm:ss (or hh:mm:ss) timestamp patterns from transcripts,
    including bracketed forms like '[00:00]', '(00:00)', or bare '00:00'.
    """
    if not text:
        return ""
    cleaned = re.sub(r'^(?:\[|\()?\d{1,2}:\d{2}(?::\d{2})?(?:\]|\))?\s*[-–—:]?\s*', '', text.strip())
    return cleaned.strip()


def get_valid_stt_providers() -> set:
    """
    Construct valid STT provider names dynamically from current config:
    - Primary model (STT_PRIMARY_MODEL)
    - Secondary model (STT_SECONDARY_MODEL)
    - Tertiary model (STT_TERTIARY_MODEL)
    - Groq fallback name (f"groq-{STT_TERTIARY_MODEL}")
    """
    from server.config import STT_PRIMARY_MODEL, STT_SECONDARY_MODEL, STT_TERTIARY_MODEL
    valid = {
        STT_PRIMARY_MODEL,
        STT_SECONDARY_MODEL,
        STT_TERTIARY_MODEL,
        f"groq-{STT_TERTIARY_MODEL}",
    }
    return {p for p in valid if p}


def _save_to_stt_cache(audio_hash: str, raw_transcript: str, provider: str) -> None:
    """
    Internal cache writer strictly locked to the STT pipeline.
    Cannot be imported from database.py or called with unauthorized/fake providers.
    Guards against tests mutating the real production database.
    """
    allowed_providers = get_valid_stt_providers()
    if provider not in allowed_providers:
        raise ValueError(f"Unauthorized STT provider '{provider}' cannot write to stt_cache.")

    if "PYTEST_CURRENT_TEST" in os.environ and "VOICE_DB_PATH" not in os.environ:
        raise PermissionError(
            "Security Guard: Tests cannot write to production stt_cache without setting VOICE_DB_PATH."
        )

    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO stt_cache (audio_hash, raw_transcript, stt_provider)
            VALUES (?, ?, ?)
            """,
            (audio_hash, raw_transcript, provider)
        )
        conn.commit()


def transcribe_audio_pipeline(original_sha256: str, ogg_bytes: bytes) -> Dict[str, Any]:
    """
    Resilient Multi-Tier Transcription Pipeline:
    1. Check SQLite cache by original uploaded audio SHA-256
    2. Primary Gemini model (default: gemini-3.8-flash)
    3. Secondary Gemini model (default: gemini-3.5-flash)
    4. Tertiary Groq Whisper fallback (whisper-large-v3)
    5. Cache and return result
    """
    # 1. Check cache
    cached = get_cached_transcript(original_sha256)
    if cached:
        return {
            "transcript": cached["raw_transcript"],
            "stt_provider": cached["stt_provider"],
            "cached": True,
            "fallback": "groq" in cached["stt_provider"].lower()
        }

    # 2. Try Primary Gemini
    transcript = call_gemini_stt(STT_PRIMARY_MODEL, ogg_bytes)
    provider = STT_PRIMARY_MODEL
    fallback = False

    # 3. Try Secondary Gemini if Primary fails
    if not transcript:
        transcript = call_gemini_stt(STT_SECONDARY_MODEL, ogg_bytes)
        provider = STT_SECONDARY_MODEL

    # 4. Try Tertiary Groq Whisper if both Gemini models fail
    if not transcript:
        transcript = call_groq_stt(STT_TERTIARY_MODEL, ogg_bytes)
        provider = f"groq-{STT_TERTIARY_MODEL}"
        fallback = True

    if not transcript:
        raise RuntimeError("Transcription failed across all primary, secondary, and fallback providers.")

    # Post-process: strip any leading timestamps e.g. "00:00 "
    transcript = strip_leading_timestamp(transcript)

    # 5. Cache result via internal pipeline writer
    _save_to_stt_cache(original_sha256, transcript, provider)

    return {
        "transcript": transcript,
        "stt_provider": provider,
        "cached": False,
        "fallback": fallback
    }

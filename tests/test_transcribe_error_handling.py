"""
Tests for /api/transcribe error handling and failure modes.

Verifies:
1. When STT providers fail/time out, endpoint returns clean 503 Service Unavailable JSON.
2. File validation errors (empty, oversized) return clean 400 Bad Request JSON.
3. Audio conversion errors return clean 422 Unprocessable Entity JSON.
4. Pipeline directly reproduces the provider exhaustion exception when providers fail.
5. Tests never call real Gemini or touch the production database.
"""

import io
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.stt_pipeline import transcribe_audio_pipeline

client = TestClient(app)
SAMPLE_AUDIO_PATH = Path(__file__).resolve().parent.parent / "audio/73519c82b5a22de87e71939eee5c6b4dba8d4e8f66b0c2bfc0fbbe3e51e79bcd.ogg"


def test_pipeline_reproduces_exception_when_providers_fail():
    """Reproduce provider failure exception by calling pipeline directly on the audio file."""
    assert SAMPLE_AUDIO_PATH.exists(), f"Sample audio {SAMPLE_AUDIO_PATH} not found"
    raw_bytes = SAMPLE_AUDIO_PATH.read_bytes()
    file_hash = "73519c82b5a22de87e71939eee5c6b4dba8d4e8f66b0c2bfc0fbbe3e51e79bcd"

    with patch("server.stt_pipeline.call_gemini_stt", return_value=None):
        with patch("server.stt_pipeline.call_groq_stt", return_value=None):
            with pytest.raises(RuntimeError, match="Transcription failed across all primary"):
                transcribe_audio_pipeline(file_hash, raw_bytes)


def test_transcribe_endpoint_returns_503_json_when_stt_fails():
    """When all STT providers fail, endpoint must return 503 with structured JSON detail."""
    raw_bytes = SAMPLE_AUDIO_PATH.read_bytes()

    with patch("server.stt_pipeline.call_gemini_stt", return_value=None):
        with patch("server.stt_pipeline.call_groq_stt", return_value=None):
            resp = client.post(
                "/api/transcribe",
                files={"file": ("test_recording.ogg", io.BytesIO(raw_bytes), "audio/ogg")}
            )

    assert resp.status_code == 503
    assert resp.headers.get("content-type", "").startswith("application/json")
    data = resp.json()
    assert "detail" in data
    assert "STT Service Unavailable" in data["detail"]


def test_transcribe_endpoint_rejects_empty_file_with_400():
    """Empty audio file returns clean 400 JSON."""
    resp = client.post(
        "/api/transcribe",
        files={"file": ("empty.ogg", io.BytesIO(b""), "audio/ogg")}
    )
    assert resp.status_code == 400
    assert resp.headers.get("content-type", "").startswith("application/json")
    assert "empty" in resp.json()["detail"].lower()


def test_transcribe_endpoint_rejects_oversized_file_with_400():
    """File exceeding 10 MB returns clean 400 JSON."""
    huge_data = b"0" * (10 * 1024 * 1024 + 1024)
    resp = client.post(
        "/api/transcribe",
        files={"file": ("huge.ogg", io.BytesIO(huge_data), "audio/ogg")}
    )
    assert resp.status_code == 400
    assert resp.headers.get("content-type", "").startswith("application/json")
    assert "maximum" in resp.json()["detail"].lower()


def test_transcribe_endpoint_rejects_corrupted_audio_with_422():
    """Non-audio bytes that fail ffmpeg conversion return clean 422 JSON."""
    garbage = b"NOT_A_REAL_AUDIO_FILE_GARBAGE_HEADER_12345"
    resp = client.post(
        "/api/transcribe",
        files={"file": ("corrupt.ogg", io.BytesIO(garbage), "audio/ogg")}
    )
    assert resp.status_code in (400, 422)
    assert resp.headers.get("content-type", "").startswith("application/json")
    assert "Audio conversion failed" in resp.json()["detail"]

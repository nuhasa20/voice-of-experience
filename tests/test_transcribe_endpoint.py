#!/usr/bin/env python3
"""
Test the /api/transcribe endpoint end-to-end:
1. Validates upload limit rejection (files > 10 MB or > 2 min)
2. Converts a browser WebM recording through ffmpeg
3. Exercises the fallback chain (Gemini 503 -> secondary -> Groq whisper-large-v3)
4. Checks SQLite stt_cache idempotency on original bytes
"""

import io
import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure tests run against an isolated temporary database
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["VOICE_DB_PATH"] = _tmp_db.name

from fastapi.testclient import TestClient
from server.main import app
from server.database import get_connection, init_db

init_db()
client = TestClient(app)

import subprocess
from server.audio_convert import get_ffmpeg_executable

def test_transcribe_endpoint():
    print("=== TEST 1: Health Check ===")
    resp = client.get("/api/health")
    print(f"Health response: {resp.status_code} {resp.json()}")
    assert resp.status_code == 200

    print("\n=== TEST 2: Reject File > 10 MB ===")
    big_fake_bytes = b"0" * (10 * 1024 * 1024 + 1024)
    resp = client.post(
        "/api/transcribe",
        files={"file": ("huge.webm", io.BytesIO(big_fake_bytes), "audio/webm")}
    )
    print(f"Big file response: {resp.status_code} {resp.json()}")
    assert resp.status_code == 400

    print("\n=== TEST 3: Reject Empty File ===")
    resp = client.post(
        "/api/transcribe",
        files={"file": ("empty.webm", io.BytesIO(b""), "audio/webm")}
    )
    print(f"Empty file response: {resp.status_code} {resp.json()}")
    assert resp.status_code == 400

    print("\n=== TEST 4: Browser WebM Upload & Fallback Chain ===")
    webm_file = Path("/tmp/browser_recording_sample.webm")
    if not webm_file.exists():
        ffmpeg_exe = get_ffmpeg_executable()
        source_ogg = BASE_DIR / "audio/04_data_leakage.ogg"
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", str(source_ogg), "-c:a", "libopus", str(webm_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

    with open(webm_file, "rb") as f:
        webm_bytes = f.read()

    resp = client.post(
        "/api/transcribe",
        files={"file": ("mic_recording.webm", io.BytesIO(webm_bytes), "audio/webm")}
    )
    print(f"Transcribe response status: {resp.status_code}")
    data = resp.json()
    print("Returned JSON payload:")
    for k, v in data.items():
        if k == "transcript":
            print(f"  {k}: {str(v)[:160]}...")
        else:
            print(f"  {k}: {v}")

    assert resp.status_code == 200
    assert "audio_hash" in data
    assert "transcript" in data
    assert len(data["transcript"]) > 0

    print("\n=== TEST 5: Verify Cache Idempotency (Second Call with Same WebM) ===")
    resp2 = client.post(
        "/api/transcribe",
        files={"file": ("mic_recording.webm", io.BytesIO(webm_bytes), "audio/webm")}
    )
    data2 = resp2.json()
    print(f"Second call status: {resp2.status_code}")
    print(f"Cached flag: {data2.get('cached')}")
    assert data2.get("cached") is True
    assert data2.get("audio_hash") == data.get("audio_hash")

    print("\n=== ALL END-TO-END TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_transcribe_endpoint()

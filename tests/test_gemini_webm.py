#!/usr/bin/env python3
"""
Test whether Gemini accepts audio converted from a browser WebM recording.
Also checks whether Gemini accepts raw WebM directly.
NEVER prints API keys.
"""

import os
import sys
import subprocess
import json
import base64
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server.config import (
    GEMINI_API_KEY,
    STT_PRIMARY_MODEL,
    sanitize_message
)
from server.audio_convert import convert_audio_to_ogg, get_ffmpeg_executable
from server.stt_pipeline import GEMINI_STT_PROMPT

def run_test():
    source_ogg = BASE_DIR / "audio/04_data_leakage.ogg"
    if not source_ogg.exists():
        print(f"Error: {source_ogg} not found!")
        return

    ffmpeg_exe = get_ffmpeg_executable()
    webm_path = Path("/tmp/browser_recording_sample.webm")

    print("[1] Generating browser-style WebM recording from audio/04_data_leakage.ogg...")
    # Browser MediaRecorder uses WebM container with Opus audio
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-i", str(source_ogg),
            "-c:a", "libopus",
            "-b:a", "64k",
            "-ar", "48000",
            "-ac", "1",
            "-f", "webm",
            str(webm_path)
        ],
        check=True,
        capture_output=True
    )
    print(f"    Generated WebM size: {webm_path.stat().st_size} bytes")

    with open(webm_path, "rb") as f:
        raw_webm_bytes = f.read()

    print("[2] Running conversion through server.audio_convert (WebM -> OGG Opus)...")
    try:
        converted_ogg, duration, original_hash = convert_audio_to_ogg(raw_webm_bytes, original_extension=".webm")
        print(f"    Conversion successful!")
        print(f"    Duration: {duration:.2f} seconds")
        print(f"    Original WebM SHA-256: {original_hash}")
        print(f"    Converted OGG size: {len(converted_ogg)} bytes")
    except Exception as e:
        print(f"    Conversion failed: {sanitize_message(str(e))}")
        return

    print(f"[3] Sending converted OGG to Gemini ({STT_PRIMARY_MODEL})...")
    audio_b64 = base64.b64encode(converted_ogg).decode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{STT_PRIMARY_MODEL}:generateContent"
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

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        print(f"    Gemini Response Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    transcript = parts[0]["text"].strip()
                    print("\n--- TRANSCRIPT RETURNED BY GEMINI ---")
                    print(transcript)
                    print("--------------------------------------")
                    print("\nRESULT: SUCCESS! Gemini accepts audio converted from WebM recording.")
                else:
                    print("    No text part in candidate content.")
            else:
                print("    No candidate in response.")
        else:
            print(f"    Gemini error: {sanitize_message(resp.text[:400])}")
    except Exception as exc:
        print(f"    Request failed: {sanitize_message(str(exc))}")

    # Optional: Also test raw WebM directly to check native support
    print(f"\n[4] Supplemental test: Sending raw WebM directly to Gemini with mime_type='audio/webm'...")
    webm_b64 = base64.b64encode(raw_webm_bytes).decode("utf-8")
    payload_raw = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "audio/webm",
                            "data": webm_b64
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
    try:
        resp_raw = requests.post(url, headers=headers, json=payload_raw, timeout=90)
        print(f"    Raw WebM Gemini Status: {resp_raw.status_code}")
        if resp_raw.status_code == 200:
            print("    Gemini also directly accepts raw audio/webm!")
        else:
            print(f"    Raw WebM response: {sanitize_message(resp_raw.text[:200])}")
    except Exception as exc:
        print(f"    Raw WebM test failed: {sanitize_message(str(exc))}")

if __name__ == "__main__":
    run_test()

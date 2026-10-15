#!/usr/bin/env python3
"""
Run Gemini 3.5-flash and 3.6-flash evaluation with:
- Prompt B + exactness instruction ("Transcribe exactly what was said. Do not correct, rephrase or fix wording. If a word is unclear, write [unclear] instead of guessing.")
- temperature = 0
- audio/04_data_leakage.ogg (second run to test repeatability)
- audio/06_nan_missing_class.ogg
- Automatic backoff/retry on temporary 503 spikes
"""

import os
import sys
import time
import base64
import requests

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PROMPT = (
    "Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, "
    "keep English terms in Latin letters. Transcribe exactly what was said. "
    "Do not correct, rephrase or fix wording. If a word is unclear, write [unclear] instead of guessing."
)

def load_dotenv(filepath=None):
    if filepath is None:
        filepath = BASE_DIR / ".env"
    env = {}
    if not os.path.exists(filepath):
        return env
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("\"'")
    return env

def sanitize(msg, keys):
    s = str(msg)
    for k in keys:
        if k and len(k) > 5:
            s = s.replace(k, "[REDACTED]")
    return s

def transcribe_with_retry(model, api_key, audio_path, max_retries=4):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

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
                        "text": PROMPT
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0
        }
    }

    last_err = ""
    for attempt in range(1, max_retries + 1):
        t0 = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            elapsed = time.time() - t0
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    text = "".join([p.get("text", "") for p in parts]).strip()
                    return {"success": True, "text": text, "elapsed_sec": round(elapsed, 2)}
                return {"success": False, "text": "[No text parts returned]", "elapsed_sec": round(elapsed, 2)}
            elif resp.status_code in [503, 429]:
                last_err = f"HTTP {resp.status_code}: {sanitize(resp.text, [api_key])}"
                wait_time = attempt * 4
                print(f"  [Attempt {attempt} returned {resp.status_code}, retrying in {wait_time}s...]", flush=True)
                time.sleep(wait_time)
            else:
                return {"success": False, "text": f"HTTP {resp.status_code}: {sanitize(resp.text, [api_key])}", "elapsed_sec": round(elapsed, 2)}
        except Exception as e:
            elapsed = time.time() - t0
            last_err = sanitize(str(e), [api_key])
            wait_time = attempt * 4
            print(f"  [Attempt {attempt} raised exception, retrying in {wait_time}s: {last_err}]", flush=True)
            time.sleep(wait_time)

    return {"success": False, "text": f"Failed after {max_retries} retries. Last error: {last_err}", "elapsed_sec": 0}

def main():
    env = load_dotenv()
    gemini_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")

    if not gemini_key:
        print("GEMINI_API_KEY not found in .env")
        sys.exit(1)

    models = ["gemini-3.5-flash", "gemini-3.6-flash"]
    files = [
        (str(BASE_DIR / "audio/04_data_leakage.ogg"), "04_data_leakage.ogg (Run 2)"),
        (str(BASE_DIR / "audio/06_nan_missing_class.ogg"), "06_nan_missing_class.ogg")
    ]

    for audio_path, label in files:
        if not os.path.exists(audio_path):
            print(f"File not found: {audio_path}")
            continue

        print("\n" + "=" * 80)
        print(f"FILE: {label}")
        print("=" * 80)

        for model in models:
            print(f"\n--- Model: {model} (temperature=0) ---", flush=True)
            res = transcribe_with_retry(model, gemini_key, audio_path)
            if res["success"]:
                print(f"Duration: {res['elapsed_sec']}s")
                print("Transcript:")
                print(res["text"])
            else:
                print(f"Failed: {res['text']}")

if __name__ == "__main__":
    main()

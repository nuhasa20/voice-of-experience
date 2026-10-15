#!/usr/bin/env python3
"""
Diagnostic script:
1. Probe Gemini models with tiny text prompt ("say hi", 20s timeout) and measure response time.
2. For Gemini models that responded with 200, run audio test (prompt B only) on audio/04_data_leakage.ogg.
3. Rerun Groq with language="ar", temperature=0, and prompt B on audio/04_data_leakage.ogg.
"""

import os
import sys
import time
import base64
import requests

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_B = "Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, keep English terms in Latin letters."

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

def probe_gemini_model(model, api_key, timeout=20):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{"parts": [{"text": "say hi"}]}]
    }

    t0 = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        elapsed = time.time() - t0
        return {
            "model": model,
            "status": resp.status_code,
            "elapsed_sec": round(elapsed, 2),
            "text": resp.text[:150],
            "success": (resp.status_code == 200)
        }
    except Exception as e:
        elapsed = time.time() - t0
        err_msg = sanitize(str(e), [api_key])
        return {
            "model": model,
            "status": "TIMEOUT/ERROR",
            "elapsed_sec": round(elapsed, 2),
            "text": err_msg,
            "success": False
        }

def transcribe_gemini_audio(model, api_key, audio_path, prompt, timeout=90):
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
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2
        }
    }

    t0 = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        elapsed = time.time() - t0
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                text = "".join([p.get("text", "") for p in parts]).strip()
                return {"success": True, "text": text, "elapsed_sec": round(elapsed, 2)}
            return {"success": False, "text": "[No text parts returned]", "elapsed_sec": round(elapsed, 2)}
        else:
            return {"success": False, "text": f"HTTP {resp.status_code}: {sanitize(resp.text, [api_key])}", "elapsed_sec": round(elapsed, 2)}
    except Exception as e:
        elapsed = time.time() - t0
        return {"success": False, "text": sanitize(str(e), [api_key]), "elapsed_sec": round(elapsed, 2)}

def transcribe_groq_stable(api_key, audio_path, prompt):
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    t0 = time.time()
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/ogg")}
        data = {
            "model": "whisper-large-v3",
            "prompt": prompt,
            "language": "ar",
            "temperature": "0",
            "response_format": "json"
        }
        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            elapsed = time.time() - t0
            if resp.status_code == 200:
                return {"success": True, "text": resp.json().get("text", "").strip(), "elapsed_sec": round(elapsed, 2)}
            else:
                return {"success": False, "text": f"HTTP {resp.status_code}: {sanitize(resp.text, [api_key])}", "elapsed_sec": round(elapsed, 2)}
        except Exception as e:
            elapsed = time.time() - t0
            return {"success": False, "text": sanitize(str(e), [api_key]), "elapsed_sec": round(elapsed, 2)}

def main():
    env = load_dotenv()
    gemini_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    groq_key = env.get("GROQ_API_KEY")

    models_to_probe = [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite"
    ]

    print("=== PART 1: Gemini Text Diagnosis (20s timeout per call) ===")
    responding_models = []
    if gemini_key:
        for model in models_to_probe:
            print(f"Probing {model}...", flush=True)
            res = probe_gemini_model(model, gemini_key, timeout=20)
            print(f"  Result: Status {res['status']} | Duration: {res['elapsed_sec']}s")
            if res['success']:
                responding_models.append(model)
                print(f"  Snippet: {res['text'].strip()}")
            else:
                print(f"  Detail: {res['text'].strip()}")
    else:
        print("GEMINI_API_KEY not found in .env")

    print("\nResponding Gemini models:", responding_models)

    audio_file = str(BASE_DIR / "audio/04_data_leakage.ogg")

    print(f"\n=== PART 2: Gemini Audio Transcription (Prompt B only on {audio_file}) ===")
    if responding_models and os.path.exists(audio_file):
        for model in responding_models:
            print(f"\n--- Transcribing with {model} ---", flush=True)
            res = transcribe_gemini_audio(model, gemini_key, audio_file, PROMPT_B, timeout=90)
            if res["success"]:
                print(f"Duration: {res['elapsed_sec']}s")
                print("Transcript:")
                print(res["text"])
            else:
                print(f"Failed in {res['elapsed_sec']}s: {res['text']}")
    else:
        print("Skipping Gemini audio: no models responded with 200 or audio missing.")

    print(f"\n=== PART 3: Groq Stable Rerun (language=ar, temperature=0, prompt B on {audio_file}) ===")
    if groq_key and os.path.exists(audio_file):
        res_groq = transcribe_groq_stable(groq_key, audio_file, PROMPT_B)
        if res_groq["success"]:
            print(f"Duration: {res_groq['elapsed_sec']}s")
            print("Transcript:")
            print(res_groq["text"])
        else:
            print(f"Failed in {res_groq['elapsed_sec']}s: {res_groq['text']}")
    else:
        print("Skipping Groq: GROQ_API_KEY missing or audio file missing.")

if __name__ == "__main__":
    main()

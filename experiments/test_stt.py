#!/usr/bin/env python3
"""
Speech-to-Text testing script for Libyan Arabic + English technical audio clips.
Compares Gemini (gemini-2.5-flash, gemini-3.8-flash) and Groq (Whisper-large-v3)
with Prompt A (with terms) and Prompt B (generic).
"""

import os
import sys
import json
import base64
import requests

PROMPT_A_GEMINI = (
    "Transcribe this audio recording verbatim. The speaker is speaking in Libyan Arabic "
    "mixed with English technical terms (such as machine learning, data leakage, NaN, "
    "missing class, telemetry, etc.). Output ONLY the raw transcript in the spoken Arabic "
    "dialect with English technical terms preserved as spoken in Latin letters. Do not "
    "translate, do not summarize, and do not add timestamps or markdown explanations."
)

PROMPT_B_GEMINI = (
    "Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, "
    "keep English terms in Latin letters."
)

PROMPT_A_GROQ = (
    "تسجيل بالعامية الليبية مع مصطلحات تقنية بالإنجليزية مثل data leakage, NaN, missing class, train, test"
)

PROMPT_B_GROQ = (
    "Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, "
    "keep English terms in Latin letters."
)

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def load_dotenv(filepath=None):
    """Load key-value pairs from .env without printing or leaking them."""
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
                k = k.strip()
                v = v.strip().strip("\"'")
                env[k] = v
    return env

def sanitize_error(err_str, keys):
    """Ensure no API key appears in any error message."""
    s = str(err_str)
    for k in keys:
        if k and len(k) > 5:
            s = s.replace(k, "[REDACTED]")
    return s

def transcribe_gemini_single(audio_path, api_key, model, prompt_text, prompt_label):
    """Transcribe a single file using a specific Gemini model and prompt."""
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    # Use header for authentication so key is not in URL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
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
                        "text": prompt_text
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                text = "".join([p.get("text", "") for p in parts]).strip()
                return text
            return "[No transcript candidate returned]"
        else:
            clean_err = sanitize_error(resp.text, [api_key])
            return f"[Error: HTTP {resp.status_code} - {clean_err}]"
    except Exception as e:
        clean_err = sanitize_error(str(e), [api_key])
        return f"[Error: {clean_err}]"

def transcribe_groq_single(audio_path, api_key, prompt_text, prompt_label):
    """Transcribe a single file using Groq Whisper Large v3 and a specific prompt."""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    with open(audio_path, "rb") as f:
        files = {
            "file": (os.path.basename(audio_path), f, "audio/ogg")
        }
        data = {
            "model": "whisper-large-v3",
            "prompt": prompt_text,
            "response_format": "json"
        }
        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=90)
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
            else:
                clean_err = sanitize_error(resp.text, [api_key])
                return f"[Error: HTTP {resp.status_code} - {clean_err}]"
        except Exception as e:
            clean_err = sanitize_error(str(e), [api_key])
            return f"[Error: {clean_err}]"

def transcribe_openai_single(audio_path, api_key, prompt_text, prompt_label):
    """Transcribe a single file using OpenAI Whisper-1."""
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    with open(audio_path, "rb") as f:
        files = {
            "file": (os.path.basename(audio_path), f, "audio/ogg")
        }
        data = {
            "model": "whisper-1",
            "prompt": prompt_text,
            "response_format": "json"
        }
        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=90)
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
            else:
                clean_err = sanitize_error(resp.text, [api_key])
                return f"[Error: HTTP {resp.status_code} - {clean_err}]"
        except Exception as e:
            clean_err = sanitize_error(str(e), [api_key])
            return f"[Error: {clean_err}]"

def main():
    env = load_dotenv()
    for k, v in env.items():
        if k not in os.environ:
            os.environ[k] = v

    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    active_services = []
    if gemini_key:
        active_services.append("Gemini")
    if groq_key:
        active_services.append("Groq")
    if openai_key:
        active_services.append("OpenAI")

    print(f"Loaded services: {active_services}")
    if not active_services:
        print("No API keys found in .env. Exiting.")
        sys.exit(1)

    audio_files = [
        str(BASE_DIR / "audio/04_data_leakage.ogg"),
        str(BASE_DIR / "audio/06_nan_missing_class.ogg")
    ]

    for audio_file in audio_files:
        if not os.path.exists(audio_file):
            print(f"File not found: {audio_file}")
            continue

        print("\n" + "=" * 80)
        print(f"FILE: {audio_file}")
        print("=" * 80)

        # Gemini runs
        if gemini_key:
            gemini_models = ["gemini-2.5-flash", "gemini-3.8-flash"]
            for model in gemini_models:
                # Prompt A
                print(f"\n--- [Gemini] {model} | prompt A (with terms) ---")
                res_a = transcribe_gemini_single(audio_file, gemini_key, model, PROMPT_A_GEMINI, "prompt A")
                print(res_a)

                # Prompt B
                print(f"\n--- [Gemini] {model} | prompt B (generic) ---")
                res_b = transcribe_gemini_single(audio_file, gemini_key, model, PROMPT_B_GEMINI, "prompt B")
                print(res_b)

        # Groq runs
        if groq_key:
            # Prompt A
            print(f"\n--- [Groq] whisper-large-v3 | prompt A (with terms) ---")
            res_groq_a = transcribe_groq_single(audio_file, groq_key, PROMPT_A_GROQ, "prompt A")
            print(res_groq_a)

            # Prompt B
            print(f"\n--- [Groq] whisper-large-v3 | prompt B (generic) ---")
            res_groq_b = transcribe_groq_single(audio_file, groq_key, PROMPT_B_GROQ, "prompt B")
            print(res_groq_b)

        # OpenAI runs (if key provided)
        if openai_key:
            print(f"\n--- [OpenAI] whisper-1 | prompt A (with terms) ---")
            res_oai_a = transcribe_openai_single(audio_file, openai_key, PROMPT_A_GROQ, "prompt A")
            print(res_oai_a)

            print(f"\n--- [OpenAI] whisper-1 | prompt B (generic) ---")
            res_oai_b = transcribe_openai_single(audio_file, openai_key, PROMPT_B_GROQ, "prompt B")
            print(res_oai_b)

if __name__ == "__main__":
    main()

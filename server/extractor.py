"""
Quote-Verified AI Card Extraction Engine.

Implements spec.md Component 5:
- Extraction prompt instructs the LLM to output strict JSON with verbatim quotes
- Arabic-aware normalized substring matching for quote verification
- Length cap (60% rule), distinct quotes rule
- Two-tier outcome: "Could not be verified – please edit" vs "Not mentioned"
- Extraction cache keyed by SHA-256 of edited transcript
- Primary extraction model with fallback (Gemini & Groq)
"""

import hashlib
import json
import re
import time
from typing import Dict, Any, Optional, List

import requests

from server.config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    EXTRACTION_MODEL,
    EXTRACTION_FALLBACK_MODEL,
)
from server.database import get_cached_extraction, set_cached_extraction
from server.normalizer import normalize_arabic

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """\
You are a structured extraction engine for an engineering troubleshooting system.
Given the following verbatim Arabic transcript (with English technical terms), extract 5 diagnostic fields.

For **each** field you MUST return:
- `verbatim_quote`: An exact substring copied verbatim from the transcript. Do NOT paraphrase. NEVER include [unclear] markers in quotes; if a phrase contains [unclear], quote only the clear portion or set to null if no clear quote exists.
- `summary`: A short optional English summary (one sentence max). May be null.

If the expert did NOT mention anything for a field, set `verbatim_quote` to null and `stated` to false. Do not invent content.

Fields to extract:
1. `problem_summary` — What problem or symptom is described?
2. `possible_causes` — What causes or reasons does the expert mention?
3. `checks` — What checks or verification steps does the expert suggest?
4. `solution_steps` — What solution or fix does the expert recommend?
5. `cautions` — Any warnings or cautions the expert states? (set `stated` to false if none)

Return ONLY valid JSON, no markdown fences, no explanation:
{
  "problem_summary": {"verbatim_quote": "...", "summary": "..."},
  "possible_causes": {"verbatim_quote": "...", "summary": "..."},
  "checks": {"verbatim_quote": "...", "summary": "..."},
  "solution_steps": {"verbatim_quote": "...", "summary": "..."},
  "cautions": {"verbatim_quote": "... or null", "summary": "... or null", "stated": true/false}
}

Transcript:
"""

FIELD_NAMES: List[str] = [
    "problem_summary",
    "possible_causes",
    "checks",
    "solution_steps",
    "cautions",
]


# ---------------------------------------------------------------------------
# Model API calls (Gemini & Groq)
# ---------------------------------------------------------------------------

def _parse_extraction_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Parse the LLM response as JSON, stripping markdown fences if present."""
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw_text.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _call_gemini_extract(model: str, transcript: str, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Call Gemini text model for structured JSON extraction with retry."""
    if not GEMINI_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": EXTRACTION_PROMPT + transcript}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }

    delays = [2, 4]
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        raw_text = parts[0]["text"].strip()
                        parsed = _parse_extraction_json(raw_text)
                        if parsed:
                            return parsed
            elif resp.status_code in (429, 503):
                time.sleep(delays[attempt] if attempt < len(delays) else 4)
                continue
            else:
                break
        except requests.RequestException:
            time.sleep(delays[attempt] if attempt < len(delays) else 4)
            continue

    return None


def _call_groq_extract(model: str, transcript: str) -> Optional[Dict[str, Any]]:
    """Call Groq chat completion model for structured JSON extraction."""
    if not GROQ_API_KEY:
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": EXTRACTION_PROMPT + transcript}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices and "message" in choices[0]:
                content = choices[0]["message"].get("content", "")
                return _parse_extraction_json(content)
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Quote verification engine
# ---------------------------------------------------------------------------

UNCLEAR_MARKER_REGEX = re.compile(
    r'(\[\s*(?:unclear|غير\s*واضح)\s*\]|\[\s*[^\]]*unclear[^\]]*\])',
    re.IGNORECASE
)


def contains_unclear_marker(text: Optional[str]) -> bool:
    """
    Check if a text string contains an [unclear] token or marker.
    Matches variations such as [unclear], [Unclear], [UNCLEAR], [غير واضح],
    [ unclear ], or any bracketed unclear token.
    """
    if not text:
        return False
    if UNCLEAR_MARKER_REGEX.search(text):
        return True
    lower = text.lower()
    return "[unclear]" in lower or "[غير واضح]" in text


def verify_quotes(
    extraction: Dict[str, Any],
    transcript: str,
) -> Dict[str, Any]:
    """
    Verify each extracted verbatim_quote against the transcript using
    Arabic-aware normalization.

    Verification rules:
    1. Normalized substring match
    2. Length cap: quote <= 60% of transcript length (reject if > 60%)
    3. Distinct quotes: no two fields share the same quote (reject duplicates)
    4. Unclear marker rejection: quotes containing [unclear] are NEVER accepted

    Outcomes:
    - verified: passes all checks, quote is primary display value
    - unverified: fails check -> display_text = "Could not be verified – please edit"
    - not_mentioned: stated=false or null quote -> display_text = "Not mentioned"
      (or "No caution stated by the expert" for cautions)
    """
    norm_transcript = normalize_arabic(transcript)
    transcript_len = len(norm_transcript)
    max_quote_len = int(0.6 * transcript_len) if transcript_len > 0 else 0

    # Collect all valid quotes for distinctness check
    quote_map: Dict[str, List[str]] = {}  # normalized_quote -> [field_names]

    for field in FIELD_NAMES:
        field_data = extraction.get(field)
        if not field_data or not isinstance(field_data, dict):
            continue

        raw_quote = field_data.get("verbatim_quote")
        stated = field_data.get("stated", True)

        if stated is False or raw_quote is None:
            continue
        if isinstance(raw_quote, str) and not raw_quote.strip():
            continue
        if contains_unclear_marker(raw_quote):
            continue

        norm_q = normalize_arabic(raw_quote)
        if norm_q:
            quote_map.setdefault(norm_q, []).append(field)

    # Duplicate quotes across fields (same quote used for multiple fields)
    duplicate_quotes = {q for q, fields in quote_map.items() if len(fields) > 1}

    # Verify each field
    verified: Dict[str, Any] = {}
    for field in FIELD_NAMES:
        field_data = extraction.get(field)
        if not field_data or not isinstance(field_data, dict):
            field_data = {}

        raw_quote = field_data.get("verbatim_quote")
        summary = field_data.get("summary")
        stated = field_data.get("stated", True)

        # 1. Not mentioned check
        if stated is False or raw_quote is None or (isinstance(raw_quote, str) and not raw_quote.strip()):
            display_text = "No caution stated by the expert" if field == "cautions" else "Not mentioned"
            verified[field] = {
                "verbatim_quote": None,
                "summary": summary,
                "status": "not_mentioned",
                "display_text": display_text,
                "stated": False,
                "reason": None,
            }
            continue

        # 2. Quote verification
        norm_quote = normalize_arabic(raw_quote)
        has_unclear = contains_unclear_marker(raw_quote)

        # Rule 1: Substring match
        is_substring = bool(norm_quote and norm_quote in norm_transcript)

        # Rule 2: Length cap (<= 60% of transcript length)
        is_within_length = bool(norm_quote and len(norm_quote) <= max_quote_len)

        # Rule 3: Distinct quotes
        is_distinct = bool(norm_quote and norm_quote not in duplicate_quotes)

        # Rule 4: Must NOT contain [unclear] markers
        is_clean_of_unclear = not has_unclear

        if is_substring and is_within_length and is_distinct and is_clean_of_unclear:
            verified[field] = {
                "verbatim_quote": raw_quote,
                "summary": summary,
                "status": "verified",
                "display_text": raw_quote,
                "stated": True,
                "reason": None,
            }
        else:
            reasons = []
            if has_unclear:
                reasons.append("contains_unclear_marker")
            if not is_substring:
                reasons.append("not_in_transcript")
            if not is_within_length:
                reasons.append("exceeds_length_cap")
            if not is_distinct:
                reasons.append("duplicate_quote")

            verified[field] = {
                "verbatim_quote": raw_quote,
                "summary": summary,
                "status": "unverified",
                "display_text": "Could not be verified – please edit",
                "stated": True,
                "reason": ", ".join(reasons),
            }

    return verified


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_card_fields(
    transcript: str,
    provider: str = "gemini",
) -> Dict[str, Any]:
    """
    Extract and verify diagnostic card fields from the edited transcript.

    1. Check extraction cache (keyed by SHA-256 of transcript text)
    2. Call primary extraction model
    3. Fallback to secondary extraction model (Gemini or Groq)
    4. Verify quotes with Arabic-aware normalization
    5. Cache and return
    """
    # Compute transcript hash for cache key
    transcript_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()

    # 1. Check extraction cache
    cached = get_cached_extraction(transcript_hash)
    if cached:
        parsed = json.loads(cached["extracted_json"])
        return {
            "fields": parsed,
            "model_name": cached["model_name"],
            "cached": True,
        }

    # 2. Call extraction model
    raw_extraction = None
    model_used = EXTRACTION_MODEL

    if provider == "test-fixture":
        raw_extraction = _test_fixture_extraction(transcript)
        model_used = "test-fixture"
    else:
        # Try primary model
        raw_extraction = _call_gemini_extract(EXTRACTION_MODEL, transcript)
        model_used = EXTRACTION_MODEL

        # Try secondary fallback model if primary failed
        if raw_extraction is None:
            if "llama" in EXTRACTION_FALLBACK_MODEL.lower() or "groq" in EXTRACTION_FALLBACK_MODEL.lower():
                raw_extraction = _call_groq_extract(EXTRACTION_FALLBACK_MODEL, transcript)
            else:
                raw_extraction = _call_gemini_extract(EXTRACTION_FALLBACK_MODEL, transcript)
            model_used = EXTRACTION_FALLBACK_MODEL

        # Tertiary fallback to Groq Llama if Gemini is completely unavailable
        if raw_extraction is None and GROQ_API_KEY:
            raw_extraction = _call_groq_extract("llama-3.3-70b-versatile", transcript)
            model_used = "groq-llama-3.3-70b-versatile"

    if raw_extraction is None:
        raise RuntimeError(
            "Extraction failed: could not get a response from any extraction model."
        )

    # 4. Verify quotes
    verified = verify_quotes(raw_extraction, transcript)

    # 5. Cache result in SQLite
    set_cached_extraction(
        transcript_hash,
        json.dumps(verified, ensure_ascii=False),
        model_used,
    )

    return {
        "fields": verified,
        "model_name": model_used,
        "cached": False,
    }


# ---------------------------------------------------------------------------
# Test fixture for stubbed testing
# ---------------------------------------------------------------------------

def _test_fixture_extraction(transcript: str) -> Dict[str, Any]:
    """
    Return a deterministic extraction for testing, using actual distinct substrings
    from the given transcript so that quote verification passes by default.
    """
    # Split transcript by common sentence delimiters
    parts = [s.strip() for s in re.split(r'[.،,؟!?\n]+', transcript) if s.strip()]

    # If transcript has fewer than 5 parts, slice it into distinct chunks
    if len(parts) < 5:
        words = transcript.split()
        chunk_size = max(1, len(words) // 5)
        parts = [
            " ".join(words[i * chunk_size : (i + 1) * chunk_size])
            for i in range(5)
        ]

    def pick(idx: int) -> Optional[str]:
        if idx < len(parts) and parts[idx]:
            return parts[idx]
        return None

    return {
        "problem_summary": {
            "verbatim_quote": pick(0),
            "summary": "Detected problem or symptom",
        },
        "possible_causes": {
            "verbatim_quote": pick(1),
            "summary": "Underlying cause identified",
        },
        "checks": {
            "verbatim_quote": pick(2),
            "summary": "Verification checks to perform",
        },
        "solution_steps": {
            "verbatim_quote": pick(3),
            "summary": "Recommended solution steps",
        },
        "cautions": {
            "verbatim_quote": pick(4),
            "summary": "Caution or warning",
            "stated": pick(4) is not None,
        },
    }

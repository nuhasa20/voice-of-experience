import os
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

import anyio
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server.config import (
    MAX_UPLOAD_BYTES,
    AUDIO_DIR,
    BASE_DIR,
    sanitize_message
)
from server.database import init_db, get_connection
from server.audio_convert import convert_audio_to_ogg
from server.stt_pipeline import transcribe_audio_pipeline
from server.extractor import extract_card_fields, contains_unclear_marker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema on startup
    init_db()
    yield

app = FastAPI(
    title="Voice of Experience (صوت الخبرة) API",
    description="Voice-first knowledge preservation backend",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local SPA development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Endpoint for audio transcription:
    1. Validates max file size (10 MB)
    2. Writes upload securely to temporary file
    3. Computes SHA-256 on ORIGINAL incoming bytes
    4. Converts audio to OGG Opus via ffmpeg subprocess argument list
    5. Checks duration limit (max 120s / 2min)
    6. Sends to resilient STT pipeline (Cache -> Gemini Primary -> Secondary -> Groq)
    7. Stores audio locally in private audio/ directory
    """
    try:
        # Read uploaded bytes with size validation
        raw_bytes = await file.read()
        if len(raw_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            )
        if len(raw_bytes) == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded audio file is empty."
            )

        # Extract extension safely
        filename = file.filename or "recording.webm"
        ext = Path(filename).suffix.lower()

        # Convert audio to OGG Opus and compute SHA-256 on original bytes
        try:
            ogg_bytes, duration, original_sha256 = await anyio.to_thread.run_sync(
                convert_audio_to_ogg, raw_bytes, ext
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except RuntimeError as re:
            raise HTTPException(status_code=500, detail=str(re))

        # Save converted audio to private storage
        audio_save_path = AUDIO_DIR / f"{original_sha256}.ogg"
        if not audio_save_path.exists():
            with open(audio_save_path, "wb") as f:
                f.write(ogg_bytes)

        # Transcribe through multi-tier pipeline
        try:
            stt_result = await anyio.to_thread.run_sync(
                transcribe_audio_pipeline, original_sha256, ogg_bytes
            )
        except Exception as e:
            sanitized = sanitize_message(str(e))
            raise HTTPException(status_code=500, detail=f"STT Pipeline Error: {sanitized}")

        return JSONResponse(
            status_code=200,
            content={
                "audio_hash": original_sha256,
                "transcript": stt_result["transcript"],
                "stt_provider": stt_result["stt_provider"],
                "cached": stt_result["cached"],
                "fallback": stt_result.get("fallback", False),
                "duration": duration,
                "audio_url": f"/audio/{original_sha256}.ogg"
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        sanitized = sanitize_message(str(exc))
        raise HTTPException(status_code=500, detail=f"Unexpected error: {sanitized}")


# -----------------------------------------------------------------------
# POST /api/extract — Quote-verified extraction
# -----------------------------------------------------------------------

class ExtractRequest(BaseModel):
    transcript: str
    provider: str = "gemini"  # "gemini" or "test-fixture"

@app.post("/api/extract")
async def extract_card(req: ExtractRequest):
    """
    Extract structured diagnostic fields from the edited transcript,
    verify verbatim quotes, and return verified/unverified/not_mentioned status.
    """
    transcript = req.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is empty.")

    try:
        result = await anyio.to_thread.run_sync(
            extract_card_fields, transcript, req.provider
        )
    except RuntimeError as e:
        sanitized = sanitize_message(str(e))
        raise HTTPException(status_code=500, detail=f"Extraction error: {sanitized}")
    except Exception as exc:
        sanitized = sanitize_message(str(exc))
        raise HTTPException(status_code=500, detail=f"Unexpected extraction error: {sanitized}")

    return JSONResponse(status_code=200, content=result)


# -----------------------------------------------------------------------
# POST /api/cards — Save an approved diagnostic card
# -----------------------------------------------------------------------

class CardFieldPayload(BaseModel):
    verbatim_quote: Optional[str] = None
    summary: Optional[str] = None
    status: str  # "verified", "unverified", "not_mentioned"
    stated: bool = True

class SaveCardRequest(BaseModel):
    expert_name: str
    origin_tag: str  # "Real" or "Demo"
    transcript: str
    audio_hash: str
    audio_duration: float
    stt_provider: str
    approved_by_expert: bool

    problem_summary: CardFieldPayload
    possible_causes: CardFieldPayload
    checks: CardFieldPayload
    solution_steps: CardFieldPayload
    cautions: CardFieldPayload

@app.post("/api/cards")
async def save_card(req: SaveCardRequest):
    """
    Save an approved diagnostic card to SQLite.
    Each call creates a new card with a unique UUID.
    """
    if req.origin_tag not in ("Real", "Demo"):
        raise HTTPException(status_code=400, detail="origin_tag must be 'Real' or 'Demo'.")

    if not req.expert_name.strip():
        raise HTTPException(status_code=400, detail="expert_name is required.")

    # Reject cards where any verified quote contains an [unclear] marker
    field_names = ("problem_summary", "possible_causes", "checks", "solution_steps", "cautions")
    for fn in field_names:
        fld = getattr(req, fn)
        if fld.status == "verified" and fld.verbatim_quote and contains_unclear_marker(fld.verbatim_quote):
            raise HTTPException(
                status_code=400,
                detail=f"Field '{fn}' contains an [unclear] marker and cannot be accepted as a verified quote."
            )

    card_id = f"card_{uuid.uuid4().hex[:12]}"
    audio_path = f"audio/{req.audio_hash}.ogg"

    # Determine has_caution from the cautions field
    has_caution = req.cautions.stated and req.cautions.verbatim_quote is not None

    def _insert():
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cards (
                    id, expert_name, origin_tag,
                    problem_summary_quote, problem_summary,
                    possible_causes_quote, possible_causes,
                    checks_quote, checks,
                    solution_steps_quote, solution_steps,
                    cautions_quote, cautions,
                    has_caution, transcript, audio_path,
                    audio_duration, stt_provider, approved_by_expert
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    req.expert_name.strip(),
                    req.origin_tag,
                    req.problem_summary.verbatim_quote or "",
                    req.problem_summary.summary,
                    req.possible_causes.verbatim_quote or "",
                    req.possible_causes.summary,
                    req.checks.verbatim_quote or "",
                    req.checks.summary,
                    req.solution_steps.verbatim_quote or "",
                    req.solution_steps.summary,
                    req.cautions.verbatim_quote,
                    req.cautions.summary,
                    has_caution,
                    req.transcript,
                    audio_path,
                    req.audio_duration,
                    req.stt_provider,
                    req.approved_by_expert,
                ),
            )
            conn.commit()

    await anyio.to_thread.run_sync(_insert)

    return JSONResponse(
        status_code=201,
        content={
            "id": card_id,
            "message": "Card saved successfully.",
        },
    )


# Serve audio files
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# Serve static frontend SPA
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


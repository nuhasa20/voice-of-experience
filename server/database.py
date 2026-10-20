import sqlite3
from typing import Optional, Dict, Any
from server import config

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.get_db_path()))
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Initialize SQLite database tables as specified in spec.md."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Diagnostic Cards Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            expert_name TEXT NOT NULL,
            origin_tag TEXT CHECK(origin_tag IN ('Real', 'Demo')) NOT NULL,
            problem_summary_quote TEXT NOT NULL,
            problem_summary TEXT,
            possible_causes_quote TEXT NOT NULL,
            possible_causes TEXT,
            checks_quote TEXT NOT NULL,
            checks TEXT,
            solution_steps_quote TEXT NOT NULL,
            solution_steps TEXT,
            cautions_quote TEXT,
            cautions TEXT,
            has_caution BOOLEAN NOT NULL,
            transcript TEXT NOT NULL,
            audio_path TEXT NOT NULL,
            audio_duration REAL NOT NULL,
            stt_provider TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_by_expert BOOLEAN NOT NULL
        );
        """)

        # STT Cache Table (keyed by SHA-256 of ORIGINAL uploaded audio bytes)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stt_cache (
            audio_hash TEXT PRIMARY KEY,
            raw_transcript TEXT NOT NULL,
            stt_provider TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Extraction Cache Table (keyed by SHA-256 of edited transcript)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS extraction_cache (
            transcript_hash TEXT PRIMARY KEY,
            extracted_json TEXT NOT NULL,
            model_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()

def get_cached_transcript(audio_hash: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT audio_hash, raw_transcript, stt_provider, created_at FROM stt_cache WHERE audio_hash = ?",
            (audio_hash,)
        ).fetchone()
        if row:
            return dict(row)
        return None

def get_cached_extraction(transcript_hash: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT transcript_hash, extracted_json, model_name, created_at FROM extraction_cache WHERE transcript_hash = ?",
            (transcript_hash,)
        ).fetchone()
        if row:
            return dict(row)
        return None

def set_cached_extraction(transcript_hash: str, extracted_json: str, model_name: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO extraction_cache (transcript_hash, extracted_json, model_name)
            VALUES (?, ?, ?)
            """,
            (transcript_hash, extracted_json, model_name)
        )
        conn.commit()

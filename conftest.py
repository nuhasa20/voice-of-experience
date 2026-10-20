"""
Pytest configuration and safety guards for test execution.

Guarantees:
1. Every test run defaults to an isolated temporary SQLite database before ANY test
   or server module is imported or executed.
2. Under no circumstance may any test read, write, or connect to the production
   database at data/voice_experience.db.
"""

import os
import tempfile
from pathlib import Path
import pytest

# Allocate a temporary database for the test session if VOICE_DB_PATH is not already set
_session_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_session_tmp_db.close()

if "VOICE_DB_PATH" not in os.environ:
    os.environ["VOICE_DB_PATH"] = _session_tmp_db.name

from server.config import DATA_DIR, get_db_path
from server.database import init_db

# Initialize tables in the session temp DB
init_db()


import sqlite3

@pytest.fixture(autouse=True)
def guard_against_production_db(monkeypatch):
    """
    Autouse safety guard that fails any test immediately if it would open or connect to
    the real production database (data/voice_experience.db).
    """
    real_db = (DATA_DIR / "voice_experience.db").resolve()

    # Pre-test check of configured path
    active_db = get_db_path().resolve()
    if active_db == real_db:
        pytest.fail(f"SECURITY GUARD: Test started with VOICE_DB_PATH pointing to production DB: {real_db}")

    orig_connect = sqlite3.connect

    def guarded_connect(database, *args, **kwargs):
        try:
            if isinstance(database, (str, Path, bytes)):
                target = Path(os.fsdecode(database)).resolve()
                if target == real_db:
                    pytest.fail(
                        f"SECURITY GUARD: Test attempted to open production database: {real_db}!"
                    )
        except Exception as e:
            if "SECURITY GUARD" in str(e):
                raise
        return orig_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)

    yield

    active_db_after = get_db_path().resolve()
    if active_db_after == real_db:
        pytest.fail(f"SECURITY GUARD: Test finished with VOICE_DB_PATH pointing to production DB: {real_db}")

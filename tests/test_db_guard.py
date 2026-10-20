"""
Tests asserting that the test suite can NEVER use or touch the production database.

Verifies:
1. Pointing VOICE_DB_PATH to the real DB path raises a security RuntimeError.
2. Unsetting VOICE_DB_PATH during test execution raises a security RuntimeError.
3. Changing VOICE_DB_PATH dynamically redirects get_connection() to the new database.
4. The real data/voice_experience.db is not modified during test runs.
"""

import os
import sqlite3
import tempfile
from pathlib import Path
import pytest

from server.config import DATA_DIR, get_db_path
from server.database import get_connection


def test_guard_rejects_production_db_path():
    """Attempting to set VOICE_DB_PATH to the production DB path must raise RuntimeError."""
    real_db = (DATA_DIR / "voice_experience.db").resolve()
    saved_env = os.environ.get("VOICE_DB_PATH")

    try:
        os.environ["VOICE_DB_PATH"] = str(real_db)
        with pytest.raises(RuntimeError, match="Security Guard: Tests are strictly forbidden"):
            get_db_path()

        with pytest.raises(RuntimeError, match="Security Guard: Tests are strictly forbidden"):
            get_connection()
    finally:
        if saved_env is not None:
            os.environ["VOICE_DB_PATH"] = saved_env


def test_guard_rejects_unset_voice_db_path():
    """Unsetting VOICE_DB_PATH while tests are running must raise RuntimeError."""
    saved_env = os.environ.get("VOICE_DB_PATH")

    try:
        del os.environ["VOICE_DB_PATH"]
        with pytest.raises(RuntimeError, match="Security Guard: Tests must never use the production"):
            get_db_path()

        with pytest.raises(RuntimeError, match="Security Guard: Tests must never use the production"):
            get_connection()
    finally:
        if saved_env is not None:
            os.environ["VOICE_DB_PATH"] = saved_env


def test_dynamic_db_path_resolution():
    """Updating VOICE_DB_PATH at runtime immediately updates get_connection target."""
    tmp1 = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp2 = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp1.close()
    tmp2.close()
    saved_env = os.environ.get("VOICE_DB_PATH")

    try:
        os.environ["VOICE_DB_PATH"] = tmp1.name
        conn1 = get_connection()
        db_file_1 = conn1.execute("PRAGMA database_list").fetchall()[0][2]
        conn1.close()
        assert Path(db_file_1).resolve() == Path(tmp1.name).resolve()

        os.environ["VOICE_DB_PATH"] = tmp2.name
        conn2 = get_connection()
        db_file_2 = conn2.execute("PRAGMA database_list").fetchall()[0][2]
        conn2.close()
        assert Path(db_file_2).resolve() == Path(tmp2.name).resolve()
    finally:
        if saved_env is not None:
            os.environ["VOICE_DB_PATH"] = saved_env
        try:
            os.unlink(tmp1.name)
            os.unlink(tmp2.name)
        except OSError:
            pass


def test_sqlite3_connect_to_production_db_fails():
    """Direct calls to sqlite3.connect on the real database must trigger test failure via conftest guard."""
    real_db = (DATA_DIR / "voice_experience.db").resolve()
    with pytest.raises(pytest.fail.Exception, match="SECURITY GUARD: Test attempted to open production database"):
        sqlite3.connect(str(real_db))


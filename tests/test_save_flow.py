"""
Unit tests for the Save Diagnostic Card flow and DOM element binding.

Verifies:
1. DOM elements queried in contribution.js (specifically saveSuccessMsg and saveSuccessBanner)
   exist in index.html to prevent TypeError: Cannot set properties of undefined (setting 'textContent').
2. Card save endpoint persists to SQLite correctly without calling external APIs.
3. Save flow prevents duplicate card creation on retry or while a save is in-flight.
"""

import os
import re
import tempfile
import pytest
from pathlib import Path
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

# Create an isolated temporary SQLite DB for test isolation
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["VOICE_DB_PATH"] = _tmp_db.name

from server.main import app
from server.database import init_db, get_connection

init_db()
client = TestClient(app)

BASE_DIR = Path(__file__).resolve().parent.parent


def test_dom_elements_in_contribution_js_exist_in_html():
    """Ensure every getElementById call in contribution.js has a corresponding element in index.html."""
    html_path = BASE_DIR / "static" / "index.html"
    js_path = BASE_DIR / "static" / "js" / "contribution.js"

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    # Find all document.getElementById calls
    ids_in_js = re.findall(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)", js_content)
    assert len(ids_in_js) > 0

    # Specifically check the previously buggy save elements
    assert "saveSuccessMsg" in ids_in_js, "saveSuccessMsg must be initialized via getElementById"
    assert "saveSuccessBanner" in ids_in_js

    missing_ids = [el_id for el_id in set(ids_in_js) if not soup.find(id=el_id)]
    assert not missing_ids, f"The following IDs in contribution.js are missing from index.html: {missing_ids}"


def test_save_state_guards_in_contribution_js():
    """Ensure duplicate save guards are implemented in contribution.js."""
    js_path = BASE_DIR / "static" / "js" / "contribution.js"
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    # Check for duplicate prevention variables
    assert "this.savedCardId" in js
    assert "this.isSaving" in js

    # Check that submitSaveCard guards on isSaving or savedCardId
    assert "this.isSaving || this.savedCardId" in js

    # Check that catch block only re-enables button if card was not already saved
    assert "!this.savedCardId" in js


def test_save_card_endpoint_and_db_persistence():
    """Test POST /api/cards succeeds and persists card row in SQLite."""
    payload = {
        "expert_name": "Test Expert",
        "origin_tag": "Demo",
        "transcript": "اختبار فحص الموديل والداتا",
        "audio_hash": "test_audio_hash_12345",
        "audio_duration": 30.0,
        "stt_provider": "test-fixture",
        "approved_by_expert": True,
        "problem_summary": {
            "verbatim_quote": "الموديل يعطي accuracy عالية",
            "summary": "High accuracy in test",
            "status": "verified",
            "stated": True
        },
        "possible_causes": {
            "verbatim_quote": "تسرب البيانات",
            "summary": "Data leakage",
            "status": "verified",
            "stated": True
        },
        "checks": {
            "verbatim_quote": None,
            "summary": None,
            "status": "not_mentioned",
            "stated": False
        },
        "solution_steps": {
            "verbatim_quote": None,
            "summary": None,
            "status": "not_mentioned",
            "stated": False
        },
        "cautions": {
            "verbatim_quote": None,
            "summary": None,
            "status": "not_mentioned",
            "stated": False
        }
    }

    resp = client.post("/api/cards", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    card_id = data["id"]
    assert card_id.startswith("card_")

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        assert row is not None
        assert dict(row)["expert_name"] == "Test Expert"
        assert dict(row)["origin_tag"] == "Demo"

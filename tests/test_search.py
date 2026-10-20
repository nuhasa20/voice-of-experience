"""
tests/test_search.py - Tests for Stage 4 Character N-gram TF-IDF Search Engine.

Validates:
1. Ranking of a known query.
2. Below-threshold fallback ({"results": [], "message": "I don't know"}).
3. Empty database returns fallback.
4. Arabic and English queries.
5. Alias expansion (e.g. "داتا ليكج" matches "data leakage", "NaN" matches "قيم ناقصة").
6. POST /api/search endpoint with top-3 cap and required metadata fields:
   audio_path, expert_name, origin_tag, approved_by_expert.
7. Rebuild index on card save.
8. Strictly operates on temp DB; conftest.py guard stays on.
"""

import os
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Allocate isolated temporary DB for this test file
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["VOICE_DB_PATH"] = _tmp_db.name

from server.main import app
from server.database import init_db, get_connection
from server.search import search_cards, search_engine, expand_query
from server.config import get_db_path, DATA_DIR, SEARCH_THRESHOLD

init_db()
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure clean table state for each test in this module."""
    with get_connection() as conn:
        conn.execute("DELETE FROM cards")
        conn.commit()
    search_engine.invalidate()
    yield


def _insert_card(
    card_id: str,
    expert_name: str,
    origin_tag: str,
    problem_quote: str,
    problem_summary: str,
    causes_quote: str = "",
    causes_summary: str = "",
    checks_quote: str = "",
    checks_summary: str = "",
    solution_quote: str = "",
    solution_summary: str = "",
    cautions_quote: str = "",
    cautions_summary: str = "",
    transcript: str = "",
    audio_path: str = "audio/sample.ogg",
    approved_by_expert: bool = True
):
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
                expert_name,
                origin_tag,
                problem_quote,
                problem_summary,
                causes_quote,
                causes_summary,
                checks_quote,
                checks_summary,
                solution_quote,
                solution_summary,
                cautions_quote,
                cautions_summary,
                bool(cautions_quote),
                transcript,
                audio_path,
                45.0,
                "test-stt",
                approved_by_expert
            )
        )
        conn.commit()
    search_engine.invalidate()


def test_conftest_guard_active():
    """Verify test runs on isolated temp DB, never on production DB."""
    active = get_db_path().resolve()
    real_db = (DATA_DIR / "voice_experience.db").resolve()
    assert active != real_db
    assert active.exists()


def test_empty_db_search():
    """Searching an empty database returns 'I don't know' fallback."""
    res = search_cards("data leakage in model")
    assert res["results"] == []
    assert res.get("message") == "I don't know"

    # API endpoint also returns 200 with fallback
    resp = client.post("/api/search", json={"query": "data leakage"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["message"] == "I don't know"


def test_ranking_of_known_query():
    """Known query matches correct card and ranks it highest with score >= SEARCH_THRESHOLD."""
    _insert_card(
        card_id="card_leakage_1",
        expert_name="Eng. Sara",
        origin_tag="Demo",
        problem_quote="الموديل يعطي accuracy عالية بشكل مريب في test وبعدين يطيح",
        problem_summary="Data leakage causing misleadingly high test accuracy",
        causes_quote="المعلومات من test دخلت في التدريب من غير ما نقصدوا",
        causes_summary="Information from test set entered training unintentionally",
        solution_quote="نقسموا البيانات أول شيء وبعدين نعملوا processing على train فقط",
        transcript="تسرب البيانات data leakage في الموديل",
        audio_path="audio/leakage.ogg"
    )
    _insert_card(
        card_id="card_drift_2",
        expert_name="Eng. Momen",
        origin_tag="Real",
        problem_quote="انحراف حساسات الضغط في خطوط الأنابيب",
        problem_summary="Pressure sensor drift in oil pipelines",
        causes_quote="تراكم الرواسب على مستشعر الضغط بعد شهور تشغيل",
        causes_summary="Sediment build up on sensor",
        transcript="انحراف الحساس sensor drift بعد فترة طويلة",
        audio_path="audio/drift.ogg"
    )

    res = search_cards("data leakage in test split")
    assert len(res["results"]) > 0
    top = res["results"][0]
    assert top["id"] == "card_leakage_1"
    assert top["score"] >= SEARCH_THRESHOLD
    assert "score" in top
    assert top["expert_name"] == "Eng. Sara"
    assert top["origin_tag"] == "Demo"
    assert top["approved_by_expert"] is True


def test_below_threshold_fallback():
    """Query completely unrelated to preserved engineering cards returns fallback."""
    _insert_card(
        card_id="card_leakage_1",
        expert_name="Eng. Sara",
        origin_tag="Demo",
        problem_quote="الموديل يعطي accuracy عالية",
        problem_summary="Data leakage causing misleadingly high test accuracy",
        transcript="data leakage in model"
    )

    # Completely unrelated query
    res = search_cards("how to replace a drill bit on a mechanical rig in the desert")
    assert res["results"] == []
    assert res.get("message") == "I don't know"


def test_arabic_and_english_queries():
    """Search matches both natural Arabic queries and English queries."""
    _insert_card(
        card_id="card_sensor_drift",
        expert_name="Eng. Ahmed",
        origin_tag="Real",
        problem_quote="قراءات الحساسات فيها انحراف تدريجي عن المعيار",
        problem_summary="Gradual sensor drift in telemetry instrumentation",
        transcript="sensor telemetry drift قراءات المستشعر غير دقيقة"
    )

    # Arabic query
    res_ar = search_cards("انحراف في قراءات الحساسات")
    assert len(res_ar["results"]) > 0
    assert res_ar["results"][0]["id"] == "card_sensor_drift"
    assert res_ar["results"][0]["score"] >= SEARCH_THRESHOLD

    # English query
    res_en = search_cards("sensor telemetry drift")
    assert len(res_en["results"]) > 0
    assert res_en["results"][0]["id"] == "card_sensor_drift"
    assert res_en["results"][0]["score"] >= SEARCH_THRESHOLD


def test_alias_expansion():
    """Alias expansion expands query only, bridging Arabic transliterations to English terms."""
    # Test expand_query helper directly
    expanded_leakage = expand_query("داتا ليكج")
    assert "data leakage" in expanded_leakage
    assert "تسريب" in expanded_leakage

    expanded_nan = expand_query("قيم ناقصة في الجدول")
    assert "nan" in expanded_nan
    assert "missing" in expanded_nan

    # Test retrieval with alias expansion
    # Card uses English terms
    _insert_card(
        card_id="card_ml_leakage",
        expert_name="Eng. Sara",
        origin_tag="Demo",
        problem_quote="High accuracy in test set due to data leakage",
        problem_summary="Data leakage in cross validation",
        transcript="data leakage occurred during preprocessing"
    )

    # User searches using Arabic transliteration "داتا ليكج"
    res = search_cards("داتا ليكج")
    assert len(res["results"]) > 0
    assert res["results"][0]["id"] == "card_ml_leakage"
    assert res["results"][0]["score"] >= SEARCH_THRESHOLD

    # Card uses Arabic terms for missing values
    _insert_card(
        card_id="card_missing_vals",
        expert_name="Eng. Khaled",
        origin_tag="Real",
        problem_quote="البيانات تحتوي على قيم ناقصة تسبب توقف المعالجة",
        problem_summary="Missing values causing pipeline crash",
        transcript="الصفوف فيها قيم ناقصة كثيرة"
    )

    # User searches using English term "NaN"
    res_nan = search_cards("NaN in pipeline data")
    assert len(res_nan["results"]) > 0
    assert res_nan["results"][0]["id"] == "card_missing_vals"


def test_api_search_endpoint_contract():
    """POST /api/search returns correct contract, top 3 cap, and required fields."""
    for i in range(5):
        _insert_card(
            card_id=f"card_leakage_{i}",
            expert_name=f"Expert {i}",
            origin_tag="Real" if i % 2 == 0 else "Demo",
            problem_quote=f"مشكلة تسرب البيانات في الموديل رقم {i}",
            problem_summary=f"Data leakage issue variant {i}",
            transcript=f"data leakage problem {i}",
            audio_path=f"audio/leakage_{i}.ogg",
            approved_by_expert=True
        )

    resp = client.post("/api/search", json={"query": "data leakage"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    # Must cap at top 3
    assert len(data["results"]) <= 3

    top = data["results"][0]
    # Check all required fields from prompt:
    # "Include audio_path, expert_name, origin_tag, approved_by_expert"
    assert "score" in top
    assert "audio_path" in top
    assert "expert_name" in top
    assert "origin_tag" in top
    assert "approved_by_expert" in top
    assert top["origin_tag"] in ("Real", "Demo")
    assert isinstance(top["approved_by_expert"], bool)


def test_rebuild_index_on_save_card():
    """When a new card is saved via POST /api/cards, it is immediately indexable in search."""
    payload = {
        "expert_name": "Eng. Dynamic",
        "origin_tag": "Real",
        "transcript": "فقدان إشارة الكابل البحري telemetry submarine cable",
        "audio_hash": "dynamic_hash_789",
        "audio_duration": 25.0,
        "stt_provider": "gemini-3.5-flash",
        "approved_by_expert": True,
        "problem_summary": {
            "verbatim_quote": "فقدان إشارة الكابل البحري",
            "summary": "Submarine cable telemetry signal loss",
            "status": "verified",
            "stated": True
        },
        "possible_causes": {
            "verbatim_quote": None,
            "summary": None,
            "status": "not_mentioned",
            "stated": False
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

    save_resp = client.post("/api/cards", json=payload)
    assert save_resp.status_code == 201

    # Search immediately for the newly saved card
    search_resp = client.post("/api/search", json={"query": "submarine cable telemetry"})
    assert search_resp.status_code == 200
    res_data = search_resp.json()
    assert len(res_data["results"]) > 0
    assert res_data["results"][0]["expert_name"] == "Eng. Dynamic"
    assert res_data["results"][0]["score"] >= SEARCH_THRESHOLD


def test_get_cards_library_endpoint():
    """GET /api/cards returns all cards for initial library view."""
    _insert_card(
        card_id="card_101",
        expert_name="Eng. Test 1",
        origin_tag="Real",
        problem_quote="مشكلة عطل في الصمام",
        problem_summary="Valve failure"
    )
    _insert_card(
        card_id="card_102",
        expert_name="Eng. Test 2",
        origin_tag="Demo",
        problem_quote="مشكلة في المحرك",
        problem_summary="Motor issue"
    )

    resp = client.get("/api/cards")
    assert resp.status_code == 200
    data = resp.json()
    assert "cards" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["cards"]) == 2
    assert data["cards"][0]["approved_by_expert"] is True


def test_search_dom_elements_exist_in_index_html():
    """Verify all element IDs queried in search.js exist in static/index.html."""
    from bs4 import BeautifulSoup
    import re

    base_dir = Path(__file__).resolve().parent.parent
    html_path = base_dir / "static" / "index.html"
    js_path = base_dir / "static" / "js" / "search.js"

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    ids_in_js = re.findall(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)", js_content)
    assert len(ids_in_js) > 0

    missing_ids = [el_id for el_id in set(ids_in_js) if not soup.find(id=el_id)]
    assert not missing_ids, f"The following IDs in search.js are missing from index.html: {missing_ids}"

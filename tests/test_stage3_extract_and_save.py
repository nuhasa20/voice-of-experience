"""
Stage 3 tests for /api/extract and /api/cards endpoints.

Rules:
- Uses test-fixture extraction provider (no real LLM calls)
- Uses a temporary isolated SQLite database (VOICE_DB_PATH env var)
- Never writes fake rows into the real database or cache
"""

import os
import json
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Create a temp DB before any import of server modules
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["VOICE_DB_PATH"] = _tmp_db.name

from server.main import app
from server.database import init_db, get_connection

# Initialize schema in the temp DB
init_db()

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared test transcript (real cached entry from stt_cache, used verbatim)
# ---------------------------------------------------------------------------

TRANSCRIPT_SHORT = (
    "تسرب البيانات المشكلة اللي شفتها مرات الموديل يعطي accuracy عالية بشكل مريب في التست "
    "وبعدين في الواقع يطيح السبب غالباً data leakage يعني المعلومات من التست دخلت في التدريب "
    "من غير ما نقصد مثلاً لما نعمل normalization على كل البيانات قبل ما نقسم التست والترين "
    "أو لما نفس الحالة تتكرر في الجهتين باش نتأكد نشوف هل في صفوف مكررة بين المجموعتين "
    "ونشوف هل النتيجة عالية على غير العادة نقسم البيانات أولاً وبعدين نديرو normalization "
    "على الترين بس وتحذير إذا كان الأداء مثالي بزيادة لازم تشك فيه أول حاجة"
)

FAKE_AUDIO_HASH = "aabbccddeeff0011aabbccddeeff0011aabbccddeeff0011aabbccddeeff0011"


# ---------------------------------------------------------------------------
# POST /api/extract tests
# ---------------------------------------------------------------------------

class TestExtractEndpoint:
    def test_extract_returns_five_fields(self):
        resp = client.post("/api/extract", json={
            "transcript": TRANSCRIPT_SHORT,
            "provider": "test-fixture",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "fields" in data
        assert "model_name" in data
        assert data["model_name"] == "test-fixture"
        for field in ["problem_summary", "possible_causes", "checks", "solution_steps", "cautions"]:
            assert field in data["fields"], f"Missing field: {field}"

    def test_extract_field_has_required_keys(self):
        resp = client.post("/api/extract", json={
            "transcript": TRANSCRIPT_SHORT,
            "provider": "test-fixture",
        })
        assert resp.status_code == 200
        fields = resp.json()["fields"]
        for field_name, field_data in fields.items():
            assert "status" in field_data, f"{field_name} missing status"
            assert "display_text" in field_data, f"{field_name} missing display_text"
            assert "stated" in field_data, f"{field_name} missing stated"

    def test_extract_verified_fields_have_verbatim_quote(self):
        resp = client.post("/api/extract", json={
            "transcript": TRANSCRIPT_SHORT,
            "provider": "test-fixture",
        })
        assert resp.status_code == 200
        fields = resp.json()["fields"]
        verified_count = sum(1 for f in fields.values() if f["status"] == "verified")
        assert verified_count >= 4, f"Expected at least 4 verified fields, got {verified_count}"

    def test_extract_not_mentioned_field_has_correct_display(self):
        # A very short transcript should cause cautions to be not_mentioned
        very_short = "الموديل يعطي خطأ"
        resp = client.post("/api/extract", json={
            "transcript": very_short,
            "provider": "test-fixture",
        })
        assert resp.status_code == 200
        fields = resp.json()["fields"]
        # Check that not_mentioned fields have appropriate display text
        for field_data in fields.values():
            if field_data["status"] == "not_mentioned":
                assert field_data["display_text"] in (
                    "Not mentioned",
                    "No caution stated by the expert",
                )

    def test_extract_empty_transcript_returns_400(self):
        resp = client.post("/api/extract", json={
            "transcript": "   ",
            "provider": "test-fixture",
        })
        assert resp.status_code == 400

    def test_extract_caches_result(self):
        transcript = "نص تجريبي للاختبار وهو نص بسيط جداً يعطي accuracy عالية جداً وداتا ليكيج داتا leakage في الترين والتست من غير ما نقصد ذلك"
        # First call — should not be cached
        resp1 = client.post("/api/extract", json={
            "transcript": transcript,
            "provider": "test-fixture",
        })
        assert resp1.status_code == 200
        assert resp1.json()["cached"] == False

        # Second call with same transcript — should be cached
        resp2 = client.post("/api/extract", json={
            "transcript": transcript,
            "provider": "test-fixture",
        })
        assert resp2.status_code == 200
        assert resp2.json()["cached"] == True

    def test_unverified_display_text(self):
        """Quote that can't be verified should show 'Could not be verified – please edit'."""
        from server.extractor import verify_quotes
        # Inject an extraction where one quote is NOT in the transcript
        fake_extraction = {
            "problem_summary": {
                "verbatim_quote": "هذا النص ليس في الترانسكريبت على الإطلاق وهو اختراع كامل",
                "summary": "fake",
            },
            "possible_causes": {"verbatim_quote": None, "summary": None, "stated": False},
            "checks": {"verbatim_quote": None, "summary": None, "stated": False},
            "solution_steps": {"verbatim_quote": None, "summary": None, "stated": False},
            "cautions": {"verbatim_quote": None, "summary": None, "stated": False},
        }
        transcript = "الموديل يعطي خطأ في التدريب"
        result = verify_quotes(fake_extraction, transcript)
        assert result["problem_summary"]["status"] == "unverified"
        assert result["problem_summary"]["display_text"] == "Could not be verified – please edit"

    def test_duplicate_quotes_rejected(self):
        """Same quote used for two fields must both be marked unverified."""
        from server.extractor import verify_quotes
        same_quote = "الموديل يعطي accuracy عالية"
        fake_extraction = {
            "problem_summary": {"verbatim_quote": same_quote, "summary": "s1"},
            "possible_causes": {"verbatim_quote": same_quote, "summary": "s2"},
            "checks": {"verbatim_quote": None, "summary": None, "stated": False},
            "solution_steps": {"verbatim_quote": None, "summary": None, "stated": False},
            "cautions": {"verbatim_quote": None, "summary": None, "stated": False},
        }
        transcript = "الموديل يعطي accuracy عالية في التدريب والتست"
        result = verify_quotes(fake_extraction, transcript)
        # Both that used the same quote must be rejected
        assert result["problem_summary"]["status"] == "unverified"
        assert result["possible_causes"]["status"] == "unverified"

    def test_length_cap_60_percent(self):
        """Quote longer than 60% of transcript must be marked unverified."""
        from server.extractor import verify_quotes, normalize_arabic
        transcript = "الموديل يعطي accuracy عالية بشكل مريب في التست"
        norm_t = normalize_arabic(transcript)
        # Quote that is 80% of normalized transcript → exceeds cap
        quote_len = int(0.8 * len(norm_t))
        long_quote = transcript  # exact full transcript (100%)
        fake_extraction = {
            "problem_summary": {"verbatim_quote": long_quote, "summary": "s"},
            "possible_causes": {"verbatim_quote": None, "summary": None, "stated": False},
            "checks": {"verbatim_quote": None, "summary": None, "stated": False},
            "solution_steps": {"verbatim_quote": None, "summary": None, "stated": False},
            "cautions": {"verbatim_quote": None, "summary": None, "stated": False},
        }
        result = verify_quotes(fake_extraction, transcript)
        # The quote IS a substring and IS the full transcript (100% > 60%)
        assert result["problem_summary"]["status"] == "unverified"
        assert "exceeds_length_cap" in result["problem_summary"]["reason"]

    def test_unclear_marker_in_quote_is_rejected(self):
        """Quotes containing [unclear] must never be accepted as verified."""
        from server.extractor import verify_quotes
        transcript = "الموديل يعطي accuracy عالية [unclear] بشكل مريب في التست وبعدين يطيح"
        fake_extraction = {
            "problem_summary": {
                "verbatim_quote": "accuracy عالية [unclear] بشكل مريب",
                "summary": "Suspicious accuracy",
            },
            "possible_causes": {"verbatim_quote": None, "summary": None, "stated": False},
            "checks": {"verbatim_quote": None, "summary": None, "stated": False},
            "solution_steps": {"verbatim_quote": None, "summary": None, "stated": False},
            "cautions": {"verbatim_quote": None, "summary": None, "stated": False},
        }
        result = verify_quotes(fake_extraction, transcript)
        assert result["problem_summary"]["status"] == "unverified"
        assert result["problem_summary"]["display_text"] == "Could not be verified – please edit"
        assert "contains_unclear_marker" in result["problem_summary"]["reason"]

    def test_arabic_unclear_marker_in_quote_is_rejected(self):
        """Quotes containing [غير واضح] must also be rejected."""
        from server.extractor import verify_quotes
        transcript = "الموديل يعطي خطأ [غير واضح] في النتائج النهائية"
        fake_extraction = {
            "problem_summary": {
                "verbatim_quote": "خطأ [غير واضح] في النتائج",
                "summary": "Error in results",
            },
            "possible_causes": {"verbatim_quote": None, "summary": None, "stated": False},
            "checks": {"verbatim_quote": None, "summary": None, "stated": False},
            "solution_steps": {"verbatim_quote": None, "summary": None, "stated": False},
            "cautions": {"verbatim_quote": None, "summary": None, "stated": False},
        }
        result = verify_quotes(fake_extraction, transcript)
        assert result["problem_summary"]["status"] == "unverified"
        assert "contains_unclear_marker" in result["problem_summary"]["reason"]


# ---------------------------------------------------------------------------
# POST /api/cards tests
# ---------------------------------------------------------------------------

def _make_verified_field(quote: str, summary: str = "Test summary") -> dict:
    return {
        "verbatim_quote": quote,
        "summary": summary,
        "status": "verified",
        "stated": True,
    }


def _make_not_mentioned_field(cautions: bool = False) -> dict:
    return {
        "verbatim_quote": None,
        "summary": None,
        "status": "not_mentioned",
        "stated": False,
    }


def _save_card_payload(expert_name: str = "Test Engineer", audio_hash: str = FAKE_AUDIO_HASH) -> dict:
    return {
        "expert_name": expert_name,
        "origin_tag": "Demo",
        "transcript": TRANSCRIPT_SHORT,
        "audio_hash": audio_hash,
        "audio_duration": 45.0,
        "stt_provider": "test-fixture",
        "approved_by_expert": True,
        "problem_summary": _make_verified_field("الموديل يعطي accuracy عالية"),
        "possible_causes": _make_verified_field("data leakage في التدريب"),
        "checks": _make_verified_field("نشوف هل في صفوف مكررة"),
        "solution_steps": _make_verified_field("نقسم البيانات أولاً"),
        "cautions": _make_not_mentioned_field(cautions=True),
    }


class TestSaveCardEndpoint:
    def test_save_card_returns_201_with_id(self):
        resp = client.post("/api/cards", json=_save_card_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["id"].startswith("card_")
        assert "message" in data

    def test_save_card_persists_to_db(self):
        resp = client.post("/api/cards", json=_save_card_payload("Eng. Sara"))
        assert resp.status_code == 201
        card_id = resp.json()["id"]
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        assert row is not None
        assert dict(row)["expert_name"] == "Eng. Sara"

    def test_two_saves_produce_two_separate_cards(self):
        """Saving twice must create two distinct cards with different IDs."""
        resp1 = client.post("/api/cards", json=_save_card_payload("Expert A", "a" * 64))
        resp2 = client.post("/api/cards", json=_save_card_payload("Expert B", "b" * 64))
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        id1 = resp1.json()["id"]
        id2 = resp2.json()["id"]
        assert id1 != id2

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, expert_name FROM cards WHERE id IN (?, ?)",
                (id1, id2)
            ).fetchall()
        assert len(rows) == 2
        names = {dict(r)["expert_name"] for r in rows}
        assert names == {"Expert A", "Expert B"}

    def test_save_card_invalid_origin_tag_returns_400(self):
        payload = _save_card_payload()
        payload["origin_tag"] = "Invalid"
        resp = client.post("/api/cards", json=payload)
        assert resp.status_code == 400

    def test_save_card_empty_name_returns_400(self):
        payload = _save_card_payload()
        payload["expert_name"] = "   "
        resp = client.post("/api/cards", json=payload)
        assert resp.status_code == 400

    def test_save_card_has_caution_when_stated(self):
        """When cautions field is stated with a quote, has_caution should be True."""
        payload = _save_card_payload()
        payload["cautions"] = _make_verified_field("إذا كان الأداء مثالي شك فيه أول")
        payload["cautions"]["stated"] = True
        resp = client.post("/api/cards", json=payload)
        assert resp.status_code == 201
        card_id = resp.json()["id"]
        with get_connection() as conn:
            row = dict(conn.execute("SELECT has_caution FROM cards WHERE id = ?", (card_id,)).fetchone())
        assert row["has_caution"] == True

    def test_save_card_rejects_unclear_marker_in_verified_quote(self):
        """Saving a card where a verified quote contains [unclear] must return 400."""
        payload = _save_card_payload()
        payload["problem_summary"] = {
            "verbatim_quote": "الموديل يعطي [unclear] في النتائج",
            "summary": "Problem with unclear word",
            "status": "verified",
            "stated": True,
        }
        resp = client.post("/api/cards", json=payload)
        assert resp.status_code == 400
        assert "[unclear] marker" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# STT pipeline lockdown & timestamp stripping tests
# ---------------------------------------------------------------------------

class TestSttPipelineLockdown:
    def test_database_module_does_not_export_set_cached_transcript(self):
        """set_cached_transcript must not exist in server.database to prevent external scripts from writing to stt_cache."""
        import server.database
        assert not hasattr(server.database, "set_cached_transcript")

    def test_strip_leading_timestamp(self):
        """Leading timestamps like 00:00, [00:00], (00:00) must be cleanly stripped."""
        from server.stt_pipeline import strip_leading_timestamp
        assert strip_leading_timestamp("00:00 قيم الـ NaN") == "قيم الـ NaN"
        assert strip_leading_timestamp("[00:00] قيم الـ NaN") == "قيم الـ NaN"
        assert strip_leading_timestamp("(01:23) - قيم الـ NaN") == "قيم الـ NaN"
        assert strip_leading_timestamp("00:00:15: قيم الـ NaN") == "قيم الـ NaN"
        assert strip_leading_timestamp("قيم الـ NaN من غير توقيت") == "قيم الـ NaN من غير توقيت"

    def test_save_to_stt_cache_rejects_unauthorized_provider(self):
        """Internal STT cache writer must reject unauthorized/fixture providers."""
        from server.stt_pipeline import _save_to_stt_cache
        with pytest.raises(ValueError, match="Unauthorized STT provider"):
            _save_to_stt_cache("somehash", "transcript text", "fake-provider-name")

    def test_secondary_model_fallback_is_cached(self, monkeypatch):
        """
        Simulate primary Gemini model failing and secondary Gemini model answering.
        Verify that the secondary model's result is cached and stt_provider is secondary.
        """
        from server.config import STT_PRIMARY_MODEL, STT_SECONDARY_MODEL
        from server.stt_pipeline import transcribe_audio_pipeline
        from server.database import get_cached_transcript

        test_audio_hash = "mock_hash_fallback_secondary_001"
        test_ogg_bytes = b"fake_ogg_bytes_for_secondary_test"
        secondary_transcript = "قيم الـ NaN فئة كاملة ما ظهرتش في التدريب"

        def mock_call_gemini_stt(model: str, ogg_bytes: bytes, max_retries: int = 3):
            if model == STT_PRIMARY_MODEL:
                # Primary model fails (e.g. 503 or quota exceeded)
                return None
            elif model == STT_SECONDARY_MODEL:
                # Secondary model succeeds
                return secondary_transcript
            return None

        monkeypatch.setattr("server.stt_pipeline.call_gemini_stt", mock_call_gemini_stt)

        result = transcribe_audio_pipeline(test_audio_hash, test_ogg_bytes)

        # Verify pipeline response
        assert result["stt_provider"] == STT_SECONDARY_MODEL
        assert result["transcript"] == secondary_transcript
        assert result["cached"] is False
        assert result["fallback"] is False

        # Verify result is persisted to stt_cache in the isolated test DB
        cached_row = get_cached_transcript(test_audio_hash)
        assert cached_row is not None
        assert cached_row["raw_transcript"] == secondary_transcript
        assert cached_row["stt_provider"] == STT_SECONDARY_MODEL


# ---------------------------------------------------------------------------
# Teardown: remove temp DB after all tests
# ---------------------------------------------------------------------------

def teardown_module(module):
    try:
        os.unlink(_tmp_db.name)
    except Exception:
        pass

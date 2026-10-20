"""
server/search.py - Character N-Gram TF-IDF Search Engine for Diagnostic Cards.

Implements Stage 4 per devpost/spec.md Component 7 & prd.md Section 4.2.
- Character n-gram TF-IDF (scikit-learn, analyzer="char_wb", ngram_range=(3,5))
  fitted exclusively on card documents.
- Arabic-aware text normalization using server.normalizer.normalize_arabic.
- Query-only alias expansion table (bilingual technical terms & dialect transliterations).
- Calibrated anti-hallucination fallback: returns {"results": [], "message": "I don't know"}
  when top similarity score is below SEARCH_THRESHOLD.
- Rebuilds or refreshes index dynamically as cards are added.
- Zero embeddings, zero external API calls, 100% offline scikit-learn.
"""

import re
from typing import List, Dict, Any, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from server import config
from server.normalizer import normalize_arabic
from server.database import get_connection


# Small alias table to expand queries only (bidirectional technical terms / transliterations)
ALIAS_TABLE: Dict[str, List[str]] = {
    # Data leakage / تسريب البيانات
    "data leakage": ["داتا ليكج", "داتا ليكيج", "تسريب", "تسرب البيانات", "تسرب"],
    "leakage": ["داتا ليكج", "تسريب", "تسرب البيانات"],
    "داتا ليكج": ["data leakage", "leakage", "تسريب", "تسرب البيانات"],
    "داتا ليكيج": ["data leakage", "leakage", "تسريب", "تسرب البيانات"],
    "تسريب": ["data leakage", "تسرب البيانات", "leakage"],
    "تسرب": ["data leakage", "تسريب", "leakage"],
    "تسرب البيانات": ["data leakage", "داتا ليكج"],

    # Missing values / NaN / قيم ناقصة
    "nan": ["قيم ناقصة", "قيمة ناقصة", "missing", "missing value", "ماسينج فاليو", "قيم مفقودة"],
    "missing": ["nan", "قيم ناقصة", "missing value", "ماسينج فاليو", "قيم مفقودة"],
    "missing value": ["nan", "قيم ناقصة", "ماسينج فاليو"],
    "missing values": ["nan", "قيم ناقصة", "ماسينج فاليو"],
    "قيم ناقصة": ["nan", "missing", "missing value", "ماسينج فاليو"],
    "قيمة ناقصة": ["nan", "missing", "missing value"],
    "قيم مفقودة": ["nan", "missing", "missing value"],
    "ماسينج فاليو": ["nan", "missing", "missing value", "قيم ناقصة"],

    # Model / الموديل
    "model": ["موديل", "الموديل", "مودل", "المودل"],
    "موديل": ["model"],
    "مودل": ["model"],

    # Train / تدريب
    "train": ["ترين", "الترين", "تدريب"],
    "training": ["تدريب", "ترين"],
    "ترين": ["train", "تدريب"],

    # Test / اختبار
    "test": ["تست", "التست", "اختبار"],
    "testing": ["اختبار", "تست"],
    "تست": ["test", "اختبار"],

    # Accuracy / دقة
    "accuracy": ["أكيسيري", "اكيسيري", "دقة"],
    "أكيسيري": ["accuracy", "دقة"],
    "اكيسيري": ["accuracy", "دقة"],

    # Normalization / تطبيع
    "normalization": ["نورميزايليشن", "تطبيع"],
    "نورميزايليشن": ["normalization"],

    # Processing / معالجة
    "processing": ["بروسيسينج", "معالجة"],
    "preprocessing": ["بروسيسينج", "معالجة أولية"],
    "بروسيسينج": ["processing"],

    # Sensor / مستشعر / حساس
    "sensor": ["حساس", "مستشعر"],
    "sensors": ["حساسات", "مستشعرات"],
    "حساس": ["sensor"],
    "حساسات": ["sensors", "sensor"],

    # Drift / انحراف
    "drift": ["درفت", "انحراف"],
    "درفت": ["drift"],
    "انحراف": ["drift"],

    # Telemetry / قياسات
    "telemetry": ["تيليميتري", "قياسات عن بعد", "بيانات الحساسات"],
    "تيليميتري": ["telemetry"],

    # Outlier / قيم شاذة
    "outlier": ["قيمة شاذة", "قيم شاذة"],
    "outliers": ["قيم شاذة"],
    "شاذة": ["outlier", "outliers"],
}


def expand_query(query: str) -> str:
    """
    Expands the user query using domain-specific aliases (bilingual Arabic/English synonyms).
    Expands the query ONLY; card searchable text is not altered by aliases.
    """
    if not query:
        return ""

    norm_q = normalize_arabic(query)
    expanded_tokens = [norm_q]

    # Match normalized alias keys
    for key, synonyms in ALIAS_TABLE.items():
        norm_key = normalize_arabic(key)
        if not norm_key:
            continue
        pattern = r'(?:\b|^)' + re.escape(norm_key) + r'(?:\b|$)'
        if re.search(pattern, norm_q):
            for syn in synonyms:
                norm_syn = normalize_arabic(syn)
                if norm_syn and norm_syn not in expanded_tokens:
                    expanded_tokens.append(norm_syn)

    return " ".join(expanded_tokens)


def build_card_search_text(card: Dict[str, Any]) -> str:
    """
    Concatenate card text fields:
    problem, causes, checks, solution, cautions (quotes and summaries), and transcript,
    then apply Arabic normalization.
    """
    fields = [
        card.get("problem_summary_quote") or "",
        card.get("problem_summary") or "",
        card.get("possible_causes_quote") or "",
        card.get("possible_causes") or "",
        card.get("checks_quote") or "",
        card.get("checks") or "",
        card.get("solution_steps_quote") or "",
        card.get("solution_steps") or "",
        card.get("cautions_quote") or "",
        card.get("cautions") or "",
        card.get("transcript") or "",
    ]
    raw_doc = " ".join(str(f).strip() for f in fields if f and str(f).strip())
    return normalize_arabic(raw_doc)


def fetch_all_cards() -> List[Dict[str, Any]]:
    """Fetch all diagnostic cards from active SQLite database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM cards ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


class SearchEngine:
    """
    Scikit-learn character n-gram TF-IDF search engine.
    Fitted exclusively on diagnostic card texts.
    """

    def __init__(self):
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.card_vectors = None
        self.cards: List[Dict[str, Any]] = []
        self._dirty: bool = True

    def invalidate(self) -> None:
        """Mark index as dirty to force rebuild on next search."""
        self._dirty = True

    def build_index(self, cards: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Build and fit the TF-IDF vectorizer over the given or fetched cards.
        """
        if cards is None:
            cards = fetch_all_cards()

        self.cards = cards
        self._dirty = False

        if not self.cards:
            self.vectorizer = None
            self.card_vectors = None
            return

        documents = [build_card_search_text(c) for c in self.cards]

        # Check if at least one document has non-empty text
        if not any(doc.strip() for doc in documents):
            self.vectorizer = None
            self.card_vectors = None
            return

        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1
        )
        self.card_vectors = self.vectorizer.fit_transform(documents)

    def search(
        self,
        query: str,
        threshold: Optional[float] = None,
        top_k: int = 3,
        rebuild: bool = True
    ) -> Dict[str, Any]:
        """
        Search diagnostic cards using character n-gram cosine similarity.

        Returns:
            {"results": [top 3 cards with score]}
            or
            {"results": [], "message": "I don't know"} if top score < threshold or empty DB.
        """
        if threshold is None:
            threshold = config.SEARCH_THRESHOLD

        clean_query = query.strip() if query else ""
        if not clean_query:
            return {"results": [], "message": "I don't know"}

        if rebuild or self._dirty or self.vectorizer is None:
            self.build_index()

        # If DB is empty or vectorizer could not be fitted
        if not self.cards or self.vectorizer is None or self.card_vectors is None:
            return {"results": [], "message": "I don't know"}

        # Expand query using alias table and normalize
        expanded = expand_query(clean_query)
        norm_query = normalize_arabic(expanded)
        if not norm_query.strip():
            return {"results": [], "message": "I don't know"}

        # Vectorize query ONLY (transform, never fit)
        query_vector = self.vectorizer.transform([norm_query])

        # Cosine similarity
        sim_scores = cosine_similarity(query_vector, self.card_vectors)[0]
        if len(sim_scores) == 0:
            return {"results": [], "message": "I don't know"}

        max_score = float(np.max(sim_scores))
        if max_score < threshold:
            return {"results": [], "message": "I don't know"}

        # Rank cards descending by score
        ranked_indices = np.argsort(sim_scores)[::-1]
        results = []
        for idx in ranked_indices:
            score = float(sim_scores[idx])
            if score < threshold:
                break

            card_dict = dict(self.cards[idx])
            card_dict["score"] = round(score, 4)
            card_dict["approved_by_expert"] = bool(card_dict.get("approved_by_expert"))
            card_dict["has_caution"] = bool(card_dict.get("has_caution"))
            results.append(card_dict)
            if len(results) >= top_k:
                break

        return {"results": results}


# Module-level default search engine instance
search_engine = SearchEngine()


def search_cards(
    query: str,
    threshold: Optional[float] = None,
    top_k: int = 3,
    rebuild: bool = True
) -> Dict[str, Any]:
    """Helper entrypoint for searching cards."""
    return search_engine.search(query=query, threshold=threshold, top_k=top_k, rebuild=rebuild)

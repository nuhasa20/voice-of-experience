#!/usr/bin/env python3
"""
scripts/eval_search.py - Search Evaluation & Threshold Calibration Script.

Reads eval/queries.json (list of objects with fields:
id, split, kind, query, expected_card_ids).

Supports:
    python3 scripts/eval_search.py --split tuning
    python3 scripts/eval_search.py --split heldout

Evaluates retrieval performance against the active cards database using
character n-gram TF-IDF cosine similarity.

A query passes if:
- top-1 card is in expected_card_ids (when expected_card_ids is non-empty)
- or, when expected_card_ids is empty, if the system says "I don't know" (top score < threshold).
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server import config
from server.search import SearchEngine, expand_query
from server.normalizer import normalize_arabic
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def load_eval_queries(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Evaluate search retrieval on eval/queries.json")
    parser.add_argument(
        "--split",
        choices=["tuning", "heldout"],
        default="tuning",
        help="Evaluation split to run ('tuning' or 'heldout')"
    )
    args = parser.parse_args()

    eval_file = PROJECT_ROOT / "eval" / "queries.json"
    if not eval_file.exists():
        print(f"Error: Evaluation queries file not found at: {eval_file}")
        sys.exit(1)

    all_queries = load_eval_queries(eval_file)
    split_queries = [q for q in all_queries if q.get("split") == args.split]

    if not split_queries:
        print(f"Error: No queries found for split '{args.split}' in {eval_file}.")
        sys.exit(1)

    # Initialize and fit search engine on active database cards
    engine = SearchEngine()
    engine.build_index()

    cards = engine.cards
    if not cards or engine.vectorizer is None or engine.card_vectors is None:
        print("Error: No cards found in the database. Ensure data/voice_experience.db contains cards.")
        sys.exit(1)

    current_threshold = config.SEARCH_THRESHOLD
    print("=" * 105)
    print(f"Voice of Experience — Search Evaluation (Split: '{args.split.upper()}', Active Threshold: {current_threshold:.2f})")
    print(f"Database Cards: {len(cards)} | Total Split Queries: {len(split_queries)}")
    print("=" * 105)

    eval_rows = []

    for item in split_queries:
        qid = item.get("id", "")
        kind = item.get("kind", "")
        query_text = (item.get("query") or "").strip()
        expected_ids = item.get("expected_card_ids", [])
        is_in_scope = len(expected_ids) > 0

        # Run TF-IDF scoring
        expanded_q = expand_query(query_text)
        norm_q = normalize_arabic(expanded_q)

        if not norm_q.strip():
            top_score = 0.0
            top_card = None
        else:
            q_vec = engine.vectorizer.transform([norm_q])
            scores = cosine_similarity(q_vec, engine.card_vectors)[0]
            best_idx = int(np.argmax(scores))
            top_score = float(scores[best_idx])
            top_card = cards[best_idx]

        top_card_id = top_card["id"] if top_card else None

        # Pass / Fail evaluation under active threshold
        # If top_score < current_threshold: system output is "I don't know"
        if top_score < current_threshold:
            system_output = "I don't know"
            passed = (len(expected_ids) == 0)
        else:
            system_output = top_card_id
            passed = (len(expected_ids) > 0 and top_card_id in expected_ids)

        eval_rows.append({
            "id": qid,
            "kind": kind,
            "query": query_text,
            "expected_ids": expected_ids,
            "is_in_scope": is_in_scope,
            "top_score": top_score,
            "top_card": top_card,
            "top_card_id": top_card_id,
            "system_output": system_output,
            "passed": passed
        })

    # Print per-query report
    print(f"{'ID':<4} | {'Kind':<22} | {'Top Score':<9} | {'Status':<6} | {'Top Card':<20} | {'Query'}")
    print("-" * 105)
    passed_count = 0
    for r in eval_rows:
        status_str = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            passed_count += 1
        top_card_display = r["top_card_id"] or "None"
        q_display = (r["query"][:36] + "...") if len(r["query"]) > 39 else r["query"]
        print(f"{r['id']:<4} | {r['kind']:<22} | {r['top_score']:<9.4f} | {status_str:<6} | {top_card_display:<20} | {q_display}")

    print("-" * 105)
    total_q = len(eval_rows)
    acc = (passed_count / total_q) * 100 if total_q > 0 else 0
    print(f"Summary: {passed_count}/{total_q} passed ({acc:.1f}%) at active threshold {current_threshold:.2f}")

    # Threshold Range & Calibration Analysis (specifically for tuning split)
    if args.split == "tuning":
        print("\n" + "=" * 105)
        print("Tuning Split — Threshold Range & Calibration Analysis:")
        print("=" * 105)

        in_scope_rows = [r for r in eval_rows if r["is_in_scope"]]
        neg_rows = [r for r in eval_rows if not r["is_in_scope"]]

        # Check ranking correctness for in-scope queries
        ranking_errors = []
        for r in in_scope_rows:
            if r["top_card_id"] not in r["expected_ids"]:
                ranking_errors.append(r)

        max_neg_score = max((r["top_score"] for r in neg_rows), default=0.0)
        min_pos_score = min((r["top_score"] for r in in_scope_rows), default=1.0)

        print(f"In-scope queries (N={len(in_scope_rows)}):   Min Top Score = {min_pos_score:.4f}, Max Top Score = {max(r['top_score'] for r in in_scope_rows):.4f}")
        print(f"Negative queries (N={len(neg_rows)}):   Min Top Score = {min(r['top_score'] for r in neg_rows):.4f}, Max Top Score = {max_neg_score:.4f}")
        print("-" * 105)

        if not ranking_errors and max_neg_score < min_pos_score:
            print("PERFECT SEPARATION ACHIEVED:")
            print(f"  All in-scope queries have correct top-1 cards.")
            print(f"  Max negative score ({max_neg_score:.4f}) < Min in-scope score ({min_pos_score:.4f}).")
            print(f"  Exact range of thresholds classifying ALL tuning queries correctly:")
            print(f"    ({max_neg_score:.4f}, {min_pos_score:.4f}]")
            midpoint = (max_neg_score + min_pos_score) / 2.0
            print(f"  Recommended Midpoint Threshold: {midpoint:.4f}")
        else:
            print("Scores overlap or ranking mismatch found. Finding best trade-off threshold:")
            if ranking_errors:
                print(f"  Note: {len(ranking_errors)} in-scope query(s) did not match expected card at top-1:")
                for re in ranking_errors:
                    print(f"    - Query {re['id']}: matched '{re['top_card_id']}', expected {re['expected_ids']}")

            # Test candidate thresholds between sorted unique scores
            all_scores = sorted(set(r["top_score"] for r in eval_rows))
            candidate_thresholds = [0.0]
            for idx in range(len(all_scores) - 1):
                candidate_thresholds.append((all_scores[idx] + all_scores[idx + 1]) / 2.0)
            candidate_thresholds.append(all_scores[-1] + 0.01)

            best_t = current_threshold
            best_correct = -1
            best_errors = []

            for t in candidate_thresholds:
                correct = 0
                errors = []
                for r in eval_rows:
                    if r["is_in_scope"]:
                        if r["top_score"] >= t and r["top_card_id"] in r["expected_ids"]:
                            correct += 1
                        else:
                            if r["top_score"] < t:
                                errors.append((r["id"], f"False Negative (score {r['top_score']:.4f} < {t:.4f})"))
                            else:
                                errors.append((r["id"], f"Wrong top-1 card ('{r['top_card_id']}' not in {r['expected_ids']})"))
                    else:
                        if r["top_score"] < t:
                            correct += 1
                        else:
                            errors.append((r["id"], f"False Positive (score {r['top_score']:.4f} >= {t:.4f})"))

                if correct > best_correct:
                    best_correct = correct
                    best_t = t
                    best_errors = errors

            print(f"\n  Best Trade-Off Threshold: τ = {best_t:.4f}")
            print(f"  Accuracy: {best_correct}/{len(eval_rows)} correct ({best_correct/len(eval_rows)*100:.1f}%)")
            print(f"  Listing errors at best trade-off (τ = {best_t:.4f}):")
            for qid, err_desc in best_errors:
                print(f"    - Query {qid}: {err_desc}")

        print("=" * 105)


if __name__ == "__main__":
    main()

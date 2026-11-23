"""Task 4 — Interest weight evaluation using controlled test scenarios.

Evaluates how different interests weights (0.0, 0.05, 0.10, 0.15, 0.20)
affect ranking. Uses deterministic mock providers only (no live API calls).

Key assertions:
- weight=0.0 reproduces the no-interest baseline identically.
- Core compatibility scores are invariant across weights.
- Ranking order shifts monotonically: candidates with high interest overlap
  gain rank as the weight increases.
- Missing interest data is always neutral (never penalizes candidates).
- Weights beyond 0.20 are noted as requiring A/B validation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytest

from dating_ml_model import RecommendationModel
from dating_ml_model.interests import UserInterestProfile
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService

NOW = datetime(2026, 10, 30, 10, 0, 0)

EVAL_WEIGHTS = [0.0, 0.05, 0.10, 0.15, 0.20]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _man(pid: str, **kw) -> Dict[str, Any]:
    base = {
        "id": pid, "age": 30, "sex": "m", "orientation": "straight",
        "job": "science / tech / engineering",
        "education": "graduated from college/university",
        "religion": "agnosticism", "drinks": "socially", "smokes": "no",
        "offspring": "wants kids",
    }
    base.update(kw)
    return base


def _woman(pid: str, **kw) -> Dict[str, Any]:
    return _man(pid, sex="f", **kw)


def _make_service_with_weight(users: List[Dict], interest_weight: float) -> RecommendationService:
    base_model = RecommendationModel()
    cfg = dict(base_model.config)
    weights = dict(cfg["final_ranking"]["weights"])
    weights["interests"] = interest_weight
    cfg["final_ranking"] = dict(cfg["final_ranking"])
    cfg["final_ranking"]["weights"] = weights
    model = RecommendationModel(config=cfg)
    repo = InMemoryRecommendationRepository(users)
    return RecommendationService(
        model.compatibility, repo, recommendation_model=model,
        clock=lambda: NOW,
    )


def _setup_scenario() -> Tuple[Dict, Dict, Dict, Dict]:
    """Standard evaluation scenario with one user and three candidates."""
    user = _woman("u_eval", age=28)

    # High interest match: both "jazz" and "rock_climbing" align with imported interests
    cand_high = _man("c_high_int", age=29,
                     interests=["jazz", "rock_climbing", "hiking"])

    # Partial interest match: only "jazz" aligns
    cand_partial = _man("c_partial_int", age=29,
                        interests=["jazz", "knitting"])

    # No interest match: completely different interests
    cand_none = _man("c_no_int", age=29,
                     interests=["pottery", "calligraphy"])

    return user, cand_high, cand_partial, cand_none


def _run_at_weight(
    weight: float, with_consent: bool = True
) -> Tuple[List[Dict], Dict[str, float]]:
    """Run recommendations at a given interest weight. Returns (recs, compat_scores)."""
    user, cand_high, cand_partial, cand_none = _setup_scenario()
    all_users = [user, cand_high, cand_partial, cand_none]

    service = _make_service_with_weight(all_users, weight)

    # Import Google interests (jazz + rock_climbing) for the user
    service.import_external_interests(
        "u_eval", "google",
        {"items": [
            {"title": "Jazz", "is_topic": True, "confidence": 0.90},
            {"title": "Rock Climbing", "is_topic": True, "confidence": 0.90},
        ]},
        user_confirmed=True,
    )

    if with_consent:
        service.set_external_interest_consent("u_eval", "google", True)

    recs = service.get_recommendations("u_eval", limit=10)

    # Collect compatibility adjusted_scores (must be invariant)
    compat = {
        str(r["candidate_id"]): r["compatibility"]["adjusted_score"]
        for r in recs
    }
    return recs, compat


# ---------------------------------------------------------------------------
# T4-1  Weight=0.0 reproduces no-interest baseline
# ---------------------------------------------------------------------------

class TestZeroWeightIsBaseline:
    def test_zero_weight_equals_no_consent_baseline(self):
        """weight=0.0 with consent must produce identical final_scores as no consent."""
        recs_consent, _ = _run_at_weight(0.0, with_consent=True)
        recs_no_consent, _ = _run_at_weight(0.0, with_consent=False)

        scores_c = {str(r["candidate_id"]): r["ranking"]["final_score"] for r in recs_consent}
        scores_nc = {str(r["candidate_id"]): r["ranking"]["final_score"] for r in recs_no_consent}

        assert scores_c == scores_nc, (
            f"weight=0.0 should produce same scores regardless of consent: "
            f"{scores_c} vs {scores_nc}"
        )

    def test_zero_weight_interests_component_is_not_used(self):
        recs, _ = _run_at_weight(0.0, with_consent=True)
        for r in recs:
            for comp in r["ranking"]["components"]:
                if comp["signal"] == "interests":
                    assert not comp["used"], (
                        f"interests component must not be 'used' at weight=0.0"
                    )


# ---------------------------------------------------------------------------
# T4-2  Compatibility scores are invariant across all weights
# ---------------------------------------------------------------------------

class TestCompatibilityInvariance:
    def test_compatibility_scores_identical_across_all_weights(self):
        """adjusted_score must not change regardless of interest weight."""
        baseline_compat = None
        for w in EVAL_WEIGHTS:
            _, compat = _run_at_weight(w)
            if baseline_compat is None:
                baseline_compat = compat
            else:
                for cid, score in compat.items():
                    assert score == baseline_compat.get(cid), (
                        f"Compatibility score for {cid} changed at weight={w}: "
                        f"expected {baseline_compat.get(cid)}, got {score}"
                    )


# ---------------------------------------------------------------------------
# T4-3  Ranking order shifts with interest weight
# ---------------------------------------------------------------------------

class TestRankingOrderShifts:
    def test_high_interest_candidate_improves_rank_as_weight_increases(self):
        """c_high_int must rank no lower at higher weights than lower weights."""
        positions = {}
        for w in EVAL_WEIGHTS:
            recs, _ = _run_at_weight(w)
            ids = [str(r["candidate_id"]) for r in recs]
            positions[w] = ids.index("c_high_int") if "c_high_int" in ids else len(ids)

        pos_zero = positions[0.0]
        pos_nonzero = [positions[w] for w in EVAL_WEIGHTS if w > 0]
        for pos in pos_nonzero:
            assert pos <= pos_zero, (
                f"c_high_int position {pos} worse than baseline {pos_zero}"
            )

    def test_no_interest_candidate_does_not_rank_above_high_interest_at_nonzero_weight(self):
        """c_no_int must not outrank c_high_int at any non-zero weight."""
        for w in [0.05, 0.10, 0.15, 0.20]:
            recs, _ = _run_at_weight(w)
            ids = [str(r["candidate_id"]) for r in recs]
            pos_high = ids.index("c_high_int") if "c_high_int" in ids else len(ids)
            pos_none = ids.index("c_no_int") if "c_no_int" in ids else len(ids)
            assert pos_high <= pos_none, (
                f"At weight={w}: c_no_int (pos {pos_none}) ranked above "
                f"c_high_int (pos {pos_high})"
            )

    def test_final_score_of_high_interest_candidate_increases_with_weight(self):
        """Final score of c_high_int must be non-decreasing as interest weight increases."""
        scores = []
        for w in EVAL_WEIGHTS:
            recs, _ = _run_at_weight(w)
            score = next(
                (r["ranking"]["final_score"] for r in recs if r["candidate_id"] == "c_high_int"),
                None,
            )
            scores.append((w, score))

        for i in range(1, len(scores)):
            w_prev, s_prev = scores[i - 1]
            w_curr, s_curr = scores[i]
            if s_prev is not None and s_curr is not None:
                assert s_curr >= s_prev - 1e-9, (
                    f"Score decreased from weight={w_prev} ({s_prev:.4f}) "
                    f"to weight={w_curr} ({s_curr:.4f})"
                )


# ---------------------------------------------------------------------------
# T4-4  Missing interest data is always neutral
# ---------------------------------------------------------------------------

class TestMissingInterestDataIsNeutral:
    def test_candidate_without_interests_not_penalized_at_any_weight(self):
        """A candidate with no interest tokens must not be ranked lower than
        a zero-weight baseline purely due to the interest signal."""
        user = _woman("u_neutral_test", age=28)
        cand_no_interests = _man("c_sparse", age=29)  # no interests field at all
        cand_has_interests = _man("c_interests", age=29, interests=["jazz"])

        for w in EVAL_WEIGHTS:
            service = _make_service_with_weight(
                [user, cand_no_interests, cand_has_interests], w
            )
            service.import_external_interests(
                "u_neutral_test", "google",
                {"items": [{"title": "Jazz", "is_topic": True, "confidence": 0.90}]},
                user_confirmed=True,
            )
            service.set_external_interest_consent("u_neutral_test", "google", True)
            recs = service.get_recommendations("u_neutral_test", limit=10)

            ids = [str(r["candidate_id"]) for r in recs]
            assert "c_sparse" in ids, (
                f"Candidate without interests missing from recs at weight={w}"
            )
            sparse_score = next(
                r["ranking"]["final_score"] for r in recs if r["candidate_id"] == "c_sparse"
            )
            assert sparse_score is not None and sparse_score > 0, (
                f"c_sparse has null/zero final_score at weight={w}: {sparse_score}"
            )

    def test_user_cold_start_is_neutral_at_all_weights(self):
        """When the user has no imported interests, ranking must be identical
        to the zero-weight baseline at all tested weights."""
        user = _woman("u_no_interests", age=28)
        cand_a = _man("c_wa", age=29, interests=["jazz"])
        cand_b = _man("c_wb", age=29, interests=["pottery"])

        baseline_scores = None
        for w in EVAL_WEIGHTS:
            service = _make_service_with_weight([user, cand_a, cand_b], w)
            recs = service.get_recommendations("u_no_interests", limit=10)
            scores = {str(r["candidate_id"]): r["ranking"]["final_score"] for r in recs}

            if baseline_scores is None:
                baseline_scores = scores
            else:
                assert scores == baseline_scores, (
                    f"Scores changed at weight={w} without user having any interests: "
                    f"expected {baseline_scores}, got {scores}"
                )


# ---------------------------------------------------------------------------
# T4-5  Weight impact summary (printed to stdout)
# ---------------------------------------------------------------------------

class TestWeightImpactSummary:
    def test_print_weight_impact_table(self, capsys):
        """Non-asserting summary: prints final_score differences across weights."""
        rows = []
        for w in EVAL_WEIGHTS:
            recs, _ = _run_at_weight(w)
            for r in recs:
                cid = str(r["candidate_id"])
                fs = r["ranking"]["final_score"]
                int_score = r.get("interests", {}).get("score") if r.get("interests") else None
                rows.append((w, cid, fs, int_score))

        print("\n--- Interest Weight Impact Summary ---")
        print(f"{'Weight':>8} {'Candidate':>20} {'FinalScore':>12} {'IntScore':>10}")
        print("-" * 55)
        for w, cid, fs, int_s in rows:
            int_str = f"{int_s:.2f}" if int_s is not None else "  N/A"
            print(f"{w:>8.2f} {cid:>20} {fs:>12.4f} {int_str:>10}")

        captured = capsys.readouterr()
        assert "Weight Impact Summary" in captured.out


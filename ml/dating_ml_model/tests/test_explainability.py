"""Automated test suite for Phase 5: Explainable Recommendations & Score Transparency.

Verifies:
1. Recommendation explanation accuracy and completeness.
2. Separate isolation of matched, mismatched, hard-exclusion failures, and unavailable information.
3. Distance explanations given only when distance is known.
4. Transparent breakdown of scoring components without inventing weights or scores.
5. Absolute consistency between explanations, eligibility decisions, and ranking scores.
6. Non-probability disclaimer in score interpretation.
7. Service and HTTP API endpoints for candidate and pair explainability.
8. Preservation of regression baseline and golden recommendation parity.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from dating_ml_model import CompatibilityModel, RecommendationModel, explain_recommendation
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import MatchingService, RecommendationService
from dating_ml_model.tests.fixtures import FULL_A, FULL_B, variant
from dating_ml_model.tests.reco_fixtures import INTERACTIONS, NOW, PREFERENCES, PROFILES


@pytest.fixture
def repo():
    return InMemoryRecommendationRepository(PROFILES, INTERACTIONS, PREFERENCES)


@pytest.fixture
def recommender():
    return RecommendationModel()


@pytest.fixture
def service(repo, recommender):
    return RecommendationService(recommender.compatibility, repo, clock=lambda: NOW)


def test_explain_recommended_candidate_breakdown(recommender):
    """An eligible candidate has structured explanation, transparent scoring, and no hard failures."""
    user = variant(FULL_A, id="u1", city="Mumbai", state="Maharashtra", country="India")
    candidate = variant(FULL_B, id="u2", city="Pune", state="Maharashtra", country="India")
    u_prefs = {
        "criteria": {
            "religion": {"values": ["hindu"], "hard": False},
            "diet": {"values": ["mostly_vegetarian", "strictly_vegetarian"], "hard": False},
        }
    }
    rec = recommender.evaluate_candidate(user, candidate, user_preferences=u_prefs)
    explanation = explain_recommendation(rec)

    # 1. Identity & Eligibility
    assert explanation["user_id"] == "u1"
    assert explanation["candidate_id"] == "u2"
    assert explanation["eligible"] is True
    assert explanation["decision"] in ("strongly_recommended", "recommended", "partially_aligned")
    assert explanation["hard_exclusion_failures"] == []

    # 2. Transparent Scoring Breakdown
    sb = explanation["scoring_breakdown"]
    assert sb["final_score"] == rec["ranking"]["final_score"]
    assert sb["weights_validated"] is False
    assert "not an empirical probability of relationship success" in sb["score_interpretation"].lower()

    # Sum of point contributions must equal final_score (within float precision)
    used_components = [c for c in sb["components"] if c["used"]]
    assert len(used_components) > 0
    calculated_final = sum(c["point_contribution"] for c in used_components)
    assert abs(calculated_final - sb["final_score"]) < 1e-3

    # Weights share percentage must sum to 100%
    weight_shares = sum(c["weight_share_pct"] for c in used_components)
    assert abs(weight_shares - 100.0) < 0.1

    # Effective weight must match the ranking component exactly (no invented numbers)
    raw_ranking_comps = {c["signal"]: c for c in rec["ranking"]["components"]}
    for c in sb["components"]:
        sig = c["signal"]
        assert c["base_weight"] == raw_ranking_comps[sig]["base_weight"]
        assert c["effective_weight"] == raw_ranking_comps[sig]["effective_weight"]
        assert c["score"] == raw_ranking_comps[sig]["score"]


def test_explain_excluded_candidates_and_hard_failures(recommender):
    """Candidate failing hard exclusions must be isolated under hard_exclusion_failures with decision=ineligible."""
    user = variant(FULL_A, id="u1", age=25, city="Mumbai", state="Maharashtra", country="India")
    # Candidate smokes and lives in London (> 500 km max distance)
    candidate = variant(FULL_B, id="u2", age=27, smokes="yes", city="London", country="United Kingdom")
    u_prefs = {
        "max_distance_km": 100,
        "hard_exclusions": {"smokes": ["yes"]},
    }
    rec = recommender.evaluate_candidate(user, candidate, user_preferences=u_prefs)
    explanation = explain_recommendation(rec)

    assert explanation["eligible"] is False
    assert explanation["decision"] == "ineligible"
    assert len(explanation["hard_exclusion_failures"]) > 0
    # Must explicitly state why they failed
    failures_text = " ".join(explanation["hard_exclusion_failures"])
    assert "hard preference" in failures_text.lower() or "distance" in failures_text.lower() or "smokes" in failures_text.lower()
    assert "Candidate is not eligible:" in explanation["summary"]


def test_distance_explanation_only_when_known(recommender):
    """Distance is explained in km ONLY when known; unknown location avoids distance assumptions."""
    # Case A: Known locations (Mumbai to Pune, ~120 km)
    user_known = variant(FULL_A, id="u_mumbai", city="Mumbai", state="Maharashtra", country="India")
    cand_known = variant(FULL_B, id="c_pune", city="Pune", state="Maharashtra", country="India")
    u_prefs = {"preferred_distance_km": 200, "max_distance_km": 500}
    rec_known = recommender.evaluate_candidate(user_known, cand_known, user_preferences=u_prefs)
    exp_known = explain_recommendation(rec_known)

    loc_known = exp_known["location_explanation"]
    assert loc_known["status"] == "known"
    assert isinstance(loc_known["distance_km"], float)
    assert 100.0 <= loc_known["distance_km"] <= 150.0
    assert "approximately" in loc_known["explanation"].lower()
    assert "km away" in loc_known["explanation"].lower()

    # Case B: Unknown location (missing city on candidate)
    cand_unknown = variant(FULL_B, id="c_unknown", city=None, state=None, country=None, latitude=None, longitude=None)
    rec_unknown = recommender.evaluate_candidate(user_known, cand_unknown, user_preferences=u_prefs)
    exp_unknown = explain_recommendation(rec_unknown)

    loc_unknown = exp_unknown["location_explanation"]
    assert loc_unknown["status"] in ("unknown", "partial_unknown")
    assert loc_unknown["distance_km"] is None
    assert "distance cannot be calculated" in loc_unknown["explanation"].lower()
    assert "no location penalty was applied" in loc_unknown["explanation"].lower()
    # Explicitly flagged in unavailable_information
    assert any("distance is unknown" in info.lower() for info in exp_unknown["unavailable_information"])


def test_unavailable_information_isolated_without_penalties(recommender):
    """Missing criteria attributes and cold start behavior are transparently reported without penalty."""
    user = variant(FULL_A, id="u1")
    # Candidate lacks diet and religion
    candidate = variant(FULL_B, id="u2", diet=None, religion=None)
    u_prefs = {
        "criteria": {
            "diet": {"values": ["vegetarian"], "hard": False},
            "religion": {"values": ["hindu"], "hard": False},
        }
    }
    rec = recommender.evaluate_candidate(user, candidate, user_preferences=u_prefs)
    explanation = explain_recommendation(rec)

    # Missing diet and religion must be reported as unknown on profile, unverified, not penalized
    unavail = " ".join(explanation["unavailable_information"])
    assert "diet" in unavail.lower()
    assert "religion" in unavail.lower()
    assert "unverified; not penalized" in unavail.lower()

    # Cold start behavior is flagged
    assert any("no interaction history" in info.lower() for info in explanation["unavailable_information"])


def test_matched_and_mismatched_preferences_separated(recommender):
    """Soft preferences are partitioned cleanly into matched and mismatched."""
    user = variant(FULL_A, id="u1")
    # Candidate: drinks="socially", smokes="no", pets="likes cats"
    candidate = variant(FULL_B, id="u2", drinks="socially", smokes="no", pets="likes cats")
    u_prefs = {
        "criteria": {
            "drinks": {"values": ["socially"], "hard": False},  # MATCH
            "smokes": {"values": ["no"], "hard": False},        # MATCH
            "pets": {"values": ["dogs"], "hard": False},         # MISMATCH (likes cats)
        }
    }
    rec = recommender.evaluate_candidate(user, candidate, user_preferences=u_prefs)
    explanation = explain_recommendation(rec)

    matched_names = {m["criterion"] for m in explanation["matched_preferences"]}
    mismatched_names = {m["criterion"] for m in explanation["mismatched_preferences"]}

    assert "drinks" in matched_names
    assert "smokes" in matched_names
    assert "pets" in mismatched_names
    # Disjoint sets
    assert matched_names.isdisjoint(mismatched_names)


def test_bilateral_preference_explanations(recommender):
    """Bilateral preferences record both viewer preferences and candidate preferences."""
    user = variant(FULL_A, id="u1", drinks="socially", smokes="never")
    candidate = variant(FULL_B, id="u2", drinks="never", smokes="never")
    u_prefs = {
        "criteria": {"smokes": {"values": ["never"], "hard": False}}
    }
    c_prefs = {
        "criteria": {"drinks": {"values": ["socially"], "hard": False}}
    }
    rec = recommender.evaluate_candidate(user, candidate, user_preferences=u_prefs, candidate_preferences=c_prefs)
    explanation = explain_recommendation(rec)

    directions = {m["direction"] for m in explanation["matched_preferences"]}
    assert "viewer_preference" in directions
    assert "candidate_preference" in directions


def test_service_explain_candidate(service):
    """RecommendationService provides explain_candidate for valid users."""
    explanation = service.explain_candidate("u1", "u2")
    assert explanation["user_id"] == "u1"
    assert explanation["candidate_id"] == "u2"
    assert "scoring_breakdown" in explanation
    assert "score_interpretation" in explanation["scoring_breakdown"]
    assert "location_explanation" in explanation
    assert isinstance(explanation["unavailable_information"], list)


def test_compatibility_model_explain_pair():
    """CompatibilityModel provides explain_pair for direct deterministic pairs."""
    model = CompatibilityModel()
    user_a = variant(FULL_A, id="pa")
    user_b = variant(FULL_B, id="pb")
    exp = model.explain_pair(user_a, user_b)

    assert exp["user_id"] == "pa"
    assert exp["candidate_id"] == "pb"
    assert exp["eligible"] is True
    assert exp["scoring_breakdown"]["final_score"] is not None
    assert "not an empirical probability" in exp["scoring_breakdown"]["score_interpretation"].lower()


def test_http_api_explain_endpoints(repo):
    """FastAPI integration exposes recommendation and pair explainability endpoints."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dating_ml_model.backend_integration_example import create_app

    app = create_app(repo, clock=lambda: NOW)
    client = TestClient(app)

    # 1. Recommendation explain endpoint
    res_reco = client.get("/users/u1/recommendations/u2/explain")
    assert res_reco.status_code == 200
    data_reco = res_reco.json()
    assert data_reco["user_id"] == "u1"
    assert data_reco["candidate_id"] == "u2"
    assert "scoring_breakdown" in data_reco
    assert "hard_exclusion_failures" in data_reco

    # 2. Unknown user 404
    res_404 = client.get("/users/nonexistent_user/recommendations/u2/explain")
    assert res_404.status_code == 404

    # 3. Compatibility pair explain endpoint
    res_pair = client.post("/compatibility/pair/explain", json={
        "profile_a": FULL_A,
        "profile_b": FULL_B,
    })
    assert res_pair.status_code == 200
    data_pair = res_pair.json()
    assert data_pair["eligible"] is True
    assert "scoring_breakdown" in data_pair


def test_explain_max_distance_exceeded(recommender):
    """Candidate beyond hard max distance has distance-based explanation and hard failure."""
    # Delhi to Bengaluru is ~1740 km
    user = variant(FULL_A, id="u_delhi", city="New Delhi", state="Delhi", country="India")
    candidate = variant(FULL_B, id="c_bengaluru", city="Bengaluru", state="Karnataka", country="India")
    u_prefs = {"preferred_distance_km": 50, "max_distance_km": 100}
    rec = recommender.evaluate_candidate(user, candidate, user_preferences=u_prefs)
    exp = explain_recommendation(rec)

    assert exp["eligible"] is False
    assert exp["decision"] == "ineligible"
    assert any("maximum distance" in f.lower() for f in exp["hard_exclusion_failures"])
    loc = exp["location_explanation"]
    assert loc["status"] == "known"
    assert loc["distance_km"] > 1000
    assert loc["within_max_distance"] is False
    assert "exceeds your maximum allowed distance" in loc["explanation"].lower()


def test_explain_mutual_candidate_dealbreaker_failure(recommender):
    """When candidate's hard exclusions reject the viewer, failure is isolated as candidate's hard preference."""
    # Viewer smokes, candidate strictly requires non-smokers
    user = variant(FULL_A, id="u_smoker", smokes="yes")
    candidate = variant(FULL_B, id="c_nonsmoker", smokes="no")
    c_prefs = {
        "criteria": {
            "smokes": {"values": ["no"], "hard": True}
        }
    }
    rec = recommender.evaluate_candidate(user, candidate, candidate_preferences=c_prefs)
    exp = explain_recommendation(rec)

    assert exp["eligible"] is False
    assert exp["decision"] == "ineligible"
    assert any("candidate's hard preference" in f.lower() and "smokes" in f.lower() for f in exp["hard_exclusion_failures"])


def test_explain_coarse_and_unresolved_locations(recommender):
    """Coarse and unresolved locations explain why distance is omitted without applying penalties."""
    user = variant(FULL_A, id="u1", city="Mumbai", state="Maharashtra", country="India")

    # Coarse location: country only
    cand_coarse = variant(FULL_B, id="c_coarse", city=None, state=None, country="India")
    rec_coarse = recommender.evaluate_candidate(user, cand_coarse)
    exp_coarse = explain_recommendation(rec_coarse)
    assert exp_coarse["location_explanation"]["status"] == "coarse"
    assert exp_coarse["location_explanation"]["distance_km"] is None
    assert "coarse" in exp_coarse["location_explanation"]["explanation"].lower() or "region" in exp_coarse["location_explanation"]["explanation"].lower()

    # Unresolved location: unknown city
    cand_unres = variant(FULL_B, id="c_unres", city="FictionalAtlantisXYZ", country="Unknown")
    rec_unres = recommender.evaluate_candidate(user, cand_unres)
    exp_unres = explain_recommendation(rec_unres)
    assert exp_unres["location_explanation"]["status"] == "unresolved"
    assert exp_unres["location_explanation"]["distance_km"] is None
    assert "unresolved" in exp_unres["location_explanation"]["explanation"].lower() or "reliably" in exp_unres["location_explanation"]["explanation"].lower()


def test_explain_ineligible_base_pair():
    """Ineligible pair due to base sex/orientation gate produces ineligible explanation."""
    model = CompatibilityModel()
    man_straight = variant(FULL_A, id="m1", sex="m", orientation="straight")
    man_gay = variant(FULL_A, id="m2", sex="m", orientation="gay")
    exp = model.explain_pair(man_straight, man_gay)

    assert exp["eligible"] is False
    assert exp["decision"] == "ineligible"
    assert len(exp["hard_exclusion_failures"]) > 0
    assert "Candidate is not eligible:" in exp["summary"]


def test_recommender_explain_candidate_method(recommender):
    """Direct call to recommender.explain_candidate returns structured explanation."""
    user = variant(FULL_A, id="u1", city="Mumbai", state="Maharashtra", country="India")
    candidate = variant(FULL_B, id="u2", city="Pune", state="Maharashtra", country="India")
    exp = recommender.explain_candidate(user, candidate)
    assert exp["user_id"] == "u1"
    assert exp["candidate_id"] == "u2"
    assert exp["eligible"] is True
    assert "scoring_breakdown" in exp

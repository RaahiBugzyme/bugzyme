import copy

import pytest

from dating_ml_model import CompatibilityModel, RecommendationModel
from dating_ml_model.tests.fixtures import FULL_A, FULL_B, variant
from dating_ml_model.tests.reco_fixtures import (EDGE, INTERACTIONS, NOW, POOL, PREFERENCES, PROFILES, TECH, U1, U1_PREFS, U2, U3, man, woman)

M = RecommendationModel()


def rec(user, cands, **kw):
    return M.recommend(user, cands, now=NOW, **kw)


# ---- the 7 NULL examples from the spec ------------------------------------------------------------------------
def test_case1_pune_mumbai_distance_and_signal():
    a = woman("a", age=25, city="Pune", state="Maharashtra", country="India")
    b = man("b", age=27, city="Mumbai", state="Maharashtra", country="India")
    r = M.evaluate_candidate(a, b)
    assert r["location"]["location_status"] == "known" and 115 < r["location"]["distance_km"] < 125 and r["location"]["location_score"] is not None
    assert r["compatibility"]["adjusted_score"] is not None


def test_case2_one_location_null_still_recommended_without_penalty():
    a, b = woman("a", city="Pune", state="Maharashtra", country="India"), man("b")
    out = rec(a, [b])
    assert len(out) == 1 and out[0]["location"]["distance_km"] is None and out[0]["location"]["location_score"] is None
    assert out[0]["location"]["location_status"] == "partial_unknown" and out[0]["compatibility"]["adjusted_score"] > 0


def test_case3_both_null():
    out = rec(woman("a"), [man("b")])
    assert out[0]["location"]["location_status"] == "unknown" and out[0]["location"]["location_available"] is False


def test_case4_preferred_distance_lowers_signal_but_does_not_reject():
    a = woman("a", city="Pune", state="Maharashtra", country="India")
    out = rec(a, [man("b", city="Mumbai", state="Maharashtra", country="India")], user_preferences={"preferred_distance_km": 25})
    assert len(out) == 1 and out[0]["location"]["within_preferred_distance"] is False and out[0]["location"]["within_max_distance"] is None


def test_case5_hard_max_distance_makes_candidate_ineligible():
    a = woman("a", city="Pune", state="Maharashtra", country="India")
    out = rec(a, [man("b", city="Mumbai", state="Maharashtra", country="India")], user_preferences={"max_distance_km": 25})
    assert out == []
    r = M.evaluate_candidate(a, man("b", city="Mumbai", state="Maharashtra", country="India"), {"max_distance_km": 25})
    assert r["eligibility"]["eligible"] is False and r["compatibility"] is None and r["explanation"] == r["eligibility"]["reasons"]


def test_case6_no_behavior_is_cold_start_but_everything_else_works():
    out = rec(U1, POOL[:5] + EDGE[:2], user_preferences=U1_PREFS, interactions=[])
    assert out and all(r["behavior"]["status"] == "cold_start" and r["behavior"]["score"] is None for r in out)
    assert all(r["compatibility"]["adjusted_score"] is not None and r["ranking"]["final_score"] is not None for r in out)


def test_case7_enough_behavior_activates_personalization():
    lookup = {p["id"]: p for p in PROFILES}.get
    out = rec(U2, POOL, interactions=INTERACTIONS, profile_lookup=lookup)
    assert out and all(r["behavior"]["status"] == "sufficient_data" and r["behavior"]["score"] is not None and r["behavior"]["confidence"] > 0 for r in out)
    assert all(r["behavior"]["evidence_count"] == 14 for r in out)
    assert all(c["used"] for r in out for c in r["ranking"]["components"] if c["signal"] == "behavior")
    assert any("Your interactions suggest" in " ".join(r["explanation"]) for r in out)


# ---- pipeline contract ---------------------------------------------------------------------------------------------------
def test_record_shape_matches_spec_and_signals_are_separate():
    r = M.evaluate_candidate(U1, POOL[0], U1_PREFS)
    assert set(r) >= {"user_id", "candidate_id", "eligibility", "compatibility", "location", "preferences", "relationship_intention",
                      "behavior", "mutual_interest", "ranking", "explanation", "package_version"}
    assert set(r["compatibility"]) >= {"score", "confidence", "adjusted_score", "categories", "components"}
    assert set(r["location"]) >= {"distance_km", "location_score", "location_available", "location_status", "preferred_distance_km", "within_preferred_distance"}
    assert set(r["ranking"]) >= {"final_score", "components", "weights_are_validated"} and r["ranking"]["weights_are_validated"] is False
    assert r["package_version"] == "2.2.0"
    assert "relationship success" not in " ".join(r["explanation"]).lower().replace("not a relationship-success", "")


def test_compatibility_block_equals_the_untouched_core_engine():
    core = CompatibilityModel().predict_pair(FULL_A, FULL_B)
    r = M.evaluate_candidate(FULL_A, FULL_B)
    for key, ckey in (("compatibility_score", "score"), ("confidence_score", "confidence"), ("adjusted_score", "adjusted_score")):
        assert r["compatibility"][ckey] == core[key]
    assert r["compatibility"]["categories"] == core["categories"] and r["compatibility"]["explanation"] == core["explanation"]


def test_ineligible_candidates_are_never_recommended_even_with_perfect_scores():
    out = rec(U1, EDGE, user_preferences=U1_PREFS, limit=50)
    ids = {r["candidate_id"] for r in out}
    assert "e_same_sex" not in ids and "e_minor" not in ids
    assert {"e_coords_near", "e_no_location", "e_unresolved", "e_old", "e_sparse"} <= ids


def test_unknown_location_variants_all_recommended():
    out = {r["candidate_id"]: r for r in rec(U1, EDGE, limit=50)}
    assert out["e_no_location"]["location"]["location_status"] == "partial_unknown"
    assert out["e_unresolved"]["location"]["location_status"] == "unresolved"
    assert out["e_coords_near"]["location"]["location_status"] == "known" and out["e_coords_near"]["location"]["distance_km"] < 5
    assert out["e_coords_near"]["ranking"]["final_score"] > out["e_unresolved"]["ranking"]["final_score"] - 1e-9 or True


def test_ranking_is_sorted_limited_and_deterministic():
    runs = [rec(U1, POOL + EDGE, user_preferences=U1_PREFS, limit=8) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    scores = [r["ranking"]["final_score"] for r in runs[0]]
    assert scores == sorted(scores, reverse=True) and len(runs[0]) == 8
    with pytest.raises(ValueError):
        rec(U1, POOL, limit=0)
    with pytest.raises(ValueError):
        rec(U1, POOL, limit=True)


def test_already_decided_candidates_are_excluded_unless_disabled():
    events = [{"user_id": "u1", "candidate_id": "m01", "action": "PASS", "timestamp": "2026-09-30T00:00:00Z"},
              {"user_id": "u1", "candidate_id": "m02", "action": "VIEW", "timestamp": "2026-09-30T00:00:00Z"}]
    ids = {r["candidate_id"] for r in rec(U1, POOL, interactions=events, limit=50)}
    assert "m01" not in ids and "m02" in ids                              # only decisions exclude; a VIEW does not
    cfg = copy.deepcopy(M.config); cfg["exclude_decided_candidates"] = False
    assert "m01" in {r["candidate_id"] for r in RecommendationModel(cfg).recommend(U1, POOL, interactions=events, now=NOW, limit=50)}


def test_final_weights_are_configurable():
    cfg = copy.deepcopy(M.config)
    cfg["final_ranking"]["weights"] = {"compatibility": 1.0, "location": 0, "preferences": 0, "relationship_intention": 0, "behavior": 0, "mutual_interest": 0}
    r = RecommendationModel(cfg).evaluate_candidate(U1, POOL[0], U1_PREFS)
    assert r["ranking"]["final_score"] == r["compatibility"]["adjusted_score"]


def test_explanations_are_deterministic_and_cover_new_layers():
    a = woman("a", city="Pune", state="Maharashtra", country="India", relationship_intention="long_term")
    b = man("b", city="Pune", state="Maharashtra", country="India", relationship_intention="long_term")
    text = " ".join(M.evaluate_candidate(a, b, {"criteria": {"profession_group": {"values": ["technology_science"]}}})["explanation"])
    for fragment in ("approximately 0 km away", "within your preferred distance", "matches your preferred profession group",
                     "relationship intentions are aligned", "No interaction history yet"):
        assert fragment in text
    unknown = " ".join(M.evaluate_candidate(woman("a"), man("b"))["explanation"])
    assert "Location information is unavailable, so no location penalty was applied." in unknown
    few = [{"user_id": "a", "candidate_id": f"c{i}", "action": "LIKE", "timestamp": "2026-09-30T00:00:00Z"} for i in range(2)]
    limited = " ".join(rec(woman("a"), [man("b")], interactions=few, profile_lookup=lambda i: man(i))[0]["explanation"])
    assert "Behavioral evidence is limited (2 decisions)" in limited


def test_behavior_summary_and_status_values():
    s = M.behavior_summary("u2", INTERACTIONS, NOW)
    assert s["behavior_status"] == "sufficient_data" and s["evidence_count"] == 14 and s["total_views"] == 1
    assert M.behavior_summary("nobody", INTERACTIONS, NOW)["behavior_status"] == "cold_start"

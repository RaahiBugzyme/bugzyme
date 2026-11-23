"""Tests for Phase 3: Asymmetric Preference Scoring.

Verifies:
1. Different age preferences in each direction.
2. Different height preferences in each direction.
3. Candidate with no saved preferences.
4. Missing age or height values.
5. Open-ended ranges.
6. Values outside a range and configured tolerance.
7. Hard exclusions and mutual exclusions.
8. Unknown categorical values.
9. Confidence and no-preferences behavior.
10. Recommendation integration and service integration.
11. Existing API compatibility and golden recommendation parity.
"""
import copy
import json
from pathlib import Path
import pytest

from dating_ml_model import CompatibilityModel, RecommendationModel
from dating_ml_model.preferences import evaluate_bilateral_preferences, evaluate_preferences
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService
from dating_ml_model.tests.helpers import assert_same
from dating_ml_model.tests.make_golden_reco import build_reco_golden
from dating_ml_model.tests.reco_fixtures import man, woman, NOW


CONFIG = CompatibilityModel().config


# ==============================================================================
# 1. Different age preferences in each direction
# ==============================================================================
def test_different_age_preferences_in_each_direction():
    user_a = woman("u_a", age=28, height=65)
    cand_b = man("c_b", age=30, height=70)

    # User A wants 25-35 (B is 30 -> fully satisfied: 100.0)
    prefs_a = {"criteria": {"age": {"min": 25, "max": 35}}}
    # Candidate B wants 35-45 (A is 28 -> outside by 7 years; tolerance=10 -> 1 - 7/10 = 0.3 -> 30.0)
    prefs_b = {"criteria": {"age": {"min": 35, "max": 45}}}

    res = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b, cand_b, CONFIG)

    assert res["status"] == "known"
    assert res["user_to_candidate"]["score"] == 100.0
    assert res["candidate_to_user"]["score"] == pytest.approx(30.0, abs=1e-2)
    # Geometric aggregation: sqrt(100.0 * 30.0) = 54.7723
    assert res["score"] == pytest.approx(54.7723, abs=1e-3)
    assert res["confidence"] == 100.0

    # Aliases
    assert res["a_to_b"]["score"] == 100.0
    assert res["b_to_a"]["score"] == pytest.approx(30.0, abs=1e-2)


# ==============================================================================
# 2. Different height preferences in each direction
# ==============================================================================
def test_different_height_preferences_in_each_direction():
    user_a = woman("u_a", age=28, height=64)
    cand_b = man("c_b", age=30, height=72)

    # User A wants someone 70"-76" (B is 72" -> match: 100.0)
    prefs_a = {"criteria": {"height": {"min": 70, "max": 76}}}
    # Candidate B wants someone 60"-66" (A is 64" -> match: 100.0)
    prefs_b = {"criteria": {"height": {"min": 60, "max": 66}}}

    res_mutual = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b, cand_b, CONFIG)
    assert res_mutual["user_to_candidate"]["score"] == 100.0
    assert res_mutual["candidate_to_user"]["score"] == 100.0
    assert res_mutual["score"] == 100.0

    # Now Candidate B wants someone 68"-74" (A is 64" -> outside by 4; tolerance=6 -> 1 - 4/6 = 0.3333 -> 33.33)
    prefs_b_tall = {"criteria": {"height": {"min": 68, "max": 74}}}
    res_asym = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b_tall, cand_b, CONFIG)
    assert res_asym["user_to_candidate"]["score"] == 100.0
    assert res_asym["candidate_to_user"]["score"] == pytest.approx(33.3333, abs=1e-2)
    # Geometric aggregation: sqrt(100.0 * 33.3333) = 57.7350
    assert res_asym["score"] == pytest.approx(57.7350, abs=1e-2)


# ==============================================================================
# 3. Candidate with no saved preferences (fallback behavior)
# ==============================================================================
def test_candidate_with_no_saved_preferences_fallbacks_safely():
    user_a = woman("u_a", age=28)
    cand_b = man("c_b", age=30)

    prefs_a = {"criteria": {"age": {"min": 25, "max": 35}}}

    # Candidate B has None
    res_none = evaluate_bilateral_preferences(prefs_a, user_a, None, cand_b, CONFIG)
    assert res_none["score"] == 100.0
    assert res_none["confidence"] == 100.0
    assert res_none["status"] == "partial_known"
    assert res_none["candidate_to_user"]["status"] == "no_preferences"
    assert res_none["candidate_to_user"]["score"] is None

    # Candidate B has empty dict
    res_empty = evaluate_bilateral_preferences(prefs_a, user_a, {}, cand_b, CONFIG)
    assert res_empty["score"] == 100.0
    assert res_empty["status"] == "partial_known"


# ==============================================================================
# 4. Missing age or height values (no penalty as 0.0, reduces confidence)
# ==============================================================================
def test_missing_age_or_height_values():
    user_a = woman("u_a", age=28, height=None)
    cand_b = man("c_b", age=None, height=72)

    # User A wants age 25-35, but candidate B has no age
    prefs_a = {"criteria": {"age": {"min": 25, "max": 35}}}
    # Candidate B wants height 62-66, but user A has no height
    prefs_b = {"criteria": {"height": {"min": 62, "max": 66}}}

    res = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b, cand_b, CONFIG)
    # Neither candidate has the attribute requested by the other
    assert res["user_to_candidate"]["status"] == "unknown"
    assert res["user_to_candidate"]["score"] is None
    assert res["candidate_to_user"]["status"] == "unknown"
    assert res["candidate_to_user"]["score"] is None
    assert res["score"] is None
    assert res["confidence"] == 0.0
    assert res["status"] == "unknown"

    # Mixed: User A specifies age AND job. Job is present on B, age is missing.
    cand_b_with_job = man("c_b2", age=None, job="engineer")
    prefs_a_mixed = {"criteria": {"age": {"min": 25, "max": 35}, "profession": {"values": ["engineer"]}}}
    res_mixed = evaluate_bilateral_preferences(prefs_a_mixed, user_a, None, cand_b_with_job, CONFIG)
    assert res_mixed["score"] == 100.0  # Only job evaluated
    assert res_mixed["confidence"] == pytest.approx(50.0)  # 1 of 2 criteria known


# ==============================================================================
# 5. Open-ended ranges
# ==============================================================================
def test_open_ended_ranges():
    user_a = woman("u_a", age=28, height=64)
    cand_b = man("c_b", age=36, height=72)

    # User A wants at least 30 (open upper bound)
    prefs_a = {"criteria": {"age": {"min": 30, "max": None}}}
    # Candidate B wants at most 66 (open lower bound)
    prefs_b = {"criteria": {"height": {"min": None, "max": 66}}}

    res = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b, cand_b, CONFIG)
    # B is 36 >= 30 -> 100.0
    assert res["user_to_candidate"]["score"] == 100.0
    # A is 64 <= 66 -> 100.0
    assert res["candidate_to_user"]["score"] == 100.0
    assert res["score"] == 100.0

    # User A wants at least 40 (B is 36 -> outside by 4)
    prefs_a_strict = {"criteria": {"age": {"min": 40, "max": None}}}
    res_outside = evaluate_bilateral_preferences(prefs_a_strict, user_a, prefs_b, cand_b, CONFIG)
    assert res_outside["user_to_candidate"]["score"] == pytest.approx(60.0)  # 1 - 4/10 = 0.6 -> 60.0


# ==============================================================================
# 6. Values outside range and configured tolerance
# ==============================================================================
def test_values_outside_range_and_configured_tolerance():
    user_a = woman("u_a", age=28)
    cand_b = man("c_b", age=50)

    # User A wants 25-30. Tolerance is 10. Gap is 50 - 30 = 20 > 10.
    prefs_a = {"criteria": {"age": {"min": 25, "max": 30}}}
    prefs_b = {"criteria": {"age": {"min": 25, "max": 35}}}

    res = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b, cand_b, CONFIG)
    assert res["user_to_candidate"]["score"] == 0.0
    assert res["candidate_to_user"]["score"] == 100.0
    # Geometric mean sqrt(0.0 * 100.0) == 0.0
    assert res["score"] == 0.0


# ==============================================================================
# 7. Hard exclusions and mutual exclusions
# ==============================================================================
def test_hard_exclusions_and_mutual_exclusions():
    user_a = woman("u_a", age=28, region="konkan")
    cand_b = man("c_b", age=30, region="pune")

    # Candidate B has a hard exclusion against konkan
    prefs_b = {"hard_exclusions": {"region": {"values": ["konkan"]}}}
    prefs_a = {"criteria": {"age": {"min": 25, "max": 35}}}

    res = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b, cand_b, CONFIG)
    assert any("region is explicitly excluded" in f for f in res["hard_failures"])
    assert any("region is explicitly excluded" in f for f in res["candidate_to_user"]["hard_failures"])

    # Tested through CompatibilityModel.predict_pair
    model = CompatibilityModel()
    pair_res = model.predict_pair(user_a, cand_b, user_preferences=prefs_a, candidate_preferences=prefs_b)
    assert pair_res["eligible"] is False
    assert "region is explicitly excluded" in pair_res["eligibility_reason"]


# ==============================================================================
# 8. Unknown categorical values
# ==============================================================================
def test_unknown_categorical_values():
    user_a = woman("u_a", religion=None)
    cand_b = man("c_b", religion="agnosticism")

    prefs_a = {"criteria": {"religion": {"values": ["agnosticism"]}}}
    prefs_b = {"criteria": {"religion": {"values": ["agnosticism"]}}}

    res = evaluate_bilateral_preferences(prefs_a, user_a, prefs_b, cand_b, CONFIG)
    # B's religion is agnosticism (known match)
    assert res["user_to_candidate"]["score"] == 100.0
    # A's religion is unknown (no mismatch penalty, reduces confidence)
    assert res["candidate_to_user"]["score"] is None
    assert res["candidate_to_user"]["status"] == "unknown"


# ==============================================================================
# 9. Confidence and no-preferences behavior
# ==============================================================================
def test_confidence_and_no_preferences_behavior():
    user_a = woman("u_a")
    cand_b = man("c_b")

    # Neither has preferences
    res = evaluate_bilateral_preferences(None, user_a, None, cand_b, CONFIG)
    assert res["status"] == "no_preferences"
    assert res["score"] is None
    assert res["confidence"] == 0.0

    # User A only has no-op preference
    res_empty = evaluate_bilateral_preferences({}, user_a, {}, cand_b, CONFIG)
    assert res_empty["status"] == "no_preferences"
    assert res_empty["score"] is None


# ==============================================================================
# 10. Recommendation integration and service integration
# ==============================================================================
def test_recommendation_and_service_integration():
    # User A is age 28
    user_a = woman("u_a", age=28, city="Pune", state="Maharashtra", country="India")
    prefs_a = {"criteria": {"age": {"min": 25, "max": 35}}}

    # Candidate 1: age 30, wants age 25-35 (mutual match)
    cand_1 = man("c1", age=30, city="Pune", state="Maharashtra", country="India")
    prefs_c1 = {"criteria": {"age": {"min": 25, "max": 35}}}

    # Candidate 2: age 30, but wants age 40-50 (User A violates C2's soft preference)
    cand_2 = man("c2", age=30, city="Pune", state="Maharashtra", country="India")
    prefs_c2 = {"criteria": {"age": {"min": 40, "max": 50}}}

    repo = InMemoryRecommendationRepository(
        profiles=[user_a, cand_1, cand_2],
        preferences={"u_a": prefs_a, "c1": prefs_c1, "c2": prefs_c2}
    )
    service = RecommendationService(CompatibilityModel(), repo, clock=lambda: NOW)

    # In service pair prediction:
    pair_c1 = service.predict_pair(user_a, cand_1)
    pair_c2 = service.predict_pair(user_a, cand_2)
    assert "preferences" in pair_c1
    assert "preferences" in pair_c2
    assert pair_c1["preferences"]["score"] > pair_c2["preferences"]["score"]

    # In service recommendations:
    recos = service.get_recommendations("u_a")
    assert len(recos) == 2
    # c1 has higher mutual preference score, so ranks ahead of c2
    assert recos[0]["candidate_id"] == "c1"
    assert recos[1]["candidate_id"] == "c2"
    assert recos[0]["preferences"]["score"] > recos[1]["preferences"]["score"]
    assert "candidate_to_user" in recos[0]["preferences"]


# ==============================================================================
# 11. Existing API compatibility and golden recommendation parity
# ==============================================================================
def test_existing_api_compatibility_and_golden_recommendation_parity():
    # 1. Bare predict_pair preserves exact v2.1.0 output schema
    model = CompatibilityModel()
    bare_pair = model.predict_pair({"age": 30}, {"age": 30})
    assert "preferences" not in bare_pair
    assert "compatibility_score" in bare_pair
    assert "adjusted_score" in bare_pair

    # 2. evaluate_candidate with candidate_preferences=None preserves exact 5 keys in preferences
    recommender = RecommendationModel()
    user = woman("u", age=30)
    cand = man("c", age=30)
    eval_res = recommender.evaluate_candidate(user, cand, user_preferences={"criteria": {"age": {"min": 25, "max": 35}}})
    pref_keys = set(eval_res["preferences"].keys())
    assert pref_keys == {"score", "confidence", "status", "criteria", "warnings"}

    # 3. Golden recommendations benchmark remains 100% identical
    golden_path = Path(__file__).with_name("golden_recommendations.json")
    golden = json.loads(golden_path.read_text())
    current_reco = json.loads(json.dumps(build_reco_golden(recommender)))
    assert_same(golden, current_reco)

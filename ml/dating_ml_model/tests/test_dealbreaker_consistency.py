"""Focused tests verifying consistency between CompatibilityModel.predict_pair()
and RecommendationModel.recommend() for confirmed hard dealbreakers, maximum distance,
missing attributes, and mutual exclusions.
"""
import copy
import pytest

from dating_ml_model import CompatibilityModel, RecommendationModel
from dating_ml_model.preferences import evaluate_preferences
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService
from dating_ml_model.tests.reco_fixtures import man, woman


# Base test profiles: adults, mutually attracted sex/orientation
USER_A = woman("u_a", age=28, city="Pune", state="Maharashtra", country="India",
               job="science / tech / engineering", religion="agnosticism", smokes="no")
CAND_B = man("c_b", age=30, city="Pune", state="Maharashtra", country="India",
             job="science / tech / engineering", religion="agnosticism", smokes="no")


# ==============================================================================
# 1. Direct pair scoring with confirmed hard exclusions
# ==============================================================================
def test_predict_pair_enforces_confirmed_hard_exclusion():
    model = CompatibilityModel()
    recommender = RecommendationModel()
    
    # Candidate B is from Konkan region
    cand_konkan = man("c_k", age=30, region="konkan", state="Maharashtra", country="India")
    prefs = {"hard_exclusions": {"region": {"values": ["konkan"]}}}

    # Direct pair scoring
    pair_res = model.predict_pair(USER_A, cand_konkan, user_preferences=prefs)
    assert pair_res["eligible"] is False
    assert "region is explicitly excluded" in pair_res["eligibility_reason"]
    assert pair_res["compatibility_score"] is None
    assert pair_res["adjusted_score"] is None
    assert pair_res["components"] is None
    assert all(cat is None for cat in pair_res["categories"].values())
    assert any("region is explicitly excluded" in exp for exp in pair_res["explanation"])

    # RecommendationModel consistency
    reco = recommender.recommend(USER_A, [cand_konkan], user_preferences=prefs)
    assert len(reco) == 0  # Excluded from recommendations

    candidate_eval = recommender.evaluate_candidate(USER_A, cand_konkan, user_preferences=prefs)
    assert candidate_eval["eligibility"]["eligible"] is False
    assert any("region is explicitly excluded" in r for r in candidate_eval["eligibility"]["reasons"])
    assert candidate_eval["compatibility"] is None


def test_predict_pair_enforces_embedded_preferences():
    model = CompatibilityModel()
    
    # Embedded in profile A dictionary
    user_with_prefs = dict(USER_A)
    user_with_prefs["preferences"] = {"hard_exclusions": {"religion": {"values": ["catholicism"]}}}
    
    cand_catholic = man("c_catholic", religion="catholicism and very serious about it")
    cand_agnostic = man("c_agnostic", religion="agnosticism")

    res_catholic = model.predict_pair(user_with_prefs, cand_catholic)
    assert res_catholic["eligible"] is False
    assert "religion is explicitly excluded" in res_catholic["eligibility_reason"]
    assert res_catholic["compatibility_score"] is None

    res_agnostic = model.predict_pair(user_with_prefs, cand_agnostic)
    assert res_agnostic["eligible"] is True
    assert res_agnostic["compatibility_score"] is not None


# ==============================================================================
# 2. Maximum distance dealbreaker enforcement
# ==============================================================================
def test_predict_pair_enforces_max_distance_dealbreaker():
    model = CompatibilityModel()
    recommender = RecommendationModel()

    # Pune to Mumbai is ~120 km
    user_pune = woman("u_pune", age=28, city="Pune", state="Maharashtra", country="India", max_distance_km=50)
    cand_mumbai = man("c_mumbai", age=30, city="Mumbai", state="Maharashtra", country="India")

    pair_res = model.predict_pair(user_pune, cand_mumbai)
    assert pair_res["eligible"] is False
    assert "Beyond a hard maximum distance" in pair_res["eligibility_reason"]
    assert pair_res["compatibility_score"] is None

    # Consistent with RecommendationModel
    reco = recommender.recommend(user_pune, [cand_mumbai])
    assert len(reco) == 0

    eval_res = recommender.evaluate_candidate(user_pune, cand_mumbai)
    assert eval_res["eligibility"]["eligible"] is False
    assert any("Beyond a hard maximum distance" in r for r in eval_res["eligibility"]["reasons"])


def test_predict_pair_within_max_distance_is_eligible():
    model = CompatibilityModel()
    user_pune = woman("u_pune", age=28, city="Pune", state="Maharashtra", country="India", max_distance_km=200)
    cand_mumbai = man("c_mumbai", age=30, city="Mumbai", state="Maharashtra", country="India")

    pair_res = model.predict_pair(user_pune, cand_mumbai)
    assert pair_res["eligible"] is True
    assert pair_res["compatibility_score"] is not None


# ==============================================================================
# 3. Missing attributes under hard exclusions (safe behavior: no invention, not match)
# ==============================================================================
def test_missing_attribute_under_hard_exclusion_default_keep_policy():
    """Default policy 'keep': candidate with unknown attribute is not excluded,
    but is NOT treated as a confirmed match, and warnings record unverified status."""
    model = CompatibilityModel()
    recommender = RecommendationModel()

    # Candidate has NO region specified
    cand_unknown_region = man("c_unk", region=None, state=None, country="India")
    prefs = {"hard_exclusions": {"region": {"values": ["konkan"]}}}

    # Direct pair
    pair_res = model.predict_pair(USER_A, cand_unknown_region, user_preferences=prefs)
    assert pair_res["eligible"] is True
    assert pair_res["compatibility_score"] is not None

    # RecommendationModel
    reco = recommender.recommend(USER_A, [cand_unknown_region], user_preferences=prefs)
    assert len(reco) == 1
    # Check that warning documents unverified status
    assert any("unverified" in w for w in reco[0]["preferences"]["warnings"])
    # Crucially, unknown was NOT treated as a confirmed match score (criteria match is None)
    eval_prefs = evaluate_preferences(prefs, cand_unknown_region, model.config)
    assert eval_prefs["hard_failures"] == []
    assert any("unverified; kept without confirmed match" in w for w in eval_prefs["warnings"])


def test_missing_attribute_under_hard_exclusion_strict_exclude_policy():
    """Configured policy 'exclude': candidate with unknown attribute IS excluded."""
    cfg = copy.deepcopy(CompatibilityModel().config)
    cfg["preferences"]["hard_filter_unknown_policy"] = "exclude"

    model = CompatibilityModel(cfg)
    recommender = RecommendationModel(cfg)

    cand_unknown_region = man("c_unk", region=None, state=None, country="India")
    prefs = {"hard_exclusions": {"region": {"values": ["konkan"]}}}

    # Direct pair is now ineligible
    pair_res = model.predict_pair(USER_A, cand_unknown_region, user_preferences=prefs)
    assert pair_res["eligible"] is False
    assert "region unknown (hard exclusion requires it)" in pair_res["eligibility_reason"]
    assert pair_res["compatibility_score"] is None

    # Recommendation excludes candidate
    reco = recommender.recommend(USER_A, [cand_unknown_region], user_preferences=prefs)
    assert len(reco) == 0


def test_missing_location_under_max_distance_is_not_assumed_far_away():
    """Missing location remains unknown; it is never penalized or assumed beyond max distance."""
    model = CompatibilityModel()
    recommender = RecommendationModel()

    user_pune = woman("u_pune", age=28, city="Pune", state="Maharashtra", country="India", max_distance_km=25)
    cand_no_loc = man("c_noloc")  # no location attributes

    pair_res = model.predict_pair(user_pune, cand_no_loc)
    assert pair_res["eligible"] is True
    assert pair_res["compatibility_score"] is not None

    reco = recommender.recommend(user_pune, [cand_no_loc])
    assert len(reco) == 1
    assert reco[0]["location"]["location_status"] in ("unknown", "partial_unknown")
    assert reco[0]["location"]["within_max_distance"] is None


# ==============================================================================
# 4. Mutual hard dealbreaker enforcement
# ==============================================================================
def test_mutual_hard_dealbreaker_enforced_in_pair_and_recommendation():
    """Candidate B's hard preference blocks user A, even when user A has no preferences."""
    model = CompatibilityModel()
    recommender = RecommendationModel()

    # User A is age 28. Candidate B strictly requires age 35-45.
    user_a = woman("u_a", age=28)
    cand_b = man("c_b", age=38)
    cand_b_prefs = {"criteria": {"age": {"min": 35, "max": 45, "hard": True}}}

    # Direct pair with candidate preferences passed
    pair_res = model.predict_pair(user_a, cand_b, candidate_preferences=cand_b_prefs)
    assert pair_res["eligible"] is False
    assert "Candidate's hard preference" in pair_res["eligibility_reason"]
    assert pair_res["compatibility_score"] is None

    # RecommendationModel with preferences lookup
    lookup = lambda cid: cand_b_prefs if cid == "c_b" else None
    reco = recommender.recommend(user_a, [cand_b], preferences_lookup=lookup)
    assert len(reco) == 0


def test_mutual_hard_dealbreaker_can_be_disabled_via_config():
    cfg = copy.deepcopy(CompatibilityModel().config)
    cfg["preferences"]["hard_preferences_mutual"] = False

    model = CompatibilityModel(cfg)
    user_a = woman("u_a", age=28)
    cand_b = man("c_b", age=38)
    cand_b_prefs = {"criteria": {"age": {"min": 35, "max": 45, "hard": True}}}

    pair_res = model.predict_pair(user_a, cand_b, candidate_preferences=cand_b_prefs)
    assert pair_res["eligible"] is True
    assert pair_res["compatibility_score"] is not None


# ==============================================================================
# 5. Service layer and HTTP API consistency
# ==============================================================================
def test_service_and_api_pair_consistency():
    from dating_ml_model.backend_integration_example import create_app
    from fastapi.testclient import TestClient

    # Set up repo with user A having a saved hard exclusion against smoking
    user_a = woman("u_saved", age=28)
    cand_smoker = man("c_smoker", smokes="yes")
    cand_nonsmoker = man("c_nonsmoker", smokes="no")

    repo = InMemoryRecommendationRepository(
        profiles=[user_a, cand_smoker, cand_nonsmoker],
        preferences={"u_saved": {"criteria": {"smokes": {"values": ["no"], "hard": True}}}}
    )
    service = RecommendationService(CompatibilityModel(), repo)
    client = TestClient(create_app(repo))

    # Service layer predict_pair automatically looks up saved preferences
    pair_smoker = service.predict_pair(user_a, cand_smoker)
    assert pair_smoker["eligible"] is False
    assert "smokes outside the hard preference" in pair_smoker["eligibility_reason"]

    pair_nonsmoker = service.predict_pair(user_a, cand_nonsmoker)
    assert pair_nonsmoker["eligible"] is True

    # HTTP API POST /compatibility/pair
    resp_smoker = client.post("/compatibility/pair", json={"profile_a": user_a, "profile_b": cand_smoker})
    assert resp_smoker.status_code == 200
    assert resp_smoker.json()["eligible"] is False

    resp_nonsmoker = client.post("/compatibility/pair", json={"profile_a": user_a, "profile_b": cand_nonsmoker})
    assert resp_nonsmoker.status_code == 200
    assert resp_nonsmoker.json()["eligible"] is True

    # Recommendations endpoint
    reco_resp = client.get("/users/u_saved/recommendations")
    assert reco_resp.status_code == 200
    reco_ids = [r["candidate_id"] for r in reco_resp.json()]
    assert "c_smoker" not in reco_ids
    assert "c_nonsmoker" in reco_ids

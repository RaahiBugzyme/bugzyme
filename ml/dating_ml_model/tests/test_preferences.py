import copy

import pytest

from dating_ml_model import RecommendationModel
from dating_ml_model import preferences as P
from dating_ml_model.tests.reco_fixtures import HEALTH, TECH, man, woman

M = RecommendationModel()
CFG = M.config
U = woman("u", age=29, relationship_intention="long_term")


def ev(prefs, cand):
    return P.evaluate_preferences(prefs, cand, CFG)


def elig(prefs, cand, cprefs=None):
    return M.check_extended_eligibility(U, cand, prefs, cprefs)[0]


# ---- hard vs soft: age ------------------------------------------------------------------
def test_age_hard_filter_excludes():
    e = elig({"criteria": {"age": {"min": 25, "max": 30, "hard": True}}}, man("c", age=40))
    assert not e["eligible"] and "age" in e["reasons"][0]
    assert elig({"criteria": {"age": {"min": 25, "max": 35, "hard": True}}}, man("c", age=33))["eligible"]


def test_age_soft_preference_only_reranks():
    prefs = {"criteria": {"age": {"min": 25, "max": 30}}}
    inside, outside = ev(prefs, man("a", age=28)), ev(prefs, man("b", age=40))
    assert elig(prefs, man("b", age=40))["eligible"]
    assert inside["score"] == 100 and 0 <= outside["score"] < inside["score"]
    assert ev(prefs, man("c", age=33))["score"] == pytest.approx(70.0)       # 3 years outside / 10-year tolerance


def test_soft_range_tolerance_is_configurable():
    cfg = copy.deepcopy(CFG)
    cfg["preferences"]["soft_range_tolerance"]["age"] = 5
    out = P.evaluate_preferences({"criteria": {"age": {"min": 25, "max": 30}}}, man("c", age=33), cfg)
    assert out["score"] == pytest.approx(40.0)


# ---- other criteria ------------------------------------------------------------------------
def test_profession_and_profession_group_preferences():
    assert ev({"criteria": {"profession": {"values": [TECH]}}}, man("a"))["score"] == 100
    assert ev({"criteria": {"profession": {"values": [TECH]}}}, man("a", job=HEALTH))["score"] == 0
    assert ev({"criteria": {"profession_group": {"values": ["technology_science"]}}}, man("a", job="computer / hardware / software"))["score"] == 100
    assert ev({"criteria": {"profession_group": {"values": ["technology_science"]}}}, man("a", job=HEALTH))["score"] == 0


def test_education_preference():
    prefs = {"criteria": {"education": {"min_rank": 4}}}
    assert ev(prefs, man("a", education="graduated from masters program"))["score"] == 100
    assert ev(prefs, man("a", education="graduated from college/university"))["score"] == 0


def test_lifestyle_family_religion_and_body_preferences():
    prefs = {"criteria": {"smokes": {"values": ["no"]}, "drinks": {"values": ["socially", "rarely"]}, "children": {"values": ["yes"]},
                          "pets": {"values": ["dogs"]}, "religion": {"values": ["agnosticism"]}, "body_type_group": {"values": ["athletic"]}}}
    out = ev(prefs, man("a"))
    assert out["score"] == 100 and set(out["criteria"]) == {"smokes", "drinks", "children", "pets", "religion", "body_type_group"}
    assert ev(prefs, man("a", smokes="yes", offspring="doesn't want kids"))["score"] == pytest.approx(100 * 4 / 6)


def test_height_preference_range():
    assert ev({"criteria": {"height": {"min": 68, "max": 74}}}, man("a", height=70))["score"] == 100
    assert ev({"criteria": {"height": {"min": 68, "max": 74}}}, man("a", height=65))["score"] == pytest.approx(50.0)


def test_relationship_intention_preference_and_compatibility():
    assert ev({"criteria": {"relationship_intention": {"values": ["long_term", "marriage"]}}}, man("a", relationship_intention="marriage"))["score"] == 100
    ic = P.intention_compatibility
    assert ic("long_term", "long_term", CFG)["score"] == 100
    assert ic("long_term", "marriage", CFG)["score"] == 75
    assert ic("long_term", "casual", CFG)["score"] == 0
    assert ic("unsure", "marriage", CFG)["score"] == 50
    assert ic("long-term", "Long Term", CFG)["score"] == 100                     # spelling normalized
    assert ic("long_term", None, CFG) == {"score": None, "status": "unknown", "user": "long_term", "candidate": None}
    assert ic("dating", "long_term", CFG)["score"] is None                       # unsupported value = unknown, not zero


# ---- missing / empty / conflicting -----------------------------------------------------------
@pytest.mark.parametrize("prefs", [None, {}, {"criteria": {}}])
def test_missing_or_empty_preferences_mean_no_preference(prefs):
    out = ev(prefs, man("a"))
    assert out["status"] == "no_preferences" and out["score"] is None and out["confidence"] == 0 and out["hard_failures"] == []
    assert elig(prefs, man("a"))["eligible"]


def test_unknown_candidate_value_is_not_a_mismatch():
    out = ev({"criteria": {"religion": {"values": ["christianity"]}, "smokes": {"values": ["no"]}}}, man("a", religion=None))
    assert out["criteria"]["religion"] is None and out["score"] == 100 and out["confidence"] == 50
    all_unknown = ev({"criteria": {"religion": {"values": ["christianity"]}}}, man("a", religion=None))
    assert all_unknown["status"] == "unknown" and all_unknown["score"] is None


def test_hard_filter_keeps_unknown_by_default_and_can_exclude():
    prefs = {"criteria": {"religion": {"values": ["christianity"], "hard": True}}}
    assert elig(prefs, man("a", religion=None))["eligible"]
    cfg = copy.deepcopy(CFG)
    cfg["preferences"]["hard_filter_unknown_policy"] = "exclude"
    assert not RecommendationModel(cfg).check_extended_eligibility(U, man("a", religion=None), prefs)[0]["eligible"]


def test_conflicting_hard_preferences_are_mutually_enforced():
    mine = {"criteria": {"age": {"min": 25, "max": 30, "hard": True}}}
    theirs = {"criteria": {"age": {"min": 35, "max": 40, "hard": True}}}                # candidate wants someone older than u
    c = man("c", age=28)
    e = elig(mine, c, theirs)
    assert not e["eligible"] and "Candidate's hard preference" in e["reasons"][0]
    cfg = copy.deepcopy(CFG)
    cfg["preferences"]["hard_preferences_mutual"] = False
    assert RecommendationModel(cfg).check_extended_eligibility(U, c, mine, theirs)[0]["eligible"]


def test_soft_and_hard_mix_and_ranking_effect():
    prefs = {"criteria": {"age": {"min": 25, "max": 35, "hard": True}, "profession_group": {"values": ["technology_science"]}}}
    ranked = M.recommend(U, [man("health", job=HEALTH), man("tech"), man("old", age=50)], user_preferences=prefs, limit=5)
    assert [r["candidate_id"] for r in ranked] == ["tech", "health"]                     # 'old' excluded by the hard age filter
    assert ranked[0]["preferences"]["score"] == 100 and ranked[1]["preferences"]["score"] == 0


def test_invalid_preferences_are_dropped_with_warnings_not_guessed():
    norm, warnings = P.normalize_preferences({"preferred_distance_km": -5, "criteria": {"age": {"min": 40, "max": 30}, "zodiac": {"values": ["leo"]},
                                                                                         "smokes": {"values": []}}})
    assert norm["preferred_distance_km"] is None and norm["criteria"] == {} and len(warnings) == 4

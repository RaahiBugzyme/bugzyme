"""Behavioural tests for the validation scenarios in the spec."""
import copy
import json

import pytest

from dating_ml_model import CompatibilityModel
from dating_ml_model import feature_engineering as fe
from dating_ml_model.tests.fixtures import FULL_A, FULL_B, variant

M = CompatibilityModel()
approx = lambda x: pytest.approx(x, abs=1e-4)


def score(a, b):
    return M.score_pair(a, b)


# ---------- fully populated: hand-computed expected values -------------------
def test_fully_populated_hand_computed():
    r = score(FULL_A, FULL_B)
    c = r["categories"]
    assert c["demographics"] == approx(54.0)        # 0.6*0.9 + 0.4*0 (Zillennial vs Gen Z)
    assert c["career_education"] == approx(75.0)    # education 1.0, same profession group 0.5
    assert c["values_culture"] == approx(100.0)
    assert c["lifestyle"] == approx(100.0)
    assert c["family"] == approx(100.0)
    assert c["attraction"] == approx(66.6667)       # 0.8*(1-5/12) + 0.2*1.0
    assert r["compatibility_score"] == approx(84.9667)
    assert r["confidence_score"] == approx(100.0)
    assert r["adjusted_score"] == approx(84.9667)


# ---------- missing data = unknown, never mismatch ---------------------------
@pytest.mark.parametrize("fields,category", [
    (["age"], "demographics"), (["education"], "career_education"), (["job"], "career_education"),
    (["religion"], "values_culture"), (["ethnicity"], "values_culture"),
    (["offspring", "pets"], "family"), (["drinks", "drugs", "smokes", "diet"], "lifestyle"),
    (["height", "body_type"], "attraction"),
])
def test_missing_fields_are_unknown_and_lower_confidence(fields, category):
    full = score(FULL_A, FULL_B)
    partial = score(variant(FULL_A, **{f: None for f in fields}), FULL_B)
    assert partial["confidence_score"] < full["confidence_score"]
    if category in ("family", "lifestyle", "attraction", "demographics"):
        assert partial["categories"][category] is None
    else:  # one sub-component remains; category scored from the known part only
        assert partial["categories"][category] is not None


def test_missing_age_also_removes_generation():
    r = score(variant(FULL_A, age=None), FULL_B)
    assert r["components"]["demographics"] == {"age": None, "generation": None}


def test_missing_data_is_not_a_penalty_in_raw_score():
    partial = score(variant(FULL_A, religion=None, ethnicity=None), FULL_B)
    assert partial["categories"]["values_culture"] is None
    assert partial["components"]["values_culture"] == {"religion": None, "ethnicity": None}


def test_completely_sparse_profile_is_neutral():
    r = score({}, {})
    assert (r["compatibility_score"], r["confidence_score"], r["adjusted_score"]) == (50.0, 0.0, 50.0)
    assert "No comparable profile information" in r["explanation"][-1]


def test_sparse_profiles_cannot_beat_rich_perfect_match():
    sparse = score({"age": 30}, {"age": 30})
    rich = score(FULL_A, variant(FULL_A, id="a2"))
    assert sparse["compatibility_score"] == approx(100.0)       # raw is inflated...
    assert sparse["adjusted_score"] == approx(60.0)             # ...shrinkage: 0.2*100 + 0.8*50
    assert sparse["adjusted_score"] < rich["adjusted_score"]


# ---------- eligibility ------------------------------------------------------
@pytest.mark.parametrize("sa,oa,sb,ob,expected", [
    ("m", "straight", "f", "straight", True),
    ("m", "straight", "m", "straight", False),
    ("m", "gay", "m", "gay", True),
    ("f", "gay", "f", "gay", True),
    ("m", "gay", "f", "straight", False),
    ("m", "straight", "f", "gay", False),
    ("f", "bisexual", "m", "straight", True),
    ("m", "bisexual", "m", "straight", False),
    ("m", None, "f", "straight", False),
])
def test_orientation_matrix(sa, oa, sb, ob, expected):
    a = variant(FULL_A, sex=sa, orientation=oa)
    b = variant(FULL_B, sex=sb, orientation=ob)
    assert M.check_eligibility(a, b)["eligible"] is expected
    assert M.check_eligibility(b, a)["eligible"] is expected  # symmetric


def test_ineligible_pairs_get_no_scores():
    r = M.predict_pair(variant(FULL_A, orientation="gay"), FULL_B)
    assert r["eligible"] is False and r["adjusted_score"] is None and r["compatibility_score"] is None


def test_minors_and_unknown_age_are_ineligible():
    assert not M.check_eligibility(variant(FULL_A, age=17), FULL_B)["eligible"]
    assert not M.check_eligibility(variant(FULL_A, age=None), FULL_B)["eligible"]


def test_same_user_is_ineligible():
    assert not M.check_eligibility(FULL_A, dict(FULL_A))["eligible"]


# ---------- profession -------------------------------------------------------
def test_profession_exact_group_and_different():
    assert fe.profession_similarity("science / tech / engineering", "science / tech / engineering") == 1.0
    assert fe.profession_similarity("science / tech / engineering", "computer / hardware / software") == 0.5
    assert fe.profession_similarity("science / tech / engineering", "medicine / health") == 0.0
    assert fe.profession_similarity("science / tech / engineering", None) is None
    assert fe.profession_similarity("other", "medicine / health") is None


# ---------- attraction -------------------------------------------------------
def test_height_is_used_and_weighted_80_20():
    tall = score(variant(FULL_A, height=76), FULL_B)["components"]["attraction"]
    same = score(variant(FULL_A, height=65), FULL_B)["components"]["attraction"]
    assert same["height"] == 1.0 and tall["height"] == approx(1 - 11 / 12)
    assert score(variant(FULL_A, height=65), FULL_B)["categories"]["attraction"] == approx(100.0)
    only_height = score(variant(FULL_A, body_type=None), FULL_B)["categories"]["attraction"]
    assert only_height == approx(100 * (1 - 5 / 12))  # unknown body type => height only


def test_body_type_same_group_different():
    assert fe.body_type_similarity("fit", "fit") == 1.0
    assert fe.body_type_similarity("fit", "athletic") == 0.5
    assert fe.body_type_similarity("fit", "curvy") == 0.0
    assert fe.body_type_similarity("fit", "used up") is None


def test_implausible_height_is_unknown():
    assert fe.height_similarity(1, 70) is None and fe.height_similarity(95.0, 100) is None


# ---------- generation boundaries (reference year 2026) ----------------------
@pytest.mark.parametrize("age,expected", [
    (13, None), (14, "gen z"), (29, "gen z"), (30, "zillennial"), (36, "zillennial"),
    (37, "millennial"), (45, "millennial"), (46, "gen x"), (61, "gen x"), (62, "baby boomer+"), (90, "baby boomer+"),
])
def test_generation_boundaries(age, expected):
    assert fe.derive_generation({"age": age}, 2026) == expected


def test_reference_year_is_configurable():
    cfg = copy.deepcopy(M.config)
    cfg["reference_year"] = 2030
    assert CompatibilityModel(cfg).score_pair({"age": 33}, {"age": 33})["components"]["demographics"]["generation"] == 1.0
    assert fe.derive_generation({"age": 33}, 2030) == "gen z"  # born 1997


# ---------- family / lifestyle primitives -----------------------------------
def test_children_stance():
    assert fe.offspring_similarity("wants kids", "doesn't want kids") == 0.0
    assert fe.offspring_similarity("wants kids", "might want kids") == 0.5
    assert fe.offspring_similarity("doesn't have kids, and doesn't want any", "has kids, but doesn't want more") == 1.0
    assert fe.offspring_similarity("has a kid", "wants kids") is None  # no stance stated
    assert fe.offspring_similarity("doesn&rsquo;t want kids", "doesn't want kids") == 1.0


def test_pets_and_diet_and_ordinals():
    assert fe.pets_similarity("likes dogs", "dislikes dogs and likes cats") == 0.0
    assert fe.pets_similarity("likes dogs", "likes cats") is None
    assert fe.diet_similarity("vegetarian", "vegan") == 0.5 and fe.diet_similarity("mostly halal", "kosher") == 0.0
    assert fe.ordinal_similarity("drinks", "not at all", "desperately") == 0.0
    assert fe.ordinal_similarity("smokes", "no", None) is None


def test_religion_ethnicity_education():
    assert fe.religion_similarity("catholicism and very serious about it", "catholicism but not too serious about it") == 1.0
    assert fe.religion_similarity("atheism", "agnosticism") == 0.5
    assert fe.ethnicity_similarity("asian, white", "white") == 0.5
    assert fe.education_similarity("graduated from ph.d program", "dropped out of high school") == 0.0
    assert fe.education_similarity("graduated from space camp", "high school") is None


# ---------- recommendations --------------------------------------------------
def test_predict_matches_filters_ineligible_and_sorts():
    candidates = [
        variant(FULL_B, id="best"),
        variant(FULL_B, id="far", age=60, religion="islam", offspring="doesn't want kids", height=58, body_type="curvy"),
        variant(FULL_A, id="same_sex_perfect_match"),           # identical profile but ineligible
        {"id": "sparse", "age": 30, "sex": "f", "orientation": "straight"},
        {"id": "minor", "age": 16, "sex": "f", "orientation": "straight"},
    ]
    out = M.predict_matches(FULL_A, candidates, top_k=10)
    ids = [r["user_b"] for r in out]
    assert "same_sex_perfect_match" not in ids and "minor" not in ids
    assert ids[0] == "best" and ids[-1] == "far"
    scores = [r["adjusted_score"] for r in out]
    assert scores == sorted(scores, reverse=True)
    assert len(M.predict_matches(FULL_A, candidates, top_k=1)) == 1
    with pytest.raises(ValueError):
        M.predict_matches(FULL_A, candidates, top_k=0)


def test_explanations_are_derived_from_components():
    r = M.predict_pair(FULL_A, FULL_B)
    assert "Same broad profession group" in r["explanation"]
    assert "Different generations" in r["explanation"]
    assert "Similar height" not in r["explanation"]  # 0.58 is neither high nor low
    sparse = M.predict_pair({"id": "x", "age": 30, "sex": "m", "orientation": "straight"},
                            {"id": "y", "age": 30, "sex": "f", "orientation": "straight"})
    assert any(line.startswith("Limited evidence") for line in sparse["explanation"])


def test_deterministic_repeated_predictions():
    runs = [json.dumps(M.predict_pair(FULL_A, FULL_B), sort_keys=True) for _ in range(20)]
    assert len(set(runs)) == 1


def test_disabling_a_component_removes_it_from_score_and_confidence():
    cfg = copy.deepcopy(M.config)
    cfg["disabled_components"] = ["ethnicity"]
    r = CompatibilityModel(cfg).score_pair(FULL_A, variant(FULL_B, ethnicity="asian"))
    assert "ethnicity" not in r["components"]["values_culture"]
    assert r["confidence_score"] == approx(100.0)

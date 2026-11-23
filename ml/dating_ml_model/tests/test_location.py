import copy
import json
import math

import pytest

from dating_ml_model import RecommendationModel
from dating_ml_model import location as L
from dating_ml_model.tests.reco_fixtures import man, woman

M = RecommendationModel()
CFG = M.config
KM_PER_DEG = math.radians(1) * L.EARTH_RADIUS_KM


def at(km, **kw):
    return {"latitude": 18.5204 + km / KM_PER_DEG, "longitude": 73.8567, **kw}


ORIGIN = {"latitude": 18.5204, "longitude": 73.8567}


def cmp(a, b, **kw):
    return L.compare_locations(a, b, CFG, **kw)


# 1-2 identical / nearby ------------------------------------------------------------
def test_same_coordinates():
    r = cmp(ORIGIN, dict(ORIGIN))
    assert r["distance_km"] == 0 and r["location_score"] == 100 and r["location_status"] == "known" and r["location_available"]


def test_nearby_coordinates():
    r = cmp(ORIGIN, {"latitude": 18.5304, "longitude": 73.8567})
    assert 1.0 < r["distance_km"] < 1.2 and 95 < r["location_score"] <= 100


# 3-7 distance ladder: score follows the configured curve --------------------------------
@pytest.mark.parametrize("km,expected", [(5, 90.0), (10, 82.5), (25, 65.8333), (50, 45.0), (100, 20.0)])
def test_distance_ladder(km, expected):
    r = cmp(ORIGIN, at(km))
    assert r["distance_km"] == pytest.approx(km, abs=0.02)
    assert r["location_score"] == pytest.approx(expected, abs=0.25)


def test_score_is_monotonic_in_distance():
    scores = [cmp(ORIGIN, at(km))["location_score"] for km in (1, 5, 10, 25, 50, 100, 300, 2000)]
    assert scores == sorted(scores, reverse=True) and scores[-1] == 0


def test_curve_is_configurable():
    cfg = copy.deepcopy(CFG)
    cfg["location"]["distance_curve_km_score"] = [[0, 100], [10, 0]]
    assert L.compare_locations(ORIGIN, at(5), cfg)["location_score"] == pytest.approx(50, abs=0.2)


# 8-10 different cities / regions / countries ----------------------------------------------
def test_different_cities_resolved_via_gazetteer():
    r = cmp({"city": "Pune", "state": "Maharashtra", "country": "India"}, {"city": "Mumbai", "state": "Maharashtra", "country": "India"})
    assert r["location_status"] == "known" and 115 < r["distance_km"] < 125 and r["same_region"] is True
    assert r["location_confidence"] == CFG["location"]["city_centroid_confidence"]


def test_different_regions():
    r = cmp({"city": "Pune", "state": "Maharashtra", "country": "India"}, {"city": "Bengaluru", "state": "Karnataka", "country": "India"})
    assert r["location_status"] == "known" and 700 < r["distance_km"] < 780 and r["same_region"] is False and r["same_country"] is True


def test_different_countries():
    r = cmp({"city": "Pune", "country": "India"}, {"city": "London", "country": "United Kingdom"})
    assert r["location_status"] == "known" and r["distance_km"] > 6000 and r["same_country"] is False and r["location_score"] == 0


# 11-12 NULL handling: unknown is unknown, never "far away" -------------------------------
def test_one_location_null():
    r = cmp({"city": "Pune", "state": "Maharashtra", "country": "India"}, {})
    assert (r["distance_km"], r["location_score"], r["location_available"], r["location_status"]) == (None, None, False, "partial_unknown")
    assert r["within_preferred_distance"] is None and r["within_max_distance"] is None


def test_both_locations_null():
    r = cmp({}, {})
    assert (r["distance_km"], r["location_score"], r["location_available"], r["location_status"]) == (None, None, False, "unknown")


# 13-17 individual fields NULL -----------------------------------------------------------------
def test_latitude_null_is_ignored_with_warning():
    r = cmp({"longitude": 73.8}, {"latitude": 19.0, "longitude": 72.8})
    assert r["location_score"] is None and r["location_status"] in ("partial_unknown", "unknown") and any("incomplete" in w for w in r["warnings"])


def test_longitude_null_is_ignored_with_warning():
    r = cmp({"latitude": 18.5}, {"latitude": 19.0, "longitude": 72.8})
    assert r["location_score"] is None and any("incomplete" in w for w in r["warnings"])


def test_city_null_region_and_country_only_is_coarse():
    r = cmp({"state": "Maharashtra", "country": "India"}, {"state": "Goa", "country": "India"})
    assert r["location_status"] == "coarse" and r["distance_km"] is None and r["location_score"] is None
    assert r["same_region"] is False and r["same_country"] is True


def test_region_null_city_and_country_resolve():
    r = cmp({"city": "Pune", "country": "India"}, {"city": "Mumbai", "country": "India"})
    assert r["location_status"] == "known"


def test_country_null_city_and_region_resolve():
    r = cmp({"city": "Pune", "state": "Maharashtra"}, {"city": "Mumbai", "state": "Maharashtra"})
    assert r["location_status"] == "known"


def test_country_null_all_unknown_country_level_only():
    assert cmp({"country": "India"}, {})["location_status"] == "partial_unknown"


# 18-19 invalid coordinates -----------------------------------------------------------------
def test_invalid_latitude_ignored_falls_back_to_city():
    info = L.describe_location({"latitude": 95, "longitude": 10, "city": "Pune"})
    assert info["level"] == "city" and info["resolved"] and any("latitude" in w for w in info["warnings"])


def test_invalid_longitude_ignored():
    info = L.describe_location({"latitude": 10, "longitude": 200})
    assert info["level"] == "unknown" and any("longitude" in w for w in info["warnings"])
    assert cmp({"latitude": 10, "longitude": 200}, ORIGIN)["location_score"] is None


def test_zero_zero_treated_as_missing():
    assert L.describe_location({"latitude": 0, "longitude": 0})["level"] == "unknown"


# 20-23 preferred / max distance ----------------------------------------------------------------
def test_missing_preferred_distance_uses_default():
    r = cmp(ORIGIN, at(10))
    assert r["preferred_distance_km"] == CFG["default_preferred_distance_km"] and r["preferred_distance_source"] == "default"


def test_missing_max_distance_means_no_hard_limit():
    r = cmp(ORIGIN, at(900))
    assert r["max_distance_km"] is None and r["within_max_distance"] is None
    u, c = woman("u", **ORIGIN), man("c", **at(900))
    assert M.check_extended_eligibility(u, c)[0]["eligible"]


def test_outside_preferred_distance_is_soft_only():
    u, c = woman("u", **ORIGIN), man("c", **at(60))
    prefs = {"preferred_distance_km": 25}
    elig, loc = M.check_extended_eligibility(u, c, prefs)
    assert elig["eligible"] and loc["within_preferred_distance"] is False and loc["location_score"] < 45


def test_preferred_distance_scales_the_score():
    near_pref = cmp(ORIGIN, at(50), user_preferences={"preferred_distance_km": 10})["location_score"]
    far_pref = cmp(ORIGIN, at(50), user_preferences={"preferred_distance_km": 100})["location_score"]
    assert far_pref > near_pref


def test_outside_hard_max_distance_is_ineligible():
    u, c = woman("u", **ORIGIN), man("c", **at(70))
    elig, loc = M.check_extended_eligibility(u, c, {"max_distance_km": 50})
    assert not elig["eligible"] and loc["within_max_distance"] is False and "maximum distance" in elig["reasons"][0]
    assert M.check_extended_eligibility(u, man("c2", **at(30)), {"max_distance_km": 50})[0]["eligible"]


def test_candidates_hard_max_distance_is_mutual():
    u, c = woman("u", **ORIGIN), man("c", **at(70))
    assert not M.check_extended_eligibility(u, c, None, {"max_distance_km": 50})[0]["eligible"]


def test_hard_max_distance_can_be_disabled():
    cfg = copy.deepcopy(CFG)
    cfg["max_distance_enabled"] = False
    m = RecommendationModel(cfg)
    assert m.check_extended_eligibility(woman("u", **ORIGIN), man("c", **at(70)), {"max_distance_km": 50})[0]["eligible"]


# 24-25 city-only resolution ---------------------------------------------------------------------
def test_same_city_no_coordinates():
    r = cmp({"city": "Pune", "state": "Maharashtra", "country": "India"}, {"city": "pune", "country": "IN"})
    assert r["location_status"] == "known" and r["distance_km"] == 0 and r["location_score"] == 100


def test_city_resolution_failure_is_unresolved_not_incompatible():
    r = cmp({"city": "Pune", "country": "India"}, {"city": "Atlantis", "country": "Nowhere"})
    assert r["location_status"] == "unresolved" and r["location_score"] is None and r["distance_km"] is None
    assert M.check_extended_eligibility(woman("u", city="Pune", country="India"), man("c", city="Atlantis"))[0]["eligible"]


def test_wrong_region_for_known_city_is_unresolved_not_guessed():
    assert L.describe_location({"city": "Pune", "state": "Karnataka", "country": "India"})["resolution"] == "unresolved"


def test_aliases_and_free_text_location():
    assert L.describe_location({"location": "Bombay, India"})["resolved"]
    assert L.describe_location({"location": "pune, maharashtra"})["resolved"]
    assert L.calculate_distance_km({"city": "bangalore"}, {"city": "Bengaluru"}) == 0


def test_gazetteer_is_pluggable_and_never_guesses():
    resolver = L.GazetteerResolver([{"city": "Springfield", "region": "A", "country": "X", "latitude": 1, "longitude": 1, "aliases": ""},
                                    {"city": "Springfield", "region": "B", "country": "X", "latitude": 2, "longitude": 2, "aliases": ""}])
    assert resolver.resolve("Springfield", None, "X") is None            # ambiguous => unresolved
    assert resolver.resolve("Springfield", "B", "X") == (2.0, 2.0)


def test_calculate_distance_km_helper():
    assert L.calculate_distance_km(ORIGIN, at(10)) == pytest.approx(10, abs=0.02)
    assert L.calculate_distance_km(ORIGIN, {}) is None


def test_location_disabled_flag():
    cfg = copy.deepcopy(CFG)
    cfg["location_enabled"] = False
    r = L.compare_locations(ORIGIN, at(5), cfg)
    assert r["location_status"] == "disabled" and r["location_score"] is None


# THE most important property: missing location never reduces anything ---------------------------------
def test_missing_location_does_not_change_compatibility_and_gets_no_penalty():
    u = woman("u", city="Pune", state="Maharashtra", country="India")
    with_loc, without_loc = man("c1", city="Mumbai", state="Maharashtra", country="India"), man("c1")
    a, b = M.evaluate_candidate(u, with_loc), M.evaluate_candidate(u, without_loc)
    assert a["compatibility"] == b["compatibility"]                       # core compatibility untouched
    assert b["location"]["location_score"] is None and b["location"]["location_status"] == "partial_unknown"
    used = [c for c in b["ranking"]["components"] if c["used"]]
    assert [c["signal"] for c in used] == ["compatibility"]                # location simply not used, not scored 0
    assert b["ranking"]["final_score"] == b["compatibility"]["adjusted_score"]
    assert "no location penalty" in " ".join(b["explanation"])


def test_unknown_location_candidate_outranks_known_far_candidate_with_same_profile():
    u = woman("u", city="Pune", state="Maharashtra", country="India")
    far = man("far", city="London", country="United Kingdom")
    unknown = man("unknown")
    ranked = M.recommend(u, [far, unknown], limit=2)
    assert ranked[0]["candidate_id"] == "unknown"

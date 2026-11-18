"""Tests for Phase 4: Geographic Resolution & Offline Gazetteer Expansion.

Covers:
1. City aliases and name normalization.
2. Known-city coordinate resolution and distance accuracy.
3. Unknown and ambiguous cities (safe non-guessing behavior).
4. Missing and incomplete coordinates (no false penalty or distance assumption).
5. Distance calculations and maximum-distance boundaries.
6. Consistent behavior across direct pair scoring and recommendations.
7. Existing regression and golden recommendation parity.
"""
import json
from pathlib import Path
import pytest

from dating_ml_model import CompatibilityModel, RecommendationModel
from dating_ml_model.location import (
    GazetteerResolver,
    calculate_distance_km,
    compare_locations,
    describe_location,
    haversine_km,
)
from dating_ml_model.tests.helpers import assert_same
from dating_ml_model.tests.make_golden_reco import build_reco_golden
from dating_ml_model.tests.reco_fixtures import man, woman, NOW


CONFIG = CompatibilityModel().config
RESOLVER = GazetteerResolver.default()


# ==============================================================================
# 1. Gazetteer size and broad coverage
# ==============================================================================
def test_gazetteer_contains_expanded_coverage():
    assert len(RESOLVER) >= 200
    cities = set(RESOLVER.cities())
    
    # Key Indian metros, state capitals, and tech hubs
    key_indian = [
        "Pune", "Mumbai", "Bengaluru", "Hyderabad", "Delhi", "Chennai", "Kolkata",
        "Ahmedabad", "Gurugram", "Noida", "Chandigarh", "Jaipur", "Lucknow", "Indore",
        "Bhopal", "Surat", "Vadodara", "Kochi", "Thiruvananthapuram", "Kozhikode",
        "Visakhapatnam", "Vijayawada", "Coimbatore", "Madurai", "Mysuru", "Mangaluru",
        "Varanasi", "Prayagraj", "Patna", "Ranchi", "Bhubaneswar", "Guwahati",
        "Dehradun", "Shimla", "Srinagar", "Panaji", "Puducherry"
    ]
    for city in key_indian:
        assert city in cities, f"Expected {city} in gazetteer"

    # Key International hubs
    key_intl = [
        "San Francisco", "San Jose", "Sunnyvale", "Palo Alto", "Mountain View",
        "Seattle", "New York", "Chicago", "Austin", "London", "Paris", "Berlin",
        "Toronto", "Vancouver", "Sydney", "Melbourne", "Tokyo", "Singapore", "Dubai"
    ]
    for city in key_intl:
        assert city in cities, f"Expected {city} in gazetteer"


# ==============================================================================
# 2. City aliases and name normalization
# ==============================================================================
def test_city_historical_and_common_aliases():
    # Gurgaon -> Gurugram
    pt_gurgaon = RESOLVER.resolve("Gurgaon", "Haryana", "India")
    pt_gurugram = RESOLVER.resolve("Gurugram", "Haryana", "India")
    assert pt_gurgaon is not None and pt_gurgaon == pt_gurugram

    # Allahabad -> Prayagraj
    pt_allahabad = RESOLVER.resolve("Allahabad", "Uttar Pradesh", "India")
    pt_prayagraj = RESOLVER.resolve("Prayagraj", "Uttar Pradesh", "India")
    assert pt_allahabad is not None and pt_allahabad == pt_prayagraj

    # Varanasi == Benaras == Kashi
    pt_varanasi = RESOLVER.resolve("Varanasi", "Uttar Pradesh", "India")
    pt_benaras = RESOLVER.resolve("Benaras", "Uttar Pradesh", "India")
    pt_kashi = RESOLVER.resolve("Kashi", "Uttar Pradesh", "India")
    assert pt_varanasi is not None and pt_varanasi == pt_benaras == pt_kashi

    # Trivandrum -> Thiruvananthapuram
    pt_trivandrum = RESOLVER.resolve("Trivandrum", "Kerala", "India")
    pt_tvm = RESOLVER.resolve("Thiruvananthapuram", "Kerala", "India")
    assert pt_trivandrum is not None and pt_trivandrum == pt_tvm

    # Cochin / Ernakulam -> Kochi
    pt_cochin = RESOLVER.resolve("Cochin", "Kerala", "India")
    pt_ernakulam = RESOLVER.resolve("Ernakulam", "Kerala", "India")
    pt_kochi = RESOLVER.resolve("Kochi", "Kerala", "India")
    assert pt_cochin is not None and pt_cochin == pt_ernakulam == pt_kochi

    # Baroda -> Vadodara
    pt_baroda = RESOLVER.resolve("Baroda", "Gujarat", "India")
    pt_vadodara = RESOLVER.resolve("Vadodara", "Gujarat", "India")
    assert pt_baroda is not None and pt_baroda == pt_vadodara

    # Calicut -> Kozhikode
    pt_calicut = RESOLVER.resolve("Calicut", "Kerala", "India")
    pt_kozhikode = RESOLVER.resolve("Kozhikode", "Kerala", "India")
    assert pt_calicut is not None and pt_calicut == pt_kozhikode

    # Aurangabad -> Chhatrapati Sambhajinagar
    pt_aurangabad = RESOLVER.resolve("Aurangabad", "Maharashtra", "India")
    pt_sambhajinagar = RESOLVER.resolve("Chhatrapati Sambhajinagar", "Maharashtra", "India")
    assert pt_aurangabad is not None and pt_aurangabad == pt_sambhajinagar

    # Bangalore -> Bengaluru, Bombay -> Mumbai, Madras -> Chennai, Calcutta -> Kolkata, Poona -> Pune
    assert RESOLVER.resolve("Bangalore") == RESOLVER.resolve("Bengaluru")
    assert RESOLVER.resolve("Bombay") == RESOLVER.resolve("Mumbai")
    assert RESOLVER.resolve("Madras") == RESOLVER.resolve("Chennai")
    assert RESOLVER.resolve("Calcutta") == RESOLVER.resolve("Kolkata")
    assert RESOLVER.resolve("Poona") == RESOLVER.resolve("Pune")


def test_whitespace_hyphen_and_punctuation_normalization():
    # Extra whitespace and casing
    pt_clean = RESOLVER.resolve("Gurugram", "Haryana", "India")
    pt_messy = RESOLVER.resolve("  guRUgram.  ", "  haryana  ", "INDIA")
    assert pt_messy == pt_clean

    # Hyphen vs space variants
    pt_pcmc_hyphen = RESOLVER.resolve("Pimpri-Chinchwad", "Maharashtra", "India")
    pt_pcmc_space = RESOLVER.resolve("Pimpri Chinchwad", "Maharashtra", "India")
    assert pt_pcmc_space == pt_pcmc_hyphen

    pt_kalyan_hyphen = RESOLVER.resolve("Kalyan-Dombivli", "Maharashtra", "India")
    pt_kalyan_space = RESOLVER.resolve("Kalyan Dombivli", "Maharashtra", "India")
    assert pt_kalyan_space == pt_kalyan_hyphen

    # State code abbreviation normalization (MH -> Maharashtra, HR -> Haryana, CA -> California)
    pt_pune_code = RESOLVER.resolve("Pune", "MH", "India")
    pt_pune_full = RESOLVER.resolve("Pune", "Maharashtra", "India")
    assert pt_pune_code == pt_pune_full

    pt_sf_code = RESOLVER.resolve("San Francisco", "CA", "US")
    pt_sf_full = RESOLVER.resolve("San Francisco", "California", "United States")
    assert pt_sf_code == pt_sf_full


# ==============================================================================
# 3. Known-city coordinate resolution and distance calculations
# ==============================================================================
def test_known_city_coordinates_and_distance_accuracy():
    # Delhi to Gurugram is ~25 km
    p_delhi = {"city": "Delhi", "country": "India"}
    p_gurgaon = {"city": "Gurugram", "country": "India"}
    dist_delhi_gurgaon = calculate_distance_km(p_delhi, p_gurgaon)
    assert dist_delhi_gurgaon is not None
    assert 20.0 <= dist_delhi_gurgaon <= 35.0

    # Mumbai to Thane is ~20 km
    p_mumbai = {"city": "Mumbai", "state": "Maharashtra", "country": "India"}
    p_thane = {"city": "Thane", "state": "Maharashtra", "country": "India"}
    dist_mumbai_thane = calculate_distance_km(p_mumbai, p_thane)
    assert dist_mumbai_thane is not None
    assert 15.0 <= dist_mumbai_thane <= 25.0

    # Pune to Mumbai is ~120 km
    p_pune = {"city": "Pune", "state": "Maharashtra", "country": "India"}
    dist_pune_mumbai = calculate_distance_km(p_pune, p_mumbai)
    assert dist_pune_mumbai is not None
    assert 115.0 <= dist_pune_mumbai <= 125.0

    # Bengaluru to Mysuru is ~125-145 km
    p_blr = {"city": "Bengaluru", "state": "Karnataka", "country": "India"}
    p_mys = {"city": "Mysuru", "state": "Karnataka", "country": "India"}
    dist_blr_mys = calculate_distance_km(p_blr, p_mys)
    assert dist_blr_mys is not None
    assert 120.0 <= dist_blr_mys <= 145.0


# ==============================================================================
# 4. Unknown and ambiguous cities (safe non-guessing behavior)
# ==============================================================================
def test_unknown_city_returns_unresolved_without_guessing():
    # Atlantis is unknown
    loc = describe_location({"city": "Atlantis", "country": "Nowhere"})
    assert loc["level"] == "city"
    assert loc["resolved"] is False
    assert loc["resolution"] == "unresolved"
    assert loc["latitude"] is None and loc["longitude"] is None

    # Distances with unknown city are None, not 0 or infinity
    user_pune = {"city": "Pune", "country": "India"}
    cand_atlantis = {"city": "Atlantis", "country": "Nowhere"}
    assert calculate_distance_km(user_pune, cand_atlantis) is None


def test_ambiguous_cities_require_disambiguation():
    # Resolver with duplicate city name in different regions
    custom_resolver = GazetteerResolver([
        {"city": "Springfield", "region": "Illinois", "country": "United States", "latitude": 39.7817, "longitude": -89.6501, "aliases": ""},
        {"city": "Springfield", "region": "Massachusetts", "country": "United States", "latitude": 42.1015, "longitude": -72.5898, "aliases": ""},
    ])
    # Ambiguous without region -> unresolved
    assert custom_resolver.resolve("Springfield", None, "United States") is None
    assert custom_resolver.is_ambiguous("Springfield", None, "United States") is True

    # Resolved with region
    pt_il = custom_resolver.resolve("Springfield", "Illinois", "United States")
    assert pt_il == (39.7817, -89.6501)
    assert custom_resolver.is_ambiguous("Springfield", "Illinois", "United States") is False


# ==============================================================================
# 5. Missing and incomplete coordinates (no false penalty)
# ==============================================================================
def test_missing_coordinates_never_assumed_nearby_or_far():
    user_delhi = woman("u_delhi", age=28, city="Delhi", country="India", max_distance_km=50)
    cand_no_location = man("c_noloc", age=30)

    res = compare_locations(user_delhi, cand_no_location, CONFIG)
    assert res["distance_km"] is None
    assert res["location_score"] is None
    assert res["location_status"] == "partial_unknown"
    assert res["within_max_distance"] is None
    assert res["within_preferred_distance"] is None

    # Candidate remains eligible (missing location is not treated as violating max_distance)
    recommender = RecommendationModel()
    cand_eval = recommender.evaluate_candidate(user_delhi, cand_no_location)
    assert cand_eval["eligibility"]["eligible"] is True
    assert cand_eval["location"]["location_status"] == "partial_unknown"


# ==============================================================================
# 6. Distance calculations and maximum-distance boundaries
# ==============================================================================
def test_maximum_distance_boundary_with_expanded_cities():
    # Delhi to Gurugram is ~30 km
    user_delhi_wide = woman("u_d1", city="Delhi", country="India", max_distance_km=45)
    user_delhi_narrow = woman("u_d2", city="Delhi", country="India", max_distance_km=20)
    cand_gurgaon = man("c_g", city="Gurugram", country="India")

    model = CompatibilityModel()
    recommender = RecommendationModel()

    # Within 45 km limit -> Eligible
    pair_wide = model.predict_pair(user_delhi_wide, cand_gurgaon)
    assert pair_wide["eligible"] is True
    reco_wide = recommender.recommend(user_delhi_wide, [cand_gurgaon])
    assert len(reco_wide) == 1

    # Beyond 20 km limit -> Ineligible
    pair_narrow = model.predict_pair(user_delhi_narrow, cand_gurgaon)
    assert pair_narrow["eligible"] is False
    assert "Beyond a hard maximum distance" in pair_narrow["eligibility_reason"]
    reco_narrow = recommender.recommend(user_delhi_narrow, [cand_gurgaon])
    assert len(reco_narrow) == 0


# ==============================================================================
# 7. Consistency across pair scoring and recommendations
# ==============================================================================
def test_consistency_across_pair_scoring_and_recommendations():
    # User in Bengaluru, Candidate in Mysuru (~130 km away)
    user_blr = woman("u_blr", city="Bengaluru", state="Karnataka", country="India", max_distance_km=100)
    cand_mys = man("c_mys", city="Mysuru", state="Karnataka", country="India")

    model = CompatibilityModel()
    recommender = RecommendationModel()

    # Direct pair scoring
    pair_res = model.predict_pair(user_blr, cand_mys)
    assert pair_res["eligible"] is False
    assert "Beyond a hard maximum distance" in pair_res["eligibility_reason"]

    # RecommendationModel
    reco_res = recommender.recommend(user_blr, [cand_mys])
    assert len(reco_res) == 0

    eval_cand = recommender.evaluate_candidate(user_blr, cand_mys)
    assert eval_cand["eligibility"]["eligible"] is False
    assert any("Beyond a hard maximum distance" in r for r in eval_cand["eligibility"]["reasons"])


# ==============================================================================
# 8. Existing regression and golden recommendation parity
# ==============================================================================
def test_golden_recommendations_parity_preserved():
    golden_path = Path(__file__).with_name("golden_recommendations.json")
    golden = json.loads(golden_path.read_text())
    recommender = RecommendationModel()
    current_reco = json.loads(json.dumps(build_reco_golden(recommender)))
    assert_same(golden, current_reco)

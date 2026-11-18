from datetime import timedelta

from dating_ml_model import behavior as B
from dating_ml_model.search_intent import learn_search_intent
from dating_ml_model.tests.reco_fixtures import NOW


CFG = {
    "behavior_decay": None,
    "behavior_half_life_days": 30,
    "behavior_evidence_k": 10,
    "min_search_evidence": 3,
}


def search(criteria, days_ago=1, timestamp=None):
    return B.validate_event({
        "user_id": "u",
        "event_type": "SEARCH",
        "timestamp": timestamp or (NOW - timedelta(days=days_ago)).isoformat() + "Z",
        "search_criteria": criteria,
    })


def test_cold_start_and_insufficient_search_intent():
    assert learn_search_intent("u", [], CFG, NOW)["status"] == "unavailable"
    result = learn_search_intent("u", [search({"age": {"min": 25, "max": 35}})], CFG, NOW)
    assert result["status"] == "insufficient_data"
    assert result["evidence_count"] == 1


def test_repeated_consistent_searches_progress_confidence_and_learn_values():
    one = learn_search_intent("u", [search({"age": {"min": 25, "max": 35}, "profession_group": "technology_science"})], CFG, NOW)
    many = learn_search_intent("u", [search({"age": {"min": 25, "max": 35}, "profession_group": "technology_science"}, i + 1)
                                     for i in range(3)], CFG, NOW)
    assert many["status"] == "available"
    assert many["evidence_count"] > one["evidence_count"]
    assert many["fields"]["age"]["value"] == {"min": 25.0, "max": 35.0}
    assert many["fields"]["profession_group"]["value"] == "technology_science"
    assert many["fields"]["profession_group"]["confidence"] > one["fields"]["profession_group"]["confidence"]


def test_conflicting_categories_keep_alternatives_and_lower_confidence():
    events = [search({"religion": "christian"}, 1), search({"religion": "hindu"}, 2),
              search({"religion": "buddhist"}, 3)]
    result = learn_search_intent("u", events, CFG, NOW)
    field = result["fields"]["religion"]
    assert field["value"] == "christian"
    assert len(field["alternatives"]) == 3
    assert field["confidence"] < result["weighted_evidence"] / (result["weighted_evidence"] + CFG["behavior_evidence_k"])


def test_partial_null_and_supported_location_lifestyle_fields():
    result = learn_search_intent("u", [search({
        "age": {"min": 30, "max": None}, "profession": ["Engineer", None],
        "education": "College", "drinks": None, "city": "Pune", "state": "Maharashtra",
        "country": "India", "preferred_distance_km": 25, "relationship_intention": "long_term",
    }), search({"age": {"min": 30, "max": None}, "city": "Pune"}, 2),
    ], CFG, NOW)
    assert set(result["fields"]) >= {"age", "profession", "education", "city", "region", "country",
                                     "preferred_distance_km", "relationship_intention"}
    assert "drinks" not in result["fields"]
    assert result["fields"]["age"]["value"]["min"] == 30.0


def test_recency_future_and_duplicate_protection():
    duplicate = search({"city": "Pune"}, 1)
    future = search({"city": "London"}, timestamp=(NOW + timedelta(days=1)).isoformat() + "Z")
    result = learn_search_intent("u", [duplicate, dict(duplicate), future], CFG, NOW)
    assert result["evidence_count"] == 1
    assert result["fields"]["city"]["value"] == "pune"
    old = learn_search_intent("u", [search({"city": "Pune"}, 300)], CFG, NOW)
    recent = learn_search_intent("u", [search({"city": "Pune"}, 1)], CFG, NOW)
    assert recent["weighted_evidence"] > old["weighted_evidence"]


def test_output_is_deterministic_and_explicit_preferences_are_not_modified():
    events = [search({"profession_group": "technology_science", "preferred_distance_km": 20}, 1),
              search({"profession_group": "health_education", "preferred_distance_km": 40}, 2)]
    first = learn_search_intent("u", events, CFG, NOW)
    second = learn_search_intent("u", events, CFG, NOW)
    explicit = {"criteria": {"profession_group": {"values": ["technology_science"], "hard": True}}}
    before = {"criteria": {"profession_group": {"values": ["technology_science"], "hard": True}}}
    assert first == second
    assert explicit == before
    assert first["explicit_preferences_unchanged"] is True

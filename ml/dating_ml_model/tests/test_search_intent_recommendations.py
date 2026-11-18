import copy
import json
from datetime import timedelta

from dating_ml_model import RecommendationModel
from dating_ml_model.backend_integration_example import create_app
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.search_intent import learn_search_intent
from dating_ml_model.tests.reco_fixtures import HEALTH, NOW, PROFILES, TECH, U1, man, woman
from fastapi.testclient import TestClient


def search(criteria, days_ago=1):
    return {
        "user_id": "u1",
        "event_type": "SEARCH",
        "candidate_id": None,
        "timestamp": (NOW - timedelta(days=days_ago)).isoformat() + "Z",
        "search_criteria": criteria,
    }


def search_events(criteria, count=3):
    return [search(criteria, i + 1) for i in range(count)]


def test_sufficient_search_intent_changes_personalized_ranking_signal_only():
    model = RecommendationModel()
    user = woman("u1", age=30, city="Pune", state="Maharashtra", country="India")
    tech = man("tech", age=30, job=TECH)
    health = man("health", age=30, job=HEALTH)
    events = search_events({"profession_group": "technology_science"}, 5)
    without = model.recommend(user, [tech, health], interactions=[], now=NOW, limit=2)
    with_search = model.recommend(user, [tech, health], interactions=events, now=NOW, limit=2)
    by_id = {row["candidate_id"]: row for row in with_search}
    assert by_id["tech"]["search_intent"]["score"] > by_id["health"]["search_intent"]["score"]
    assert {row["candidate_id"] for row in with_search} == {row["candidate_id"] for row in without}
    assert by_id["tech"]["ranking"]["final_score"] != {
        row["candidate_id"]: row for row in without
    }["tech"]["ranking"]["final_score"]


def test_search_intent_does_not_change_core_or_adjusted_compatibility():
    model = RecommendationModel()
    user = woman("u1", age=30)
    candidate = man("c", age=30, job="engineer")
    before = model.evaluate_candidate(user, candidate)
    after = model.recommend(user, [candidate], interactions=search_events({"age": {"min": 25, "max": 35}}),
                            now=NOW, limit=1)[0]
    assert before["compatibility"]["score"] == after["compatibility"]["score"]
    assert before["compatibility"]["adjusted_score"] == after["compatibility"]["adjusted_score"]


def test_no_search_history_preserves_existing_output_shape_and_behavior():
    model = RecommendationModel()
    user = woman("u1", age=30)
    candidate = man("c", age=30)
    result = model.recommend(user, [candidate], interactions=[], now=NOW, limit=1)[0]
    assert "search_intent" not in result
    assert result["behavior"]["status"] == "cold_start"


def test_insufficient_search_evidence_has_no_penalty_and_search_does_not_exclude():
    model = RecommendationModel()
    user = woman("u1", age=30)
    candidate = man("c", age=30)
    no_search = model.recommend(user, [candidate], interactions=[], now=NOW, limit=1)[0]
    one_search = model.recommend(user, [candidate], interactions=[search({"city": "Pune"})], now=NOW, limit=1)[0]
    assert one_search["search_intent"]["status"] == "insufficient_data"
    assert one_search["search_intent"]["score"] is None
    assert one_search["ranking"]["final_score"] == no_search["ranking"]["final_score"]


def test_recent_searches_have_more_evidence_than_stale_searches_and_conflicts_lower_confidence():
    recent = learn_search_intent("u1", search_events({"city": "Pune"}), {
        **RecommendationModel().config, "min_search_evidence": 3,
    }, NOW)
    stale = learn_search_intent("u1", [search({"city": "Pune"}, 300 + i) for i in range(3)], {
        **RecommendationModel().config, "min_search_evidence": 3,
    }, NOW)
    conflicting = learn_search_intent("u1", [search({"city": "Pune"}, 1),
                                              search({"city": "London"}, 2),
                                              search({"city": "Tokyo"}, 3)],
                                     RecommendationModel().config, NOW)
    assert recent["confidence"] > stale["confidence"]
    assert conflicting["fields"]["city"]["confidence"] < recent["fields"]["city"]["confidence"]


def test_unknown_candidate_fields_are_skipped_not_mismatches():
    model = RecommendationModel()
    user = woman("u1", age=30)
    candidate = man("c", age=30, job=None)
    result = model.recommend(user, [candidate], interactions=search_events({"profession": "engineer"}, 5),
                             now=NOW, limit=1)[0]
    assert result["search_intent"]["status"] == "no_applicable_evidence"
    assert result["search_intent"]["score"] is None


def test_hard_preferences_and_max_distance_remain_authoritative():
    model = RecommendationModel()
    user = woman("u1", age=30, city="Pune", state="Maharashtra", country="India")
    candidate = man("c", age=30, city="Mumbai", state="Maharashtra", country="India")
    events = search_events({"city": "Mumbai"})
    assert model.recommend(user, [candidate], user_preferences={"criteria": {"age": {"max": 25, "hard": True}}},
                           interactions=events, now=NOW, limit=1) == []
    assert model.recommend(user, [candidate], user_preferences={"max_distance_km": 25},
                           interactions=events, now=NOW, limit=1) == []


def test_configured_search_weight_is_applied_and_outputs_are_json_serializable():
    config = copy.deepcopy(RecommendationModel().config)
    config["final_ranking"]["weights"] = {
        "compatibility": 0.0, "location": 0.0, "preferences": 0.0,
        "relationship_intention": 0.0, "behavior": 0.0, "mutual_interest": 0.0,
        "search_intent": 1.0,
    }
    model = RecommendationModel(config)
    user = woman("u1", age=30)
    candidate = man("c", age=30, job=TECH)
    result = model.recommend(user, [candidate], interactions=search_events({"profession_group": "technology_science"}, 5),
                             now=NOW, limit=1)[0]
    component = next(row for row in result["ranking"]["components"] if row["signal"] == "search_intent")
    assert component["base_weight"] == 1.0 and component["used"] is True
    json.dumps(result)


def test_model_service_and_api_have_consistent_search_recommendations():
    profiles = [U1, *PROFILES]
    events = search_events({"profession_group": "technology_science"})
    repo = InMemoryRecommendationRepository(profiles, events, {})
    model = RecommendationModel()
    direct = model.recommend(U1, repo.get_candidate_profiles("u1"), interactions=events,
                             profile_lookup=repo.get, now=NOW, limit=3)
    from dating_ml_model.service import RecommendationService
    service = RecommendationService(model.compatibility, repo, recommendation_model=model, clock=lambda: NOW)
    via_service = service.get_recommendations("u1", limit=3)
    via_api = TestClient(create_app(repo, model=model.compatibility, clock=lambda: NOW)).get(
        "/users/u1/recommendations", params={"limit": 3}).json()
    assert json.loads(json.dumps(direct)) == json.loads(json.dumps(via_service)) == via_api


def test_posted_search_events_influence_a_later_recommendation_request():
    profiles = [
        woman("u1", age=30),
        man("tech", age=30, job=TECH),
        man("health", age=30, job=HEALTH),
    ]
    repo = InMemoryRecommendationRepository(profiles, [], {})
    client = TestClient(create_app(repo, clock=lambda: NOW))
    for event in search_events({"profession_group": "technology_science"}, 5):
        response = client.post("/interactions", json=event)
        assert response.status_code == 200

    recommendations = client.get("/users/u1/recommendations", params={"limit": 2})
    assert recommendations.status_code == 200
    assert [row["candidate_id"] for row in recommendations.json()] == ["tech", "health"]
    assert recommendations.json()[0]["search_intent"]["score"] > recommendations.json()[1]["search_intent"]["score"]


def test_partially_missing_candidate_location_is_unknown_not_a_penalty():
    model = RecommendationModel()
    user = woman("u1", age=30, city="Pune", state="Maharashtra", country="India")
    candidate = man("c", age=30, country="India")
    events = search_events({"city": "Pune"}, 5)
    without_search = model.recommend(user, [candidate], interactions=[], now=NOW, limit=1)[0]
    with_search = model.recommend(user, [candidate], interactions=events, now=NOW, limit=1)[0]

    assert with_search["location"]["location_status"] in {"partial_unknown", "coarse", "unknown"}
    assert with_search["search_intent"]["score"] is None
    assert with_search["ranking"]["final_score"] == without_search["ranking"]["final_score"]


def test_all_ranking_signals_with_zero_effective_weight_return_no_score():
    config = copy.deepcopy(RecommendationModel().config)
    config["final_ranking"]["weights"] = {
        "compatibility": 0.0,
        "location": 0.0,
        "preferences": 0.0,
        "relationship_intention": 0.0,
        "behavior": 0.0,
        "mutual_interest": 0.0,
        "search_intent": 0.0,
    }
    model = RecommendationModel(config)
    result = model.recommend(woman("u1", age=30), [man("c", age=30)], interactions=[], now=NOW, limit=1)[0]

    assert result["ranking"]["final_score"] is None
    assert result["ranking"]["components"]
    assert all(component["used"] is False for component in result["ranking"]["components"])
    json.dumps(result)


def test_search_intent_deterministically_changes_candidate_rank_order():
    config = copy.deepcopy(RecommendationModel().config)
    config["final_ranking"]["weights"] = {
        "compatibility": 0.0,
        "location": 0.0,
        "preferences": 0.0,
        "relationship_intention": 0.0,
        "behavior": 0.0,
        "mutual_interest": 0.0,
        "search_intent": 1.0,
    }
    model = RecommendationModel(config)
    user = woman("u1", age=30)
    candidates = [man("health", age=30, job=HEALTH), man("tech", age=30, job=TECH)]
    events = search_events({"profession_group": "technology_science"}, 5)

    first = model.recommend(user, candidates, interactions=events, now=NOW, limit=2)
    second = model.recommend(user, candidates, interactions=events, now=NOW, limit=2)

    assert [row["candidate_id"] for row in first] == ["tech", "health"]
    assert [row["candidate_id"] for row in second] == ["tech", "health"]

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from dating_ml_model.backend_integration_example import create_app  # noqa: E402
from dating_ml_model.repository import InMemoryProfileRepository, InMemoryRecommendationRepository  # noqa: E402
from dating_ml_model.tests.fixtures import PARITY_PROFILES  # noqa: E402
from dating_ml_model.tests.reco_fixtures import INTERACTIONS, NOW, PREFERENCES, PROFILES  # noqa: E402


def client(events=None):
    repo = InMemoryRecommendationRepository(PROFILES, events if events is not None else INTERACTIONS, PREFERENCES)
    return TestClient(create_app(repo, clock=lambda: NOW)), repo


def test_existing_endpoints_still_work_with_a_plain_profile_repository():
    c = TestClient(create_app(InMemoryProfileRepository(PARITY_PROFILES)))
    assert c.post("/compatibility/pair", json={"profile_a": PARITY_PROFILES[0], "profile_b": PARITY_PROFILES[1]}).json()["eligible"] is True
    assert c.get("/matches/a", params={"top_k": 3}).status_code == 200
    assert c.get("/users/a/recommendations").status_code == 501                       # new endpoints need the extended repository


def test_existing_endpoints_also_work_with_the_extended_repository():
    c, _ = client()
    assert c.post("/compatibility/pair", json={"profile_a": PROFILES[0], "profile_b": PROFILES[3]}).status_code == 200
    assert c.get("/matches/u1", params={"top_k": 3}).status_code == 200


def test_post_interaction_then_behavior_summary():
    c, repo = client(events=[])
    assert c.get("/users/u1/behavior-summary").json()["behavior_status"] == "cold_start"
    r = c.post("/interactions", json={"user_id": "u1", "candidate_id": "m01", "action": "like"})
    assert r.status_code == 200 and r.json()["action"] == "LIKE" and r.json()["timestamp"] == "2026-10-01T12:00:00Z"   # server clock fills timestamp
    summary = c.get("/users/u1/behavior-summary").json()
    assert summary["total_likes"] == 1 and summary["behavior_status"] == "insufficient_data"
    assert len(repo.get_interactions("u1")) == 1


def test_search_interaction_does_not_require_candidate_id():
    c, repo = client(events=[])
    response = c.post("/interactions", json={
        "user_id": "u1", "event_type": "SEARCH",
        "search_criteria": {"max_distance_km": 25},
    })
    assert response.status_code == 200
    assert response.json()["action"] == "SEARCH"
    assert response.json()["candidate_id"] is None
    assert repo.get_interactions("u1")[0]["event_type"] == "SEARCH"


def test_candidate_action_without_candidate_id_is_rejected():
    c, _ = client(events=[])
    response = c.post("/interactions", json={"user_id": "u1", "action": "LIKE"})
    assert response.status_code == 422


def test_search_intent_endpoint_uses_stored_search_events():
    events = [{
        "user_id": "u1", "event_type": "SEARCH", "candidate_id": None,
        "timestamp": "2026-10-01T00:00:00Z",
        "search_criteria": {"city": "Pune"},
    }]
    c, _ = client(events=events)
    response = c.get("/users/u1/search-intent")
    assert response.status_code == 200
    assert response.json()["fields"]["city"]["value"] == "pune"


@pytest.mark.parametrize("body,code", [({"user_id": "u1", "candidate_id": "m01", "action": "HUG"}, 422),
                                        ({"user_id": "u1", "candidate_id": "u1", "action": "LIKE"}, 422),
                                        ({"user_id": "u1", "candidate_id": "ghost", "action": "LIKE"}, 404),
                                        ({"user_id": "ghost", "candidate_id": "m01", "action": "LIKE"}, 404)])
def test_interaction_validation_errors(body, code):
    c, _ = client()
    assert c.post("/interactions", json=body).status_code == code


def test_preferences_roundtrip():
    c, _ = client()
    assert c.get("/users/u2/preferences").json() == {"user_id": "u2", "preferences": None, "status": "not_set"}
    saved = c.put("/users/u2/preferences", json={"max_distance_km": 50, "criteria": {"age": {"min": 25, "max": 35, "hard": True}, "zodiac": {"values": ["leo"]}}})
    assert saved.status_code == 200 and saved.json()["normalized"]["max_distance_km"] == 50 and len(saved.json()["warnings"]) == 1
    assert c.get("/users/u2/preferences").json()["status"] == "set"
    assert c.get("/users/u1/preferences").json()["preferences"]["criteria"]["profession_group"]["values"] == ["technology_science"]


def test_recommendations_endpoint_shape_limit_and_unknowns():
    c, _ = client()
    r = c.get("/users/u1/recommendations", params={"limit": 5})
    body = r.json()
    assert r.status_code == 200 and len(body) == 5 and all(b["eligibility"]["eligible"] for b in body)
    assert {"compatibility", "location", "preferences", "behavior", "mutual_interest", "ranking", "explanation"} <= set(body[0])
    assert body[0]["behavior"]["status"] == "cold_start" and body[0]["mutual_interest"]["probability"] is None
    assert c.get("/users/u1/recommendations", params={"limit": 0}).status_code == 422
    assert c.get("/users/ghost/recommendations").status_code == 404
    default = c.get("/users/u1/recommendations").json()
    assert len(default) <= 20


def test_recommendations_use_behavior_when_enough_events():
    c, _ = client()
    body = c.get("/users/u2/recommendations", params={"limit": 3}).json()
    assert all(b["behavior"]["status"] == "sufficient_data" for b in body)
    assert "m01" not in {b["candidate_id"] for b in c.get("/users/u2/recommendations", params={"limit": 50}).json()}     # already decided


def test_preference_profile_endpoint():
    c, _ = client()
    p = c.get("/users/u2/preference-profile").json()
    assert p["behavior_status"] == "sufficient_data" and "profession_group" in p["learned_preferences"]
    cold = c.get("/users/u1/preference-profile").json()
    assert cold["behavior_status"] == "cold_start" and cold["learned_preferences"] == {} and cold["explicit_preferences"] is not None
    few = c.get("/users/u3/preference-profile").json()
    assert few["behavior_status"] == "insufficient_data" and few["learned_preferences"] == {}


def test_new_interaction_changes_next_recommendations_exclusion():
    c, _ = client(events=[])
    before = {b["candidate_id"] for b in c.get("/users/u1/recommendations", params={"limit": 50}).json()}
    c.post("/interactions", json={"user_id": "u1", "candidate_id": "m01", "action": "PASS"})
    after = {b["candidate_id"] for b in c.get("/users/u1/recommendations", params={"limit": 50}).json()}
    assert "m01" in before and "m01" not in after

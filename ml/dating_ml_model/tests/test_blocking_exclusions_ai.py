import pytest

from dating_ml_model.backend_integration_example import create_app
from dating_ml_model.model import CompatibilityModel
from dating_ml_model.preferences import evaluate_preferences
from dating_ml_model.preference_interpreter import _local_interpret
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.tests.reco_fixtures import PROFILES, U1, man
from fastapi.testclient import TestClient


def make_client():
    profiles = list(PROFILES) + [
        man("konkan", state="Konkan", region="Konkan"),
        man("unknown-region", state=None, region=None),
    ]
    repo = InMemoryRecommendationRepository(profiles)
    return TestClient(create_app(repo, preference_ai_client=_local_interpret)), repo


def test_block_and_unblock_are_persistent_and_backend_enforced():
    client, _ = make_client()
    assert client.post("/users/u1/blocks/konkan").status_code == 200
    ids = {row["candidate_id"] for row in client.get("/users/u1/recommendations", params={"limit": 100}).json()}
    assert "konkan" not in ids
    assert "konkan" not in {row["id"] for row in client.post("/users/u1/search").json()}
    assert client.delete("/users/u1/blocks/konkan").json()["blocked"] is False
    assert "konkan" in {row["id"] for row in client.post("/users/u1/search").json()}


def test_hard_exclusion_is_separate_and_only_excludes_explicit_value():
    client, _ = make_client()
    saved = client.put("/users/u1/preferences", json={
        "hard_exclusions": {"region": {"values": ["Konkan"]}},
        "criteria": {"religion": {"values": ["buddhism"], "hard": False}},
    })
    assert saved.status_code == 200
    ids = {row["candidate_id"] for row in client.get("/users/u1/recommendations", params={"limit": 100}).json()}
    assert "konkan" not in ids
    assert "unknown-region" in ids


def test_interpreter_requires_clarification_and_confirmation_before_save():
    client, _ = make_client()
    ambiguous = client.post("/users/u1/preferences/interpret", json={"request": "I want someone traditional"})
    assert ambiguous.status_code == 200 and ambiguous.json()["status"] == "clarification_required"
    interpreted = client.post("/users/u1/preferences/interpret", json={"request": "exclude Konkan region"})
    assert interpreted.json()["status"] == "confirmation_required"
    assert client.get("/users/u1/preferences").json()["status"] == "not_set"
    confirmed = interpreted.json()
    confirmed["confirmed"] = True
    assert client.post("/users/u1/preferences/confirm", json=confirmed).status_code == 200


def test_invalid_ai_response_is_rejected_and_missing_attributes_stay_unknown():
    client, _ = make_client()
    response = client.post("/users/u1/preferences/interpret", json={"request": "exclude Konkan region"})
    assert response.status_code == 200
    with pytest.raises(ValueError):
        from dating_ml_model.preference_interpreter import interpret_preference_request
        interpret_preference_request("exclude Konkan region", ai_client=lambda _: {"status": "confirmation_required", "preferences": {"hard_exclusions": {"religion": {"values": [""]}}}})
    config = CompatibilityModel().config
    result = evaluate_preferences({"hard_exclusions": {"region": {"values": ["Konkan"]}}}, {"id": "x"}, config)
    assert result["hard_failures"] == []


def test_compatibility_predictions_are_unchanged():
    client, _ = make_client()
    before = CompatibilityModel().predict_pair(U1, PROFILES[3])
    after = client.post("/compatibility/pair", json={"profile_a": U1, "profile_b": PROFILES[3]}).json()
    assert after == before

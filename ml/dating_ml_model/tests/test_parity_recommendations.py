"""Notebook == exported package == service layer == HTTP backend, for the recommendation pipeline."""
import json
from pathlib import Path

import pytest

from dating_ml_model import RecommendationModel
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService
from dating_ml_model.tests.helpers import assert_same
from dating_ml_model.tests.make_golden_reco import USERS, build_reco_golden
from dating_ml_model.tests.reco_fixtures import INTERACTIONS, NOW, PREFERENCES, PROFILES

GOLDEN = json.loads((Path(__file__).with_name("golden_recommendations.json")).read_text())


def repo():
    return InMemoryRecommendationRepository(PROFILES, INTERACTIONS, PREFERENCES)


def test_exported_model_equals_notebook_golden():
    assert_same(GOLDEN, json.loads(json.dumps(build_reco_golden(RecommendationModel()))))


def test_golden_is_non_trivial():
    assert all(len(GOLDEN[u]) >= 3 for u in USERS) and GOLDEN["u2"][0]["behavior"]["status"] == "sufficient_data"
    assert GOLDEN["u1"][0]["behavior"]["status"] == "cold_start" and GOLDEN["u3"][0]["behavior"]["status"] == "insufficient_data"


def test_service_layer_equals_golden():
    service = RecommendationService(RecommendationModel().compatibility, repo(), clock=lambda: NOW)
    for uid in USERS:
        assert_same(GOLDEN[uid], json.loads(json.dumps(service.get_recommendations(uid, limit=8))), uid)


def test_http_backend_equals_golden():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dating_ml_model.backend_integration_example import create_app

    client = TestClient(create_app(repo(), clock=lambda: NOW))
    for uid in USERS:
        r = client.get(f"/users/{uid}/recommendations", params={"limit": 8})
        assert r.status_code == 200
        assert_same(GOLDEN[uid], r.json(), uid)


def test_repeated_runs_identical():
    runs = {json.dumps(build_reco_golden(RecommendationModel()), sort_keys=True) for _ in range(4)}
    assert len(runs) == 1

"""Notebook == exported package == backend.

`golden_predictions.json` is written by the notebook from the notebook's model.
These tests recompute everything from the packaged code (directly, through the
service layer, and through the HTTP API) and require agreement to <= 1e-4.
"""
import json
import math
from pathlib import Path

import pytest

from dating_ml_model import CompatibilityModel
from dating_ml_model.tests.fixtures import PARITY_PROFILES

GOLDEN = json.loads((Path(__file__).with_name("golden_predictions.json")).read_text())
TOL = 1e-4


def assert_same(x, y, path="root"):
    if isinstance(x, dict):
        assert isinstance(y, dict) and x.keys() == y.keys(), f"{path}: keys differ"
        for k in x:
            assert_same(x[k], y[k], f"{path}.{k}")
    elif isinstance(x, list):
        assert isinstance(y, list) and len(x) == len(y), f"{path}: length differs"
        for i, (p, q) in enumerate(zip(x, y)):
            assert_same(p, q, f"{path}[{i}]")
    elif isinstance(x, float) or isinstance(y, float):
        assert x is not None and y is not None and math.isclose(x, y, abs_tol=TOL), f"{path}: {x} != {y}"
    else:
        assert x == y, f"{path}: {x!r} != {y!r}"


def pair_key(a, b):
    return f"{a['id']}|{b['id']}"


PAIRS = [(a, b) for a in PARITY_PROFILES for b in PARITY_PROFILES]


def test_golden_covers_all_pairs():
    assert set(GOLDEN["pairs"]) == {pair_key(a, b) for a, b in PAIRS}


def test_exported_model_equals_notebook_model():
    model = CompatibilityModel()
    for a, b in PAIRS:
        assert_same(GOLDEN["pairs"][pair_key(a, b)], model.predict_pair(a, b), pair_key(a, b))


def test_eligibility_identical():
    model = CompatibilityModel()
    for a, b in PAIRS:
        expected = GOLDEN["pairs"][pair_key(a, b)]
        result = model.check_eligibility(a, b)
        assert result["eligible"] == expected["eligible"]
        assert result["reason"] == expected["eligibility_reason"]


def test_categories_and_adjusted_identical():
    model = CompatibilityModel()
    for a, b in PAIRS:
        expected, actual = GOLDEN["pairs"][pair_key(a, b)], model.predict_pair(a, b)
        assert_same(expected["categories"], actual["categories"])
        assert_same(expected["adjusted_score"], actual["adjusted_score"])


def test_repeated_runs_identical():
    model = CompatibilityModel()
    first = json.dumps([model.predict_pair(a, b) for a, b in PAIRS], sort_keys=True)
    for _ in range(5):
        assert json.dumps([CompatibilityModel().predict_pair(a, b) for a, b in PAIRS], sort_keys=True) == first


def test_matches_identical():
    model = CompatibilityModel()
    for user in PARITY_PROFILES:
        expected = GOLDEN["matches"][user["id"]]
        actual = model.predict_matches(user, PARITY_PROFILES, top_k=5)
        assert_same(expected, actual, f"matches[{user['id']}]")


def _repo(tmp_path):
    import pandas as pd
    from dating_ml_model.repository import CsvProfileRepository

    path = tmp_path / "profiles.csv"
    pd.DataFrame(PARITY_PROFILES).to_csv(path, index=False)
    return CsvProfileRepository(str(path), id_column="id")


def test_service_layer_equals_model(tmp_path):
    from dating_ml_model.service import MatchingService

    service = MatchingService(CompatibilityModel(), _repo(tmp_path))
    for user in PARITY_PROFILES:
        assert_same(GOLDEN["matches"][user["id"]], service.get_matches(user["id"], top_k=5), f"service[{user['id']}]")


def test_http_backend_equals_notebook_model(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from dating_ml_model.backend_integration_example import create_app

    client = TestClient(create_app(_repo(tmp_path)))
    for a, b in PAIRS:
        response = client.post("/compatibility/pair", json={"profile_a": a, "profile_b": b})
        assert response.status_code == 200
        assert_same(GOLDEN["pairs"][pair_key(a, b)], response.json(), pair_key(a, b))
    for user in PARITY_PROFILES:
        response = client.get(f"/matches/{user['id']}", params={"top_k": 5})
        assert response.status_code == 200
        assert_same(GOLDEN["matches"][user["id"]], response.json(), f"http[{user['id']}]")
    assert client.get("/matches/does-not-exist").status_code == 404
    assert client.get("/matches/a", params={"top_k": 0}).status_code == 422

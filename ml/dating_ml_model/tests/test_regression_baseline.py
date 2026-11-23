"""v2.1.0 -> v2.2.0 regression: the validated compatibility engine must not change.

`golden_predictions_v2.1.0_baseline.json` is the ORIGINAL golden file and is never regenerated.
"""
import hashlib
import json
from pathlib import Path

from dating_ml_model import CompatibilityModel
from dating_ml_model.compatibility_engine import load_config
from dating_ml_model.tests.fixtures import FULL_A, FULL_B, PARITY_PROFILES, variant
from dating_ml_model.tests.helpers import assert_same

HERE = Path(__file__).parent
PKG = HERE.parent
BASE = json.loads((HERE / "golden_predictions_v2.1.0_baseline.json").read_text())
HASHES = json.loads((HERE / "baseline_hashes_v2.1.0.json").read_text())
M = CompatibilityModel()
sha = lambda b: hashlib.sha256(b).hexdigest()


def test_baseline_golden_pairs_unchanged():
    assert len(BASE["pairs"]) == 64
    for a in PARITY_PROFILES:
        for b in PARITY_PROFILES:
            assert_same(BASE["pairs"][f"{a['id']}|{b['id']}"], M.predict_pair(a, b), f"{a['id']}|{b['id']}")


def test_baseline_golden_matches_unchanged():
    for user in PARITY_PROFILES:
        assert_same(BASE["matches"][user["id"]], M.predict_matches(user, PARITY_PROFILES, top_k=5), f"matches[{user['id']}]")


def test_core_engine_files_are_byte_identical_to_v2_1_0():
    for name, digest in HASHES["unchanged_files"].items():
        assert sha((PKG / name).read_bytes()) == digest, f"{name} changed"


def test_extended_modules_only_appended_never_edited():
    for name, spec in HASHES["append_only_files"].items():
        assert sha((PKG / name).read_bytes()[: spec["prefix_bytes"]]) == spec["sha256"], f"{name}: original section was edited"


def test_original_config_keys_unchanged():
    old = json.loads((HERE / "config_v2.1.0_baseline.json").read_text())
    new = load_config()
    for key, value in old.items():
        assert new[key] == value, f"config key '{key}' changed"


def test_existing_stability_properties():
    # eligibility, missing-data, profession, attraction, shrinkage and explanations (spot checks on top of the golden files)
    assert not M.check_eligibility(variant(FULL_A, orientation="gay"), FULL_B)["eligible"]
    assert M.score_pair(FULL_A, FULL_B)["compatibility_score"] == 84.9667
    assert M.score_pair({}, {})["adjusted_score"] == 50.0
    assert M.score_pair({"age": 30}, {"age": 30})["adjusted_score"] == 60.0
    assert M.score_pair(FULL_A, FULL_B)["components"]["career_education"]["profession"] == 0.5
    assert M.score_pair(FULL_A, FULL_B)["categories"]["attraction"] == 66.6667
    assert M.predict_pair(FULL_A, FULL_B)["model_version"] == "2.1.0"                  # compatibility engine version is unchanged
    assert "Same broad profession group" in M.predict_pair(FULL_A, FULL_B)["explanation"]


def test_compatibility_is_independent_of_location_preferences_and_behavior():
    far = variant(FULL_B, id="far", city="London", country="United Kingdom")
    near = variant(FULL_B, id="near", city="Pune", state="Maharashtra", country="India")
    a = variant(FULL_A, city="Pune", state="Maharashtra", country="India", relationship_intention="long_term", preferred_distance_km=5)
    assert_same(M.score_pair(a, far)["categories"], M.score_pair(a, near)["categories"])
    assert M.score_pair(a, far)["adjusted_score"] == M.score_pair(a, near)["adjusted_score"] == M.score_pair(FULL_A, FULL_B)["adjusted_score"]

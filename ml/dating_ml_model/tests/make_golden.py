"""Writes golden_predictions.json from the CURRENT model (the notebook runs this)."""
import json
from pathlib import Path

from dating_ml_model import CompatibilityModel
from dating_ml_model.tests.fixtures import PARITY_PROFILES


def build_golden(model=None):
    model = model or CompatibilityModel()
    pairs = {f"{a['id']}|{b['id']}": model.predict_pair(a, b) for a in PARITY_PROFILES for b in PARITY_PROFILES}
    matches = {u["id"]: model.predict_matches(u, PARITY_PROFILES, top_k=5) for u in PARITY_PROFILES}
    return {"pairs": pairs, "matches": matches}


if __name__ == "__main__":
    out = Path(__file__).with_name("golden_predictions.json")
    out.write_text(json.dumps(build_golden(), indent=1, sort_keys=True))
    print("wrote", out)

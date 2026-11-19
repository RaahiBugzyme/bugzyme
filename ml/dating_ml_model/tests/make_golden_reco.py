"""Writes golden_recommendations.json from the CURRENT RecommendationModel (the notebook runs this)."""
import json
from pathlib import Path

from dating_ml_model import RecommendationModel
from dating_ml_model.tests.reco_fixtures import INTERACTIONS, NOW, PREFERENCES, PROFILES

USERS = ("u1", "u2", "u3")


def build_reco_golden(model=None):
    model = model or RecommendationModel()
    by_id = {p["id"]: p for p in PROFILES}
    out = {}
    for uid in USERS:
        user = by_id[uid]
        events = [e for e in INTERACTIONS if e["user_id"] == uid]
        out[uid] = model.recommend(user, [p for p in PROFILES if p["id"] != uid], user_preferences=PREFERENCES.get(uid),
                                   preferences_lookup=lambda i: PREFERENCES.get(i), interactions=events,
                                   profile_lookup=by_id.get, now=NOW, limit=8)
    return out


if __name__ == "__main__":
    path = Path(__file__).with_name("golden_recommendations.json")
    path.write_text(json.dumps(build_reco_golden(), indent=1, sort_keys=True))
    print("wrote", path)

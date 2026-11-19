"""Mechanics tests. The synthetic log below is a TEST FIXTURE with a planted rule, used only to prove the
pipeline trains / splits chronologically / refuses to train without enough data. It is never shipped or reported."""
import copy
from datetime import datetime, timedelta

import numpy as np
import pytest

from dating_ml_model import RecommendationModel
from dating_ml_model import mutual_interest as MI
from dating_ml_model.tests.reco_fixtures import HEALTH, TECH, man, woman

BASE = datetime(2026, 1, 1)


def synthetic(n_users=26, seed=0):
    rng = np.random.RandomState(seed)
    women = [woman(f"w{i}", age=int(rng.randint(24, 40)), height=int(rng.randint(60, 70))) for i in range(n_users)]
    men = [man(f"m{i}", age=int(rng.randint(24, 45)), job=[TECH, HEALTH, "student"][i % 3], height=int(rng.randint(64, 76)),
               smokes=["no", "yes"][int(rng.randint(0, 2))]) for i in range(n_users)]
    profiles = {p["id"]: p for p in women + men}
    events, k = [], 0
    for w in women:
        for m in men:
            like = m["job"] == TECH or (m["smokes"] == "no" and rng.rand() < 0.3)      # planted rule
            events.append({"user_id": w["id"], "candidate_id": m["id"], "action": "LIKE" if like else "PASS",
                           "timestamp": (BASE + timedelta(hours=k)).isoformat() + "Z"})
            k += 1
    return profiles, events


@pytest.fixture(scope="module")
def trained():
    profiles, events = synthetic()
    model = RecommendationModel()
    cfg = copy.deepcopy(model.config)
    cfg["mutual_interest_min_training_rows"] = 300
    now = BASE + timedelta(days=400)
    result = MI.train_mutual_interest_model(events, profiles.get, model.compatibility.engine, cfg, now=now)
    return result, profiles, events, cfg, now


def test_insufficient_data_returns_explicit_state_no_fake_probability():
    profiles, events = synthetic(n_users=4)                                  # 16 rows << 1000
    model = RecommendationModel()
    result = MI.train_mutual_interest_model(events, profiles.get, model.compatibility.engine, model.config, now=BASE + timedelta(days=100))
    assert result["status"] == "insufficient_behavioral_data" and result["model"] is None and result["report"]["rows_available"] == 16
    out = MI.UNAVAILABLE.predict_mutual(profiles["w0"], profiles["m0"], model.compatibility.engine, model.config)
    assert out == {"probability": None, "confidence": 0.0, "status": "insufficient_behavioral_data", "model_version": None}


def test_disabled_flag():
    cfg = copy.deepcopy(RecommendationModel().config)
    cfg["mutual_interest_enabled"] = False
    out = MI.UNAVAILABLE.predict_mutual({}, {}, None, cfg)
    assert out["status"] == "disabled" and out["probability"] is None


def test_single_class_is_refused():
    profiles, events = synthetic()
    only_pass = [{**e, "action": "PASS"} for e in events]
    model = RecommendationModel()
    cfg = copy.deepcopy(model.config); cfg["mutual_interest_min_training_rows"] = 300
    result = MI.train_mutual_interest_model(only_pass, profiles.get, model.compatibility.engine, cfg, now=BASE + timedelta(days=400))
    assert result["status"] == "insufficient_behavioral_data" and "class" in result["report"]["reason"]


def test_training_is_chronological_and_documented(trained):
    result, _, events, _, now = trained
    assert result["status"] == "available"
    meta = result["model"].metadata
    split = meta["split"]
    assert split["train_cutoff"] < split["validation_cutoff"] <= split["test_end"]
    assert all(split["rows"][s] > 0 for s in ("train", "validation", "test")) and sum(split["rows"].values()) == len(events)
    for key in ("target", "features", "selected_model", "test_metrics", "test_calibration", "test_ranking_metrics", "limitations",
                "no_skill_pr_auc", "confidence_definition", "trained_at", "validity"):
        assert key in meta
    for key in ("accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "confusion_matrix"):
        assert key in meta["test_metrics"]
    for key in ("precision@5", "recall@5", "hit_rate@5", "ndcg@5", "map@5", "users_evaluated"):
        assert key in meta["test_ranking_metrics"]
    assert "NOT relationship success" in meta["target"] or "not relationship success" in meta["validity"].lower()


def test_no_future_events_used_in_training():
    profiles, events = synthetic()
    model = RecommendationModel()
    cfg = copy.deepcopy(model.config); cfg["mutual_interest_min_training_rows"] = 300
    cutoff = BASE + timedelta(hours=400)
    frame, _ = MI.build_training_frame(events, profiles.get, model.compatibility.engine, cfg, None, cutoff)
    assert len(frame) < len(events) and frame["timestamp"].max() <= cutoff
    assert set(MI.FEATURES) <= set(frame.columns) and not any("id" in f for f in MI.FEATURES)        # no ID features => no memorization


def test_prediction_is_product_of_directional_probabilities_and_is_bounded(trained):
    result, profiles, _, cfg, _ = trained
    mi, engine = result["model"], RecommendationModel().compatibility.engine
    a, b = profiles["w0"], profiles["m0"]
    out = mi.predict_mutual(a, b, engine, cfg)
    pab, pba = mi._directional(a, b, engine, cfg, None), mi._directional(b, a, engine, cfg, None)
    assert out["status"] == "available" and 0 <= out["probability"] <= 1 and out["probability"] == pytest.approx(pab * pba, abs=1e-4)
    assert 0 <= out["confidence"] <= 100


def test_learned_model_reflects_planted_rule_only_as_a_mechanics_check(trained):
    result, profiles, _, cfg, _ = trained
    mi, engine = result["model"], RecommendationModel().compatibility.engine
    tech = np.mean([mi._directional(profiles[f"w{i}"], profiles[f"m{j}"], engine, cfg, None) for i in range(5) for j in range(0, 26, 3)])
    other = np.mean([mi._directional(profiles[f"w{i}"], profiles[f"m{j}"], engine, cfg, None) for i in range(5) for j in range(1, 26, 3)])
    assert tech > other


def test_save_load_roundtrip(trained, tmp_path):
    result, profiles, _, cfg, _ = trained
    path = str(tmp_path / "mi.joblib")
    result["model"].save(path)
    loaded, engine = MI.MutualInterestModel.load(path), RecommendationModel().compatibility.engine
    a, b = profiles["w1"], profiles["m4"]
    assert loaded.predict_mutual(a, b, engine, cfg) == result["model"].predict_mutual(a, b, engine, cfg)


def test_attached_model_flows_into_recommendations_with_confidence_scaled_weight(trained):
    result, profiles, _, cfg, now = trained
    rm = RecommendationModel(cfg, mutual_interest_model=result["model"])
    rec = rm.recommend(profiles["w0"], [profiles["m1"], profiles["m2"]], now=now)[0]
    assert rec["mutual_interest"]["status"] == "available"
    comp = next(c for c in rec["ranking"]["components"] if c["signal"] == "mutual_interest")
    assert comp["effective_weight"] <= comp["base_weight"] and any("not a relationship-success probability" in l for l in rec["explanation"])


# ---- ranking metrics against hand-computed values -------------------------------------------------------------
def test_ranking_metrics_hand_computed():
    perfect = {"u": [(0.9, 1), (0.8, 1), (0.1, 0), (0.05, 0)]}
    worst = {"u": [(0.9, 0), (0.8, 0), (0.1, 1), (0.05, 1)]}
    p = MI.ranking_metrics(perfect, ks=(2,))
    w = MI.ranking_metrics(worst, ks=(2,))
    assert (p["precision@2"], p["recall@2"], p["hit_rate@2"], p["ndcg@2"], p["map@2"]) == (1, 1, 1, 1, 1)
    assert (w["precision@2"], w["recall@2"], w["hit_rate@2"], w["ndcg@2"], w["map@2"]) == (0, 0, 0, 0, 0)
    mixed = MI.ranking_metrics({"u": [(0.9, 0), (0.8, 1), (0.1, 0), (0.05, 1)]}, ks=(2,))
    assert mixed["precision@2"] == 0.5 and mixed["recall@2"] == 0.5 and mixed["hit_rate@2"] == 1
    assert mixed["ndcg@2"] == pytest.approx((1 / np.log2(3)) / (1 + 1 / np.log2(3)), abs=1e-6) and mixed["map@2"] == pytest.approx(0.25)
    assert MI.ranking_metrics({"u": [(0.5, 0), (0.4, 0)]})["users_evaluated"] == 0       # users without positives are skipped

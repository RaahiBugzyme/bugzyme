"""Optional mutual-interest model (supervised, trained ONLY on genuine interaction logs).

Target: the observed decision of a user on a shown candidate: LIKE/SUPER_LIKE = 1, PASS = 0
(directional). Mutual interest for (A, B) = p(A likes B) x p(B likes A)  (independence assumption,
documented). No synthetic labels are ever created; with too little data the status is
"insufficient_behavioral_data" and the probability is null.

Leakage control: features are PAIR features computed from the two profiles only (compatibility
components, distance, signed age/height difference). No event-derived features, no IDs. The split is
CHRONOLOGICAL (train < validation < test by event timestamp); cutoffs are recorded in the metadata.
Limitation: profiles are read at training time (no profile-history snapshots), so later profile edits
can leak backwards unless the repository supplies as-of snapshots.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import feature_engineering as fe
from .behavior import DECISION_ACTIONS, POSITIVE_DECISIONS, format_timestamp, latest_decisions, usable_events, utcnow
from .location import GeoResolver, compare_locations

COMPONENT_NAMES = ("age", "generation", "education", "profession", "religion", "ethnicity", "drinks", "drugs",
                   "smokes", "diet", "offspring", "pets", "height", "body_type")
FEATURES = tuple(f"sim_{n}" for n in COMPONENT_NAMES) + ("distance_km", "location_score", "age_difference", "height_difference")
STATUS_OK, STATUS_DISABLED, STATUS_INSUFFICIENT = "available", "disabled", "insufficient_behavioral_data"
LIMITATIONS = [
    "Directional like/pass decisions of the platform's own users; not relationship success.",
    "Profiles are read at training time (no as-of snapshots): later profile edits can leak into earlier rows.",
    "Mutual probability multiplies two directional probabilities (independence assumption).",
    "Selection bias: users only decide on candidates the previous recommender chose to show.",
    "Uses pair-similarity features only (no candidate popularity or absolute attributes), so it cannot learn effects such as 'this profile is liked by everyone'.",
]


def _nan(x: Optional[float]) -> float:
    return float("nan") if x is None else float(x)


def pair_features(user: Dict[str, Any], candidate: Dict[str, Any], compat_engine, config: Dict[str, Any],
                  resolver: Optional[GeoResolver] = None) -> Dict[str, float]:
    comps = compat_engine.score_pair(user, candidate)["components"]
    flat = {n: v for cat in comps.values() for n, v in cat.items()}
    loc = compare_locations(user, candidate, config, resolver)
    ref = int(config["reference_year"])
    u, c = fe.profile_attributes(user, ref), fe.profile_attributes(candidate, ref)
    row = {f"sim_{n}": _nan(flat.get(n)) for n in COMPONENT_NAMES}
    row["distance_km"] = _nan(loc["distance_km"])
    row["location_score"] = _nan(loc["location_score"])
    row["age_difference"] = _nan(None if u["age"] is None or c["age"] is None else c["age"] - u["age"])
    row["height_difference"] = _nan(None if u["height"] is None or c["height"] is None else c["height"] - u["height"])
    return row


# ------------------------------------------------------------------ metrics
def classification_metrics(y_true, p, threshold: float) -> Dict[str, Any]:
    from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss, confusion_matrix,
                                 f1_score, precision_score, recall_score, roc_auc_score)
    pred = (p >= threshold).astype(int)
    return {"threshold": round(float(threshold), 3), "accuracy": float(accuracy_score(y_true, pred)),
            "precision": float(precision_score(y_true, pred, zero_division=0)),
            "recall": float(recall_score(y_true, pred, zero_division=0)), "f1": float(f1_score(y_true, pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(y_true, p)), "pr_auc": float(average_precision_score(y_true, p)),
            "brier": float(brier_score_loss(y_true, p)), "confusion_matrix": confusion_matrix(y_true, pred, labels=[0, 1]).tolist()}


def ranking_metrics(per_user: Dict[str, List[Tuple[float, int]]], ks=(5, 10)) -> Dict[str, Any]:
    """Precision/Recall/HitRate/NDCG/MAP @K over users with >=1 positive and >=2 items (k capped at list length)."""
    out: Dict[str, Any] = {"users_evaluated": 0}
    users = [(uid, sorted(items, key=lambda t: -t[0])) for uid, items in sorted(per_user.items())
             if len(items) >= 2 and any(l for _, l in items)]
    out["users_evaluated"] = len(users)
    for k in ks:
        p_sum = r_sum = h_sum = n_sum = ap_sum = 0.0
        for _, ranked in users:
            rel = [l for _, l in ranked][:k]
            total_pos = sum(l for _, l in ranked)
            hits = sum(rel)
            p_sum += hits / max(1, len(rel))
            r_sum += hits / total_pos
            h_sum += 1.0 if hits else 0.0
            dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel))
            ideal = sorted([l for _, l in ranked], reverse=True)[:k]
            idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
            n_sum += dcg / idcg if idcg else 0.0
            seen, ap = 0, 0.0
            for i, r in enumerate(rel):
                if r:
                    seen += 1
                    ap += seen / (i + 1)
            ap_sum += ap / min(total_pos, k)
        n = max(1, len(users))
        out[f"precision@{k}"], out[f"recall@{k}"], out[f"hit_rate@{k}"] = p_sum / n, r_sum / n, h_sum / n
        out[f"ndcg@{k}"], out[f"map@{k}"] = n_sum / n, ap_sum / n
    return out


# ----------------------------------------------------------------- training
def build_training_frame(interactions: List[Dict[str, Any]], profile_lookup: Callable[[str], Optional[Dict[str, Any]]],
                         compat_engine, config: Dict[str, Any], resolver: Optional[GeoResolver], now: datetime):
    """One row per (user, candidate): the LATEST decision known at `now`. Rows lacking either profile are skipped."""
    import pandas as pd

    by_user: Dict[str, List[Dict[str, Any]]] = {}
    for e in interactions:
        by_user.setdefault(str(e.get("user_id")), []).append(e)
    rows, skipped = [], 0
    for user_id in sorted(by_user):
        kept, _ = usable_events(by_user[user_id], user_id, now)
        user = profile_lookup(user_id)
        for cand_id, event in sorted(latest_decisions(kept).items()):
            cand = profile_lookup(cand_id)
            if user is None or cand is None:
                skipped += 1
                continue
            row = pair_features(user, cand, compat_engine, config, resolver)
            row.update(user_id=user_id, candidate_id=cand_id, timestamp=event["_ts"],
                       label=int(event["action"] in POSITIVE_DECISIONS))
            rows.append(row)
    return pd.DataFrame(rows), skipped


def train_mutual_interest_model(interactions, profile_lookup, compat_engine, config, resolver=None,
                                now: Optional[datetime] = None, output_path: Optional[str] = None,
                                random_state: int = 42) -> Dict[str, Any]:
    """Returns {"status": ..., "model": MutualInterestModel|None, "report": {...}}. Never fabricates labels."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, f1_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.calibration import calibration_curve

    now = now or utcnow()
    min_rows = int(config["mutual_interest_min_training_rows"])
    frame, skipped = build_training_frame(interactions, profile_lookup, compat_engine, config, resolver, now)
    report: Dict[str, Any] = {"rows_available": int(len(frame)), "rows_required": min_rows, "skipped_missing_profile": skipped}
    if len(frame) < min_rows:
        return {"status": STATUS_INSUFFICIENT, "model": None, "report": {**report, "reason": "fewer rows than mutual_interest_min_training_rows"}}

    frame = frame.sort_values(["timestamp", "user_id", "candidate_id"], kind="mergesort").reset_index(drop=True)
    fr = config["mutual_interest_split_fractions"]
    n = len(frame)
    t_train = frame["timestamp"].iloc[max(0, int(n * fr["train"]) - 1)]
    t_val = frame["timestamp"].iloc[max(0, int(n * (fr["train"] + fr["validation"])) - 1)]
    split = np.where(frame["timestamp"] <= t_train, "train", np.where(frame["timestamp"] <= t_val, "validation", "test"))
    parts = {s: frame[split == s] for s in ("train", "validation", "test")}
    report["split"] = {"train_cutoff": format_timestamp(t_train), "validation_cutoff": format_timestamp(t_val),
                       "test_end": format_timestamp(frame["timestamp"].iloc[-1]),
                       "rows": {s: int(len(p)) for s, p in parts.items()},
                       "positive_rate": {s: (float(p["label"].mean()) if len(p) else None) for s, p in parts.items()}}
    if any(len(p) == 0 or p["label"].nunique() < 2 for p in parts.values()):
        return {"status": STATUS_INSUFFICIENT, "model": None,
                "report": {**report, "reason": "a chronological split lacks rows or one of the two classes"}}

    X = {s: p[list(FEATURES)].astype(float) for s, p in parts.items()}
    y = {s: p["label"].astype(int).values for s, p in parts.items()}
    imp = lambda: SimpleImputer(strategy="median", keep_empty_features=True)
    candidates = {
        "logistic_regression": Pipeline([("imp", imp()), ("sc", StandardScaler()), ("m", LogisticRegression(max_iter=3000, class_weight="balanced"))]),
        "random_forest": Pipeline([("imp", imp()), ("m", RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced_subsample", random_state=random_state, n_jobs=-1))]),
        "hist_gradient_boosting": Pipeline([("imp", imp()), ("m", HistGradientBoostingClassifier(random_state=random_state))]),
    }
    val_pr = {}
    for name, pipe in candidates.items():
        pipe.fit(X["train"], y["train"])
        val_pr[name] = float(average_precision_score(y["validation"], pipe.predict_proba(X["validation"])[:, 1]))
    best = max(sorted(candidates), key=lambda k: val_pr[k])
    pipe = candidates[best]
    p_val, p_test = pipe.predict_proba(X["validation"])[:, 1], pipe.predict_proba(X["test"])[:, 1]
    grid = np.round(np.arange(0.05, 0.96, 0.05), 2)
    threshold = float(max(grid, key=lambda t: (f1_score(y["validation"], (p_val >= t).astype(int), zero_division=0), -t)))
    test = classification_metrics(y["test"], p_test, threshold)
    frac_pos, mean_pred = calibration_curve(y["test"], p_test, n_bins=min(8, max(2, len(p_test) // 20)), strategy="quantile")
    per_user: Dict[str, List[Tuple[float, int]]] = {}
    for uid, p, lab in zip(parts["test"]["user_id"], p_test, y["test"]):
        per_user.setdefault(uid, []).append((float(p), int(lab)))
    confidence = max(0.0, min(1.0, 2.0 * test["roc_auc"] - 1.0))   # normalized Gini: skill above chance
    metadata = {
        "package_model": "mutual_interest (directional like probability)", "target": "LIKE/SUPER_LIKE = 1, PASS = 0 (latest decision per user-candidate)",
        "features": list(FEATURES), "selected_model": best, "validation_pr_auc": val_pr,
        "split": report["split"], "threshold": threshold, "test_metrics": test,
        "test_calibration": {"mean_predicted": [round(float(v), 4) for v in mean_pred], "observed_rate": [round(float(v), 4) for v in frac_pos]},
        "test_ranking_metrics": ranking_metrics(per_user), "no_skill_pr_auc": float(np.mean(y["test"])),
        "confidence_definition": "max(0, 2*test_ROC_AUC - 1) (discrimination above chance)", "confidence": confidence,
        "trained_at": format_timestamp(now), "limitations": LIMITATIONS,
        "validity": "Not relationship success. Do not use for ranking unless test metrics clearly beat no-skill.",
    }
    model = MutualInterestModel(pipe, list(FEATURES), metadata)
    if output_path:
        model.save(output_path)
    return {"status": STATUS_OK, "model": model, "report": {**report, "metadata": metadata}}


# ------------------------------------------------------------------ predictor
class MutualInterestModel:
    def __init__(self, pipeline=None, features: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None):
        self.pipeline, self.features, self.metadata = pipeline, features or list(FEATURES), metadata or {}

    @property
    def available(self) -> bool:
        return self.pipeline is not None

    def save(self, path: str) -> None:
        import joblib
        joblib.dump({"pipeline": self.pipeline, "features": self.features, "metadata": self.metadata}, path)

    @classmethod
    def load(cls, path: str) -> "MutualInterestModel":
        import joblib
        b = joblib.load(path)
        return cls(b["pipeline"], b["features"], b["metadata"])

    def _directional(self, a, b, compat_engine, config, resolver) -> float:
        import pandas as pd
        feats = pair_features(a, b, compat_engine, config, resolver)
        return float(self.pipeline.predict_proba(pd.DataFrame([{f: feats[f] for f in self.features}]))[0, 1])

    def predict_mutual(self, a, b, compat_engine, config, resolver=None) -> Dict[str, Any]:
        if not config.get("mutual_interest_enabled", False):
            return {"probability": None, "confidence": 0.0, "status": STATUS_DISABLED, "model_version": None}
        if not self.available:
            return {"probability": None, "confidence": 0.0, "status": STATUS_INSUFFICIENT, "model_version": None}
        p = self._directional(a, b, compat_engine, config, resolver) * self._directional(b, a, compat_engine, config, resolver)
        return {"probability": round(p, 4), "confidence": round(100.0 * self.metadata.get("confidence", 0.0), 4),
                "status": STATUS_OK, "model_version": self.metadata.get("trained_at")}


UNAVAILABLE = MutualInterestModel()

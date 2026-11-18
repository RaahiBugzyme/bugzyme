"""UserPreferenceModel: learns what a user LIKES / PASSES from profile features (not from candidate IDs).

Candidate score = evidence-weighted average of the learned preferences of the candidate's tokens, where each token is
weighted by confidence x |preference - the user's own baseline like rate| (decisive features dominate).
For every (feature, value) token of a decided candidate we keep recency-weighted like/pass
counts and report:  preference (smoothed like rate), confidence, evidence_count, last_updated.
Low evidence is shrunk toward the user's own overall like rate, so it can never look like a
strong preference. Only decisions known at `now` are used (no future information).

"preference" is a learned interaction tendency. It is NOT a probability of a relationship.
"""
from __future__ import annotations

import bisect
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import feature_engineering as fe
from .behavior import (NEGATIVE_DECISIONS, POSITIVE_DECISIONS, format_timestamp, latest_decisions,
                       recency_weight, summarize_behavior, usable_events)
from .location import GeoResolver, calculate_distance_km


def _bin_label(value: Optional[float], edges: List[float], unit: str) -> Optional[str]:
    if value is None:
        return None
    i = bisect.bisect_right(edges, value)
    lo = "-inf" if i == 0 else f"{edges[i - 1]:g}"
    hi = "+inf" if i == len(edges) else f"{edges[i]:g}"
    return f"[{lo},{hi}) {unit}"


def feature_tokens(user: Dict[str, Any], candidate: Dict[str, Any], config: Dict[str, Any],
                   resolver: Optional[GeoResolver] = None) -> Dict[str, List[str]]:
    """Feature -> list of categorical tokens describing `candidate` (and its relation to `user`). Unknown => absent."""
    ref = int(config["reference_year"])
    c, u = fe.profile_attributes(candidate, ref), fe.profile_attributes(user, ref)
    bins = config["behavior_bins"]
    tokens: Dict[str, List[str]] = {}

    def add(name: str, value: Any) -> None:
        if value is None:
            return
        values = sorted(value) if isinstance(value, (set, list)) else [value]
        if values:
            tokens[name] = [str(v) for v in values]

    add("profession_group", c["profession_group"])
    add("education_level", None if c["education_rank"] is None else int(round(c["education_rank"])))
    add("religion", c["religion"])
    add("ethnicity", c["ethnicity"])
    for name in ("drinks", "drugs", "smokes", "diet", "children", "body_type_group", "generation", "relationship_intention"):
        add(name, c[name])
    add("pets", c["pets"] if c["pets"] is not None else None)
    if c["age"] is not None and u["age"] is not None:
        add("age_difference", _bin_label(c["age"] - u["age"], bins["age_diff_years"], "years"))
    if c["height"] is not None and u["height"] is not None:
        add("height_difference", _bin_label(c["height"] - u["height"], bins["height_diff_inches"], "in"))
    distance = calculate_distance_km(user, candidate, resolver) if config.get("location_enabled", True) else None
    if distance is not None:
        add("distance", _bin_label(distance, bins["distance_km"], "km"))
    return tokens


class UserPreferenceModel:
    def __init__(self, config: Dict[str, Any], resolver: Optional[GeoResolver] = None):
        self.config, self.resolver = config, resolver
        self.user_id: Optional[str] = None
        self.summary: Dict[str, Any] = {}
        self.overall_like_rate: Optional[float] = None
        self._table: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.skipped_missing_profile = 0

    # ------------------------------------------------------------------ fit
    def fit(self, user: Dict[str, Any], events: List[Dict[str, Any]],
            profile_lookup: Callable[[str], Optional[Dict[str, Any]]], now: datetime) -> "UserPreferenceModel":
        self.user_id = str(user.get("id", user.get("user_id")))
        self.summary = summarize_behavior(events, self.user_id, self.config, now)
        kept, _ = usable_events(events, self.user_id, now)
        decisions = latest_decisions(kept)

        rows: List[Tuple[float, float, Dict[str, List[str]], datetime]] = []
        for candidate_id, event in decisions.items():
            profile = profile_lookup(candidate_id)
            if profile is None:
                self.skipped_missing_profile += 1
                continue
            weight = recency_weight((now - event["_ts"]).total_seconds() / 86400.0, self.config)
            liked = 1.0 if event["action"] in POSITIVE_DECISIONS else 0.0
            rows.append((weight, liked, feature_tokens(user, profile, self.config, self.resolver), event["_ts"]))

        total_w = sum(w for w, _, _, _ in rows)
        self.overall_like_rate = (sum(w * y for w, y, _, _ in rows) / total_w) if total_w > 0 else None
        k = float(self.config["min_preference_evidence"])
        raw: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for weight, liked, tokens, ts in rows:
            for feature, values in tokens.items():
                for value in values:
                    cell = raw.setdefault((feature, value), {"w": 0.0, "wl": 0.0, "n": 0, "last": ts})
                    cell["w"] += weight
                    cell["wl"] += weight * liked
                    cell["n"] += 1
                    cell["last"] = max(cell["last"], ts)
        self._table = {}
        prior = self.overall_like_rate if self.overall_like_rate is not None else 0.5
        for (feature, value), cell in sorted(raw.items()):
            pref = (cell["wl"] + k * prior) / (cell["w"] + k)         # shrink toward the user's own baseline
            conf = cell["w"] / (cell["w"] + k)                         # low evidence => low confidence
            self._table.setdefault(feature, {})[value] = {
                "preference": round(pref, 4), "confidence": round(conf, 4),
                "evidence_count": cell["n"], "weighted_evidence": round(cell["w"], 4),
                "last_updated": format_timestamp(cell["last"])}
        return self

    # ------------------------------------------------------------- inspection
    def learned_preferences(self) -> Dict[str, Any]:
        """Spec format: {feature: {value: {preference, confidence, evidence_count, last_updated}}}."""
        return {f: dict(v) for f, v in self._table.items()}

    def to_dict(self) -> Dict[str, Any]:
        status = self.summary.get("behavior_status", "cold_start")
        return {"user_id": self.user_id, "behavior_status": status,
                "behavior_confidence": self.summary.get("behavior_confidence", 0.0),
                "overall_like_rate": None if self.overall_like_rate is None else round(self.overall_like_rate, 4),
                "evidence_count": self.summary.get("evidence_count", 0),
                "skipped_decisions_missing_profile": self.skipped_missing_profile,
                "learned_preferences": self.learned_preferences() if status == "sufficient_data" else {},
                "note": ("Learned preferences are only exposed once evidence >= min_behavior_events."
                         if status != "sufficient_data" else "Learned interaction preferences; not a relationship-success predictor.")}

    # ---------------------------------------------------------------- scoring
    def score_candidate(self, user: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        status = self.summary.get("behavior_status", "cold_start")
        base = {"score": None, "confidence": 0.0, "status": status,
                "evidence_count": self.summary.get("evidence_count", 0), "supporting_features": []}
        if status in ("cold_start", "disabled"):
            return base
        if status == "insufficient_data":      # no strong preference claims below the evidence threshold
            return {**base, "confidence": self.summary.get("behavior_confidence", 0.0)}
        tokens = feature_tokens(user, candidate, self.config, self.resolver)
        n_tokens = sum(len(v) for v in tokens.values())
        baseline = self.overall_like_rate if self.overall_like_rate is not None else 0.5
        num = den = 0.0
        used = 0
        supporting = []
        for feature, values in tokens.items():
            for value in values:
                entry = self._table.get(feature, {}).get(value)
                if entry is None:
                    continue
                used += 1
                # A token is informative only to the extent the user's history DEVIATES from their own baseline,
                # and only as far as the evidence supports it. Uninformative tokens (e.g. a trait every candidate
                # shares) therefore cannot wash out the decisive ones.
                weight = entry["confidence"] * abs(entry["preference"] - baseline)
                num += weight * entry["preference"]
                den += weight
                supporting.append((weight, feature, value, entry["preference"]))
        if used == 0 or n_tokens == 0:
            return {**base, "status": "no_applicable_evidence", "confidence": 0.0}
        score = 100.0 * (num / den if den > 0 else baseline)   # no discriminating evidence => the user's own baseline
        coverage = used / n_tokens
        confidence = self.summary["behavior_confidence"] * coverage
        supporting.sort(key=lambda t: (-t[0], t[1], t[2]))
        return {"score": round(score, 4), "confidence": round(confidence, 4), "status": status,
                "evidence_count": self.summary["evidence_count"],
                "supporting_features": [{"feature": f, "value": v, "preference": p} for _, f, v, p in supporting[:3]]}

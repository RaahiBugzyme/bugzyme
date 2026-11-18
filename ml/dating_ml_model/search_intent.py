"""Recency-weighted evidence of a user's current search intent.

Search intent is separate from explicit preferences, compatibility, and eligibility.
When sufficient evidence exists, it can contribute a confidence-scaled signal to
personalized recommendation ranking; it is not a permanent preference.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .behavior import format_timestamp, parse_timestamp, recency_weight, usable_events
from . import feature_engineering as fe
from .location import GeoResolver, calculate_distance_km, describe_location

SEARCH_FIELDS = (
    "age",
    "profession",
    "profession_group",
    "education",
    "religion",
    "drinks",
    "drugs",
    "smokes",
    "diet",
    "city",
    "region",
    "country",
    "preferred_distance_km",
    "relationship_intention",
)
RANGE_FIELDS = {"age", "preferred_distance_km"}
FIELD_ALIASES = {"state": "region", "max_distance_km": "preferred_distance_km"}


def _number(value: Any) -> Optional[float]:
    return fe.to_float(value)


def _text(value: Any) -> Optional[str]:
    return fe.norm_text(value)


def _normalize_criteria(criteria: Any) -> Dict[str, Any]:
    if not isinstance(criteria, dict):
        return {}
    out: Dict[str, Any] = {}
    for raw_name, raw_value in criteria.items():
        name = FIELD_ALIASES.get(str(raw_name).strip().lower(), str(raw_name).strip().lower())
        if name not in SEARCH_FIELDS or raw_value is None:
            continue
        if name == "age":
            spec = raw_value if isinstance(raw_value, dict) else {"min": raw_value}
            lo, hi = _number(spec.get("min", spec.get("minimum"))), _number(spec.get("max", spec.get("maximum")))
            if lo is not None or hi is not None:
                out[name] = {"min": lo, "max": hi}
        elif name == "preferred_distance_km":
            value = _number(raw_value)
            if value is not None and value > 0:
                out[name] = value
        else:
            values = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
            normalized = sorted({v for v in (_text(v) for v in values) if v is not None})
            if normalized:
                out[name] = normalized if len(normalized) > 1 else normalized[0]
    return out


def _criteria_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    criteria = event.get("search_criteria")
    if criteria is None:
        criteria = event.get("metadata", {}).get("search_criteria") if isinstance(event.get("metadata"), dict) else None
    return _normalize_criteria(criteria)


def _fingerprint(event: Dict[str, Any], criteria: Dict[str, Any]) -> Tuple[str, str, str]:
    ts = parse_timestamp(event.get("timestamp"))
    return (str(event.get("user_id")), format_timestamp(ts) if ts else "", json.dumps(criteria, sort_keys=True))


class SearchIntentModel:
    """Learns weak, current search evidence from genuine SEARCH events."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.user_id: Optional[str] = None
        self.status = "unavailable"
        self.evidence_count = 0
        self.weighted_evidence = 0.0
        self.last_seen: Optional[datetime] = None
        self.confidence = 0.0
        self._fields: Dict[str, Dict[str, Any]] = {}

    def fit(self, user_id: Any, events: Iterable[Dict[str, Any]], now: datetime) -> "SearchIntentModel":
        self.user_id = str(user_id)
        kept, _ = usable_events(events, user_id, now)
        rows: List[Tuple[float, datetime, Dict[str, Any]]] = []
        seen = set()
        for event in kept:
            if event.get("action") != "SEARCH":
                continue
            criteria = _criteria_from_event(event)
            if not criteria:
                continue
            fingerprint = _fingerprint(event, criteria)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            ts = event["_ts"]
            rows.append((recency_weight((now - ts).total_seconds() / 86400.0, self.config), ts, criteria))

        self.evidence_count = len(rows)
        self.weighted_evidence = sum(weight for weight, _, _ in rows)
        k = float(self.config.get("behavior_evidence_k", 10))
        self.confidence = self.weighted_evidence / (self.weighted_evidence + k) if self.weighted_evidence else 0.0
        self.last_seen = max((ts for _, ts, _ in rows), default=None)
        minimum = int(self.config.get("min_search_evidence", 3))
        if not rows:
            self.status = "unavailable"
        elif self.evidence_count < minimum:
            self.status = "insufficient_data"
        else:
            self.status = "available"

        aggregate: Dict[str, List[Tuple[float, datetime, Any]]] = {}
        for weight, ts, criteria in rows:
            for field, value in criteria.items():
                aggregate.setdefault(field, []).append((weight, ts, value))
        self._fields = {field: self._learn_field(field, values) for field, values in sorted(aggregate.items())}
        return self

    def _learn_field(self, field: str, values: List[Tuple[float, datetime, Any]]) -> Dict[str, Any]:
        total = sum(weight for weight, _, _ in values)
        k = float(self.config.get("behavior_evidence_k", 10))
        base_confidence = total / (total + k)
        last = max(ts for _, ts, _ in values)
        if field in RANGE_FIELDS:
            if field == "age":
                lows = [(w, value.get("min")) for w, _, value in values if value.get("min") is not None]
                highs = [(w, value.get("max")) for w, _, value in values if value.get("max") is not None]
                learned: Dict[str, Any] = {}
                for key, entries in (("min", lows), ("max", highs)):
                    denominator = sum(w for w, _ in entries)
                    if denominator:
                        learned[key] = round(sum(w * v for w, v in entries) / denominator, 4)
                spread = self._range_spread(values, learned)
            else:
                denominator = total
                learned = {"value": round(sum(w * float(v) for w, _, v in values) / denominator, 4)}
                spread = self._numeric_spread(values, learned["value"])
            confidence = base_confidence / (1.0 + spread)
            return self._result(learned, len(values), total, confidence, last)

        weights: Dict[str, float] = {}
        for weight, _, value in values:
            for item in (value if isinstance(value, list) else [value]):
                weights[str(item)] = weights.get(str(item), 0.0) + weight
        ordered = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
        learned = ordered[0][0] if ordered else None
        dominance = (ordered[0][1] / total) if ordered and total else 0.0
        return self._result(learned, len(values), total, base_confidence * dominance, last,
                            alternatives=[{"value": value, "weighted_evidence": round(weight, 4)} for value, weight in ordered])

    @staticmethod
    def _numeric_spread(values: List[Tuple[float, datetime, Any]], mean: float) -> float:
        return sum(weight * abs(float(value) - mean) for weight, _, value in values) / max(sum(w for w, _, _ in values), 1e-12) / max(abs(mean), 1.0)

    def _range_spread(self, values: List[Tuple[float, datetime, Any]], learned: Dict[str, Any]) -> float:
        deviations = []
        for weight, _, value in values:
            for key in ("min", "max"):
                if value.get(key) is not None and learned.get(key) is not None:
                    deviations.append((weight, abs(float(value[key]) - learned[key])))
        return sum(w * d for w, d in deviations) / max(sum(w for w, _ in deviations), 1e-12) / 10.0

    @staticmethod
    def _result(learned: Any, count: int, weighted: float, confidence: float, last: datetime,
                alternatives: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        result = {"value": learned, "evidence_count": count, "weighted_evidence": round(weighted, 4),
                  "confidence": round(min(max(confidence, 0.0), 1.0), 4),
                  "last_seen": format_timestamp(last)}
        if alternatives:
            result["alternatives"] = alternatives
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {"user_id": self.user_id, "status": self.status, "evidence_count": self.evidence_count,
                "weighted_evidence": round(self.weighted_evidence, 4),
                "confidence": round(self.confidence, 4),
                "last_seen": format_timestamp(self.last_seen) if self.last_seen else None,
                "fields": {field: dict(value) for field, value in self._fields.items()},
                "explicit_preferences_unchanged": True}


def _candidate_value(field: str, user: Dict[str, Any], candidate: Dict[str, Any],
                    config: Dict[str, Any], resolver: Optional[GeoResolver]) -> Any:
    attrs = fe.profile_attributes(candidate, int(config["reference_year"]))
    if field in attrs:
        return attrs[field]
    if field == "education":
        return fe.norm_text(candidate.get("education"))
    if field in ("city", "region", "country"):
        location = describe_location(candidate, resolver)
        return {"city": location["city"], "region": location["region"], "country": location["country"]}[field]
    if field == "preferred_distance_km":
        return calculate_distance_km(user, candidate, resolver)
    return None


def _criterion_score(field: str, learned: Dict[str, Any], user: Dict[str, Any],
                     candidate: Dict[str, Any], config: Dict[str, Any],
                     resolver: Optional[GeoResolver]) -> Optional[float]:
    actual = _candidate_value(field, user, candidate, config, resolver)
    if actual is None:
        return None
    target = learned.get("value")
    if field == "age":
        if not isinstance(target, dict) or actual is None:
            return None
        lo, hi = target.get("min"), target.get("max")
        if lo is not None and actual < lo:
            return max(0.0, 1.0 - (lo - actual) / float(config["preferences"]["soft_range_tolerance"]["age"]))
        if hi is not None and actual > hi:
            return max(0.0, 1.0 - (actual - hi) / float(config["preferences"]["soft_range_tolerance"]["age"]))
        return 1.0
    if field == "preferred_distance_km":
        desired = float(target.get("value") if isinstance(target, dict) else target)
        return 1.0 if actual <= desired else max(0.0, 1.0 - (actual - desired) / max(desired, 1.0))
    if str(actual) == str(target):
        return 1.0
    alternatives = [item for item in learned.get("alternatives", [])
                    if isinstance(item, dict) and str(item.get("value")) == str(actual)]
    total = float(learned.get("weighted_evidence", 0.0))
    if alternatives and total > 0:
        return min(1.0, float(alternatives[0].get("weighted_evidence", 0.0)) / total)
    return 0.0


def score_search_intent(user: Dict[str, Any], candidate: Dict[str, Any],
                        intent: Dict[str, Any], config: Dict[str, Any],
                        resolver: Optional[GeoResolver] = None) -> Dict[str, Any]:
    """Score candidate alignment to learned searches without changing eligibility."""
    status = intent.get("status", "unavailable")
    base = {"score": None, "confidence": 0.0, "status": status,
            "evidence_count": intent.get("evidence_count", 0),
            "supporting_attributes": []}
    if status != "available":
        return base
    weighted_scores: List[Tuple[float, float, str]] = []
    for field, learned in sorted((intent.get("fields") or {}).items()):
        score = _criterion_score(field, learned, user, candidate, config, resolver)
        if score is not None:
            weight = float(learned.get("confidence", 0.0))
            weighted_scores.append((score, weight, field))
    if not weighted_scores or sum(weight for _, weight, _ in weighted_scores) <= 0:
        return {**base, "status": "no_applicable_evidence"}
    denominator = sum(weight for _, weight, _ in weighted_scores)
    score = 100.0 * sum(value * weight for value, weight, _ in weighted_scores) / denominator
    confidence = float(intent.get("confidence", 0.0)) * (denominator / len(weighted_scores))
    return {**base, "score": round(score, 4), "confidence": round(confidence, 4),
            "supporting_attributes": [field for _, _, field in weighted_scores]}


def learn_search_intent(user_id: Any, events: Iterable[Dict[str, Any]], config: Dict[str, Any],
                        now: datetime) -> Dict[str, Any]:
    return SearchIntentModel(config).fit(user_id, events, now).to_dict()

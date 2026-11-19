"""Explicit user preferences: HARD (can exclude) vs SOFT (re-rank only).

* Missing preference  => no preference.
* Unknown candidate attribute => unknown (never a mismatch; hard filters KEEP such candidates
  unless config `hard_filter_unknown_policy` is "exclude").
* This layer never touches the core compatibility score.

Preference format (all keys optional):
{
  "preferred_distance_km": 25, "max_distance_km": 50,            # distance is handled by location.py
  "criteria": {
     "age":    {"min": 25, "max": 32, "hard": false},
     "height": {"min": 63, "max": 75},
     "education": {"min_rank": 3},                                # rank scale from feature_engineering.education_rank
     "profession" / "profession_group" / "religion" / "ethnicity" / "drinks" / "drugs" /
     "smokes" / "diet" / "children" / "pets" / "body_type" / "body_type_group" /
     "relationship_intention": {"values": [...], "hard": false}
  }
}
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from . import feature_engineering as fe

RANGE_CRITERIA = ("age", "height")
SET_CRITERIA = ("profession", "profession_group", "religion", "ethnicity", "drinks", "drugs", "smokes", "diet",
                "children", "pets", "body_type", "body_type_group", "relationship_intention")
ALL_CRITERIA = RANGE_CRITERIA + ("education",) + SET_CRITERIA + ("region",)
EXCLUSION_FIELDS = ("region", "religion", "profession")


def _norm_values(criterion: str, values) -> set:
    out = set()
    for v in values if isinstance(values, (list, tuple, set)) else [values]:
        text = fe.norm_text(v)
        if text is None:
            continue
        if criterion == "relationship_intention":
            text = fe.relationship_intention(text)
        elif criterion in ("religion",):
            text = fe.religion_base(text)
        elif criterion == "diet":
            text = fe.diet_base(text)
        elif criterion in ("profession",):
            text = fe.clean_profession(text)
        elif criterion in ("profession_group", "body_type_group", "children"):
            text = text.replace(" ", "_") if criterion != "children" else text
        if text:
            out.add(text)
    return out


def normalize_preferences(prefs: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Validate/normalize; invalid entries are dropped with a warning (never guessed)."""
    prefs = prefs or {}
    warnings: List[str] = []
    out: Dict[str, Any] = {"preferred_distance_km": None, "max_distance_km": None, "criteria": {}, "hard_exclusions": {}}
    for key in ("preferred_distance_km", "max_distance_km"):
        value = fe.to_float(prefs.get(key))
        if prefs.get(key) is not None and (value is None or value <= 0):
            warnings.append(f"{key} ignored (must be a positive number)")
        elif value is not None:
            out[key] = value
    for name, spec in (prefs.get("criteria") or {}).items():
        if name not in ALL_CRITERIA or not isinstance(spec, dict):
            warnings.append(f"criterion '{name}' ignored (unsupported)")
            continue
        hard = bool(spec.get("hard", False))
        if name in RANGE_CRITERIA:
            lo, hi = fe.to_float(spec.get("min")), fe.to_float(spec.get("max"))
            if lo is None and hi is None:
                warnings.append(f"criterion '{name}' ignored (no min/max)")
            elif lo is not None and hi is not None and lo > hi:
                warnings.append(f"criterion '{name}' ignored (min > max)")
            else:
                out["criteria"][name] = {"min": lo, "max": hi, "hard": hard}
        elif name == "education":
            rank = fe.to_float(spec.get("min_rank"))
            if rank is None:
                warnings.append("criterion 'education' ignored (no min_rank)")
            else:
                out["criteria"][name] = {"min_rank": rank, "hard": hard}
        else:
            values = _norm_values(name, spec.get("values", []))
            if not values:
                warnings.append(f"criterion '{name}' ignored (no valid values)")
            else:
                out["criteria"][name] = {"values": sorted(values), "hard": hard}
    for name, spec in (prefs.get("hard_exclusions") or {}).items():
        if name not in EXCLUSION_FIELDS or not isinstance(spec, dict):
            warnings.append(f"hard exclusion '{name}' ignored (unsupported)")
            continue
        values = _norm_values(name, spec.get("values", []))
        if not values:
            warnings.append(f"hard exclusion '{name}' ignored (no valid values)")
            continue
        out["hard_exclusions"][name] = {"values": sorted(values)}
    return out, warnings


def _match(name: str, spec: Dict[str, Any], attrs: Dict[str, Any], tolerance: Dict[str, float]) -> Optional[float]:
    """Match in [0,1] or None when the candidate attribute is unknown."""
    if name in RANGE_CRITERIA:
        value = attrs.get(name)
        if value is None:
            return None
        lo, hi = spec["min"], spec["max"]
        outside = max((lo - value) if lo is not None else 0.0, (value - hi) if hi is not None else 0.0, 0.0)
        return 1.0 - min(outside / float(tolerance.get(name, 10)), 1.0)
    if name == "education":
        rank = attrs.get("education_rank")
        return None if rank is None else (1.0 if rank >= spec["min_rank"] else 0.0)
    value = attrs.get(name)
    if value is None:
        return None
    values = set(spec["values"])
    if isinstance(value, set):
        return 1.0 if value & values else 0.0
    return 1.0 if value in values else 0.0


def _exclusion_failures(preferences: Optional[Dict[str, Any]], attrs: Dict[str, Any], unknown_policy: str = "keep") -> List[str]:
    normalized, _ = normalize_preferences(preferences)
    failures = []
    for name, spec in normalized["hard_exclusions"].items():
        value = attrs.get(name)
        if value is None:
            if unknown_policy == "exclude":
                failures.append(f"{name} unknown (hard exclusion requires it)")
        elif value in set(spec["values"]):
            failures.append(f"{name} is explicitly excluded")
    return failures


def evaluate_preferences(preferences: Optional[Dict[str, Any]], candidate: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Soft score/confidence and hard-filter failures for one candidate."""
    prefs, warnings = normalize_preferences(preferences)
    attrs = fe.profile_attributes(candidate, int(config["reference_year"]))
    pcfg = config["preferences"]
    weights, tolerance = pcfg.get("criterion_weights", {}), pcfg.get("soft_range_tolerance", {})
    unknown_policy = pcfg.get("hard_filter_unknown_policy", "keep")

    hard_failures: List[str] = []
    hard_failures.extend(_exclusion_failures(preferences, attrs, unknown_policy))
    for name in (prefs.get("hard_exclusions") or {}):
        if attrs.get(name) is None and unknown_policy == "keep":
            warnings.append(f"{name} is unknown under hard exclusion (unverified; kept without confirmed match)")
    soft_matches: Dict[str, Optional[float]] = {}
    for name, spec in prefs["criteria"].items():
        m = _match(name, spec, attrs, tolerance)
        if spec["hard"]:
            if m is None:
                if unknown_policy == "exclude":
                    hard_failures.append(f"{name} unknown (hard preference requires it)")
                else:
                    warnings.append(f"{name} is unknown under hard preference (unverified; kept without confirmed match)")
            elif m < 1.0:
                hard_failures.append(f"{name} outside the hard preference")
        else:
            soft_matches[name] = m

    total_w = sum(float(weights.get(n, 1.0)) for n in soft_matches)
    known_w = sum(float(weights.get(n, 1.0)) for n, m in soft_matches.items() if m is not None)
    if not soft_matches:
        status, score, confidence = "no_preferences", None, 0.0
    elif known_w == 0:
        status, score, confidence = "unknown", None, 0.0
    else:
        score = 100.0 * sum(m * float(weights.get(n, 1.0)) for n, m in soft_matches.items() if m is not None) / known_w
        confidence = 100.0 * known_w / total_w
        status = "known"
    return {
        "score": None if score is None else round(score, 4),
        "confidence": round(confidence, 4), "status": status,
        "criteria": {n: (None if m is None else round(m, 4)) for n, m in soft_matches.items()},
        "hard_failures": hard_failures, "warnings": warnings,
    }


def check_hard_preferences(preferences: Optional[Dict[str, Any]], candidate: Dict[str, Any], config: Dict[str, Any], who: str) -> List[str]:
    return [f"{who}: {r}" for r in evaluate_preferences(preferences, candidate, config)["hard_failures"]]


def intention_compatibility(a: Any, b: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Alignment of STATED intentions only (not a success predictor)."""
    ia, ib = fe.relationship_intention(a), fe.relationship_intention(b)
    if ia is None or ib is None:
        return {"score": None, "status": "unknown", "user": ia, "candidate": ib}
    t = config["preferences"]["relationship_intention_similarity"]
    group = set(t["commitment_group"])
    if ia == ib:
        s = t["same"]
    elif "unsure" in (ia, ib):
        s = t["unsure_with_any"]
    elif ia in group and ib in group:
        s = t["within_commitment_group"]
    elif "friendship" in (ia, ib):
        s = t["friendship_with_casual"] if "casual" in (ia, ib) else t["friendship_with_commitment"]
    else:
        s = t["casual_with_commitment"]
    return {"score": round(100.0 * s, 4), "status": "known", "user": ia, "candidate": ib}


def evaluate_bilateral_preferences(
    prefs_a: Optional[Dict[str, Any]],
    profile_a: Dict[str, Any],
    prefs_b: Optional[Dict[str, Any]],
    profile_b: Dict[str, Any],
    config: Dict[str, Any],
    aggregation: Optional[str] = None,
    viewer_weight: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluates stated preferences bilaterally (A -> B and B -> A).

    - Evaluates how well candidate B satisfies user A's stated criteria.
    - Evaluates how well user A satisfies candidate B's stated criteria.
    - If both parties have stated preferences, combines directional scores using
      bilateral geometric aggregation (or configured viewer-weighted / harmonic).
    - If candidate B has no preferences, falls back to user A's evaluation without penalty.
    - If user A has no preferences, candidate B's preferences evaluate user A.
    - If neither party has stated preferences, returns status 'no_preferences' with None score.
    - Missing or unknown values reduce confidence without being treated as a mismatch or match.
    - Confirmed hard exclusions are gathered into hard_failures.
    """
    eval_a_to_b = evaluate_preferences(prefs_a, profile_b, config)
    eval_b_to_a = evaluate_preferences(prefs_b, profile_a, config)

    pcfg = config.get("preferences", {})
    agg_mode = aggregation or pcfg.get("bilateral_aggregation", "geometric")
    vw = viewer_weight if viewer_weight is not None else float(pcfg.get("viewer_weight", 0.7))

    status_a = eval_a_to_b["status"]
    status_b = eval_b_to_a["status"]
    score_a = eval_a_to_b["score"]
    score_b = eval_b_to_a["score"]
    conf_a = eval_a_to_b["confidence"]
    conf_b = eval_b_to_a["confidence"]

    # 1. Status, score, and confidence combination
    if status_a == "no_preferences" and status_b == "no_preferences":
        status = "no_preferences"
        score = None
        confidence = 0.0
    elif status_b == "no_preferences":
        # Candidate B has no stated preferences: fall back to A's preferences
        status = "partial_known" if status_a == "known" else status_a
        score = score_a
        confidence = conf_a
    elif status_a == "no_preferences":
        # User A has no stated preferences: candidate B evaluates user A
        status = "partial_known" if status_b == "known" else status_b
        score = score_b
        confidence = conf_b
    else:
        # Both parties have stated preferences
        if score_a is not None and score_b is not None:
            status = "known"
            if agg_mode == "viewer_weighted":
                score = vw * score_a + (1.0 - vw) * score_b
                confidence = vw * conf_a + (1.0 - vw) * conf_b
            elif agg_mode == "harmonic":
                score = (2.0 * score_a * score_b / (score_a + score_b)) if (score_a + score_b) > 0 else 0.0
                confidence = (2.0 * conf_a * conf_b / (conf_a + conf_b)) if (conf_a + conf_b) > 0 else 0.0
            else:  # default: "geometric"
                score = math.sqrt(score_a * score_b)
                confidence = math.sqrt(conf_a * conf_b)
        elif score_a is not None and score_b is None:
            status = "partial_known"
            score = score_a
            confidence = round(conf_a * 0.5, 4)
        elif score_a is None and score_b is not None:
            status = "partial_known"
            score = score_b
            confidence = round(conf_b * 0.5, 4)
        else:
            # Both sides specified preferences, but all criteria attributes were missing/unknown
            status = "unknown"
            score = None
            confidence = 0.0

    # 2. Hard failures & warnings
    hard_failures = list(eval_a_to_b.get("hard_failures", []))
    if pcfg.get("hard_preferences_mutual", True):
        hard_failures.extend(eval_b_to_a.get("hard_failures", []))
    warnings = list(eval_a_to_b.get("warnings", [])) + list(eval_b_to_a.get("warnings", []))

    # Criteria view: preserve directional criteria
    criteria: Dict[str, Optional[float]] = dict(eval_a_to_b.get("criteria", {}))

    return {
        "score": None if score is None else round(score, 4),
        "confidence": round(confidence, 4),
        "status": status,
        "criteria": criteria,
        "user_to_candidate": eval_a_to_b,
        "candidate_to_user": eval_b_to_a,
        "a_to_b": eval_a_to_b,
        "b_to_a": eval_b_to_a,
        "hard_failures": hard_failures,
        "warnings": warnings,
    }


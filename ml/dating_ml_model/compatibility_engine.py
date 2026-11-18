"""Deterministic profile-compatibility engine (Dating ML V2.1).

Measures how ALIGNED two profiles are on the attributes both people filled in.
It does NOT predict relationship success: the OkCupid data has no outcome labels.

Pipeline: eligibility gate -> 14 component similarities -> 6 macro-categories
-> weighted compatibility -> confidence (evidence coverage) -> shrinkage to 50.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import feature_engineering as fe
from .eligibility import check_eligibility as _check_eligibility

CATEGORIES = ("demographics", "career_education", "values_culture", "lifestyle", "family", "attraction")

# (positive text, negative text) per component
EXPLANATIONS: Dict[str, Tuple[str, str]] = {
    "age": ("Similar age", "Large age gap"),
    "generation": ("Same generation", "Different generations"),
    "education": ("Similar education level", "Different education levels"),
    "profession": ("Same profession", "Different professions"),
    "religion": ("Same religion or belief system", "Different religions or belief systems"),
    "ethnicity": ("Shared ethnic background", "Different ethnic backgrounds"),
    "drinks": ("Similar drinking habits", "Different drinking habits"),
    "drugs": ("Similar attitude toward drugs", "Different attitude toward drugs"),
    "smokes": ("Similar smoking habits", "Different smoking habits"),
    "diet": ("Compatible diets", "Different dietary preferences"),
    "offspring": ("Aligned views on having children", "Different views on having children"),
    "pets": ("Compatible attitudes toward pets", "Different attitudes toward pets"),
    "height": ("Similar height", "Notable height difference"),
    "body_type": ("Similar body type", "Different body types"),
}


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    path = Path(path) if path else Path(__file__).with_name("config.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _weighted_mean(pairs: List[Tuple[Optional[float], float]]) -> Optional[float]:
    """Unknown-aware mean: unknown (None) components are skipped, never zeroed."""
    total = sum(w for v, w in pairs if v is not None)
    if total <= 0:
        return None
    return sum(v * w for v, w in pairs if v is not None) / total


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 4)


class CompatibilityEngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config if config is not None else load_config()
        cfg = self.config
        self.neutral = float(cfg["neutral_baseline"])
        self.reference_year = int(cfg["reference_year"])
        self.min_age = int(cfg["min_age"])
        disabled = set(cfg.get("disabled_components", []))

        for cat, comps in cfg["component_weights"].items():
            if abs(sum(comps.values()) - 1.0) > 1e-6:
                raise ValueError(f"component weights for '{cat}' must sum to 1")
        profile = cfg["category_weights"][cfg["weight_profile"]]
        if abs(sum(profile.values()) - 1.0) > 1e-6:
            raise ValueError("category weights must sum to 1")

        self.components: Dict[str, List[Tuple[str, float]]] = {}
        for cat in CATEGORIES:
            items = [(n, w) for n, w in cfg["component_weights"][cat].items() if n not in disabled and w > 0]
            total = sum(w for _, w in items)
            self.components[cat] = [(n, w / total) for n, w in items] if total > 0 else []
        active = {c: profile[c] for c in CATEGORIES if self.components[c] and profile[c] > 0}
        total = sum(active.values())
        if total <= 0:
            raise ValueError("no active categories")
        self.category_weights = {c: w / total for c, w in active.items()}

    # ---------------------------------------------------------------- gate
    def check_eligibility(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        return _check_eligibility(a, b, self.min_age)

    # ---------------------------------------------------------- components
    def _component(self, name: str, a: Dict[str, Any], b: Dict[str, Any], gens) -> Optional[float]:
        cfg = self.config
        if name == "age":
            return fe.age_similarity(a.get("age"), b.get("age"), cfg["age_max_gap_years"])
        if name == "generation":
            return fe.generation_similarity(*gens)
        if name == "education":
            return fe.education_similarity(a.get("education"), b.get("education"), cfg["education_max_gap_levels"])
        if name == "profession":
            return fe.profession_similarity(a.get("job"), b.get("job"))
        if name == "religion":
            return fe.religion_similarity(a.get("religion"), b.get("religion"), cfg["secular_partial_credit"])
        if name == "ethnicity":
            return fe.ethnicity_similarity(a.get("ethnicity"), b.get("ethnicity"))
        if name in fe.ORDINAL_SCALES:
            return fe.ordinal_similarity(name, a.get(name), b.get(name))
        if name == "diet":
            return fe.diet_similarity(a.get("diet"), b.get("diet"))
        if name == "offspring":
            return fe.offspring_similarity(a.get("offspring"), b.get("offspring"))
        if name == "pets":
            return fe.pets_similarity(a.get("pets"), b.get("pets"))
        if name == "height":
            return fe.height_similarity(
                a.get("height"), b.get("height"), cfg["height_max_gap_inches"], tuple(cfg["height_valid_range_inches"])
            )
        if name == "body_type":
            return fe.body_type_similarity(a.get("body_type"), b.get("body_type"))
        raise KeyError(name)

    # -------------------------------------------------------------- scoring
    def score_pair(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        """Score two profiles WITHOUT the eligibility gate (internal/analysis use)."""
        gens = (fe.derive_generation(a, self.reference_year), fe.derive_generation(b, self.reference_year))

        components: Dict[str, Dict[str, Optional[float]]] = {}
        category_scores: Dict[str, Optional[float]] = {}
        evidence = 0.0  # share of total weight that had data on both profiles
        for cat in CATEGORIES:
            values = [(self._component(n, a, b, gens), w) for n, w in self.components[cat]]
            components[cat] = {n: v for (n, _), (v, _w) in zip(self.components[cat], values)}
            category_scores[cat] = _weighted_mean(values)
            if cat in self.category_weights:
                known_share = sum(w for v, w in values if v is not None)  # sub-weights sum to 1
                evidence += self.category_weights[cat] * known_share

        raw = _weighted_mean([(category_scores[c], w) for c, w in self.category_weights.items()])
        compatibility = self.neutral if raw is None else raw * 100.0
        confidence_ratio = min(max(evidence, 0.0), 1.0)
        adjusted = confidence_ratio * compatibility + (1.0 - confidence_ratio) * self.neutral

        return {
            "compatibility_score": _round(compatibility),
            "confidence_score": _round(confidence_ratio * 100.0),
            "adjusted_score": _round(adjusted),
            "categories": {c: _round(None if category_scores[c] is None else category_scores[c] * 100.0) for c in CATEGORIES},
            "components": {c: {n: _round(v) for n, v in components[c].items()} for c in CATEGORIES},
            "explanation": self._explain(components, raw is None, confidence_ratio * 100.0),
        }

    # ---------------------------------------------------------- explanations
    def _explain(self, components, no_evidence: bool, confidence_pct: float) -> List[str]:
        th = self.config["explanation_thresholds"]
        lines: List[str] = []
        for cat in CATEGORIES:
            for name, value in components[cat].items():
                if value is None:
                    continue
                positive, negative = EXPLANATIONS[name]
                if name == "profession" and value == 0.5:
                    lines.append("Same broad profession group")
                elif name == "offspring" and value == 0.5:
                    lines.append("Partly aligned views on having children")
                elif value >= th["high"]:
                    lines.append(positive)
                elif value <= th["low"]:
                    lines.append(negative)
        if no_evidence:
            lines.append("No comparable profile information; score defaults to the neutral baseline")
        elif confidence_pct < th["low_confidence_pct"]:
            lines.append(f"Limited evidence: only {confidence_pct:.0f}% of the scoring weight had data on both profiles")
        return lines

    # ------------------------------------------------------------ public API
    def predict_pair(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        gate = self.check_eligibility(a, b)
        result: Dict[str, Any] = {
            "user_a": a.get("id", a.get("user_id")),
            "user_b": b.get("id", b.get("user_id")),
            "eligible": gate["eligible"],
            "eligibility_reason": gate["reason"],
        }
        if not gate["eligible"]:
            result.update(
                compatibility_score=None, confidence_score=None, adjusted_score=None,
                categories={c: None for c in CATEGORIES}, components=None, explanation=[gate["reason"]],
            )
        else:
            result.update(self.score_pair(a, b))
        result["model_version"] = self.config["model_version"]
        return result

    def predict_matches(self, user: Dict[str, Any], candidates, top_k: int = 10) -> List[Dict[str, Any]]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        eligible = []
        for candidate in candidates:
            result = self.predict_pair(user, candidate)
            if result["eligible"]:  # ineligible candidates are never recommended
                eligible.append(result)
        eligible.sort(key=lambda r: (-r["adjusted_score"], -r["confidence_score"], str(r["user_b"])))
        return eligible[:top_k]

"""Final ranking: combines SEPARATE signals with configurable weights.

Weights are placeholders (see config.final_ranking.weights_note). Unknown signals get zero weight
(no penalty); preference / behavior / mutual-interest / search-intent weights are scaled by their
confidence, so personalization fades in gradually instead of switching on abruptly. Search intent
remains separate from compatibility and eligibility and contributes only when sufficient evidence
exists.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SIGNALS = ("compatibility", "location", "preferences", "relationship_intention", "behavior", "mutual_interest", "search_intent", "personality", "interests")
CONFIDENCE_SCALED = ("location", "preferences", "behavior", "mutual_interest", "search_intent", "personality", "interests")


def combine_signals(signals: Dict[str, Dict[str, Optional[float]]], config: Dict[str, Any]) -> Dict[str, Any]:
    """signals[name] = {"score": 0..100 | None, "confidence": 0..1 | None}"""
    weights = config["final_ranking"]["weights"]
    rows: List[Dict[str, Any]] = []
    num = den = 0.0
    for name in SIGNALS:
        if name not in signals:
            continue
        sig = signals.get(name) or {}
        score, conf = sig.get("score"), sig.get("confidence")
        base_w = float(weights.get(name, 0.0))
        eff = 0.0
        if score is not None and base_w > 0:
            eff = base_w * (float(conf) if name in CONFIDENCE_SCALED and conf is not None else 1.0)
        rows.append({"signal": name, "score": None if score is None else round(float(score), 4),
                     "base_weight": base_w, "effective_weight": round(eff, 6), "used": eff > 0})
        if eff > 0:
            num += eff * float(score)
            den += eff
    return {"final_score": None if den == 0 else round(num / den, 4),
            "components": rows,
            "weights_are_validated": False,
            "weights_note": config["final_ranking"]["weights_note"]}

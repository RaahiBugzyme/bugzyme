"""Learned User Interest Profile (Phase 6).

Builds a dynamic, recency-weighted profile of user interests from:
- Explicitly stated interests (from profile or preferences).
- Search categories and keywords (from SEARCH events).
- Engaged candidate profile attributes (from LIKE, SUPER_LIKE, SAVE, CONVERSATION_STARTED, RECIPROCAL_CONVERSATION).
- Negative feedback (PASS events decrease attribute affinity).
- Time decay (older interactions decay so preferences evolve).

Critical constraint: A profile view alone is strictly a WEAK signal (weight <= 0.1),
never treated as proof of attraction or preference.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from . import feature_engineering as fe
from .behavior import (
    ACTION_SIGNAL_WEIGHTS,
    format_timestamp,
    parse_timestamp,
    recency_weight,
    usable_events,
    utcnow,
)


def _extract_profile_interest_tokens(profile: Dict[str, Any], reference_year: int) -> Set[Tuple[str, str]]:
    """Extracts informative categorical (dimension, value) tokens from a profile."""
    tokens: Set[Tuple[str, str]] = set()
    attrs = fe.profile_attributes(profile, reference_year)

    for field in ("profession_group", "religion", "ethnicity", "drinks", "smokes", "diet", "body_type_group", "generation", "relationship_intention"):
        val = attrs.get(field)
        if val is not None:
            tokens.add((field, str(val)))

    # Pets
    pets = attrs.get("pets")
    if pets and isinstance(pets, set):
        for p in pets:
            tokens.add(("pets", p))

    # Explicit interests / tags / hobbies if present on profile
    raw_interests = profile.get("interests") or profile.get("hobbies") or []
    if isinstance(raw_interests, (list, tuple, set)):
        for item in raw_interests:
            t = fe.norm_text(item)
            if t:
                tokens.add(("interest_tag", t.replace(" ", "_")))

    return tokens


class UserInterestProfile:
    """Dynamic profile of learned user interests distinct from explicit dealbreakers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.user_id: Optional[str] = None
        self.status = "cold_start"
        self.evidence_count = 0
        self.weighted_evidence = 0.0
        self.confidence = 0.0
        self.last_updated: Optional[datetime] = None

        # Learned affinity scores per (dimension, token)
        self.inferred_interests: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Explicitly stated interests
        self.explicit_interests: List[str] = []
        # External interests and provenance (Phase 1 external interest personalization)
        self.external_interests: List[Dict[str, Any]] = []
        self.provenance_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    def fit(
        self,
        user: Dict[str, Any],
        events: List[Dict[str, Any]],
        profile_lookup: Callable[[str], Optional[Dict[str, Any]]],
        now: Optional[datetime] = None,
        external_interests: Optional[List[Dict[str, Any]]] = None,
    ) -> "UserInterestProfile":
        now = now or utcnow()
        uid = str(user.get("id", user.get("user_id")))
        self.user_id = uid
        self.external_interests = [dict(i) for i in (external_interests or [])]
        self.provenance_map = {}

        # 1. Stated interests from profile
        raw_exp = user.get("interests") or user.get("hobbies") or []
        self.explicit_interests = sorted({fe.norm_text(i) for i in raw_exp if fe.norm_text(i)})

        # 2. Process usable events
        kept, _ = usable_events(events, uid, now)
        if not kept and not self.external_interests:
            self.status = "cold_start"
            self.evidence_count = 0
            self.weighted_evidence = 0.0
            self.confidence = 0.0
            self.inferred_interests = {}
            return self

        ref_year = int(self.config.get("reference_year", 2026))

        # Accumulate token scores
        # cell: {"pos_weight": float, "neg_weight": float, "count": int, "last_ts": datetime}
        token_stats: Dict[Tuple[str, str], Dict[str, Any]] = {}
        total_effective_events = 0
        total_weighted_ev = 0.0

        for ev in kept:
            act = ev["action"]
            base_w = ACTION_SIGNAL_WEIGHTS.get(act, 0.0)
            if base_w == 0.0:
                continue

            ts = ev["_ts"]
            age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
            decay_w = recency_weight(age_days, self.config)
            eff_weight = abs(base_w) * decay_w
            is_positive = base_w > 0.0

            cand_id = ev.get("candidate_id")

            # A. Profile-based tokens
            if cand_id is not None:
                cand_profile = profile_lookup(str(cand_id))
                if cand_profile:
                    tokens = _extract_profile_interest_tokens(cand_profile, ref_year)
                    for dim, val in tokens:
                        cell = token_stats.setdefault((dim, val), {"pos_weight": 0.0, "neg_weight": 0.0, "count": 0, "last_ts": ts})
                        if is_positive:
                            cell["pos_weight"] += eff_weight
                        else:
                            cell["neg_weight"] += eff_weight
                        cell["count"] += 1
                        cell["last_ts"] = max(cell["last_ts"], ts)

            # B. Search-based criteria
            if act == "SEARCH":
                sc = ev.get("search_criteria") or {}
                if isinstance(sc, dict):
                    for field, val in sc.items():
                        if val is not None and field in ("profession_group", "religion", "diet", "smokes", "drinks"):
                            v_list = val if isinstance(val, (list, tuple)) else [val]
                            for item in v_list:
                                norm_v = fe.norm_text(item)
                                if norm_v:
                                    cell = token_stats.setdefault((field, norm_v), {"pos_weight": 0.0, "neg_weight": 0.0, "count": 0, "last_ts": ts})
                                    cell["pos_weight"] += eff_weight
                                    cell["count"] += 1
                                    cell["last_ts"] = max(cell["last_ts"], ts)

            total_effective_events += 1
            total_weighted_ev += eff_weight

        # 3. Process external interests (prior positive evidence with provenance)
        for item in self.external_interests:
            token_str = str(item.get("canonical_token", ""))
            if ":" in token_str:
                dim, val = token_str.split(":", 1)
            else:
                dim, val = "interest_tag", token_str
            norm_val = fe.norm_text(val)
            if not norm_val:
                continue
            norm_val = norm_val.replace(" ", "_")
            token_key = (dim, norm_val)

            # External confidence and user confirmation weighting
            conf = float(item.get("confidence", 0.75))
            user_confirmed = bool(item.get("user_confirmed", False))
            conf_multiplier = 1.2 if user_confirmed else 0.8
            ext_w = max(0.1, min(2.0, conf * conf_multiplier))

            cell = token_stats.setdefault(token_key, {"pos_weight": 0.0, "neg_weight": 0.0, "count": 0, "last_ts": now})
            cell["pos_weight"] += ext_w
            cell["count"] += 1
            cell["last_ts"] = max(cell["last_ts"], now)

            # Record provenance for explanation
            self.provenance_map.setdefault(token_key, []).append({
                "provider": str(item.get("provider", "external")).lower(),
                "confidence": round(conf, 4),
                "source_detail": str(item.get("source_detail", "imported_account")),
                "user_confirmed": user_confirmed,
                "display_name": item.get("display_name") or val.replace("_", " ").title(),
                "category": item.get("category", "general"),
            })

            total_effective_events += 1
            total_weighted_ev += ext_w

        self.evidence_count = total_effective_events
        self.weighted_evidence = round(total_weighted_ev, 4)
        min_ev = int(self.config.get("min_behavior_events", 10))
        # If external interests are present, lower evidence threshold enables personalization
        effective_min_ev = int(self.config.get("min_external_interest_events", 1)) if self.external_interests else min_ev

        if total_effective_events == 0:
            self.status = "cold_start"
            self.confidence = 0.0
        elif total_effective_events < effective_min_ev:
            self.status = "insufficient_data"
            self.confidence = round(100.0 * total_effective_events / effective_min_ev, 2)
        else:
            self.status = "sufficient_data"
            k = float(self.config.get("behavior_evidence_k", 10))
            self.confidence = round(100.0 * total_weighted_ev / (total_weighted_ev + k), 2)

        # Build inferred interests structure
        self.inferred_interests = {}
        for (dim, val), cell in sorted(token_stats.items()):
            pos_w, neg_w = cell["pos_weight"], cell["neg_weight"]
            tot_w = pos_w + neg_w
            # Affinity ratio from 0 to 1 (0.5 is neutral)
            affinity = (pos_w / tot_w) if tot_w > 0 else 0.5
            dim_dict = self.inferred_interests.setdefault(dim, {})
            dim_dict[val] = {
                "affinity": round(affinity, 4),
                "positive_evidence": round(pos_w, 4),
                "negative_evidence": round(neg_w, 4),
                "evidence_count": cell["count"],
                "last_interacted": format_timestamp(cell["last_ts"]),
            }

        return self

    def score_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Scores candidate against learned interest profile."""
        if self.status in ("cold_start", "insufficient_data") or not self.inferred_interests:
            return {
                "score": None,
                "confidence": self.confidence,
                "status": self.status,
                "aligned_interests": [],
                "divergent_interests": [],
            }

        ref_year = int(self.config.get("reference_year", 2026))
        tokens = _extract_profile_interest_tokens(candidate, ref_year)

        num = den = 0.0
        aligned = []
        aligned_details = []
        divergent = []

        for dim, val in tokens:
            entry = self.inferred_interests.get(dim, {}).get(val)
            if entry is not None:
                tot_ev = entry["positive_evidence"] + entry["negative_evidence"]
                affinity = entry["affinity"]
                # Deviation from neutral (0.5)
                dev = abs(affinity - 0.5)
                w = tot_ev * dev
                num += w * affinity
                den += w
                if affinity >= 0.7:
                    token_str = f"{dim}: {val}"
                    aligned.append(token_str)
                    prov = self.provenance_map.get((dim, val))
                    if prov:
                        aligned_details.append({
                            "token": token_str,
                            "display_name": prov[0].get("display_name", val.replace("_", " ").title()),
                            "category": prov[0].get("category", "general"),
                            "provenance": prov,
                        })
                elif affinity <= 0.3:
                    divergent.append(f"{dim}: {val}")

        if den == 0.0:
            return {
                "score": 50.0,
                "confidence": 0.0,
                "status": "neutral_no_overlap",
                "aligned_interests": [],
                "aligned_interest_details": [],
                "divergent_interests": [],
                "has_external_interests": bool(self.external_interests),
            }

        score = round(100.0 * (num / den), 4)
        return {
            "score": score,
            "confidence": self.confidence,
            "status": "known",
            "aligned_interests": aligned[:5],
            "aligned_interest_details": aligned_details[:5],
            "divergent_interests": divergent[:5],
            "has_external_interests": bool(self.external_interests),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "status": self.status,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "weighted_evidence": self.weighted_evidence,
            "explicit_interests": self.explicit_interests,
            "external_interests_count": len(self.external_interests),
            "inferred_interests": self.inferred_interests if self.status == "sufficient_data" else {},
        }

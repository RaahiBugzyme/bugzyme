"""Public entry point. Backends call CompatibilityModel; they never re-implement scoring."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .compatibility_engine import CompatibilityEngine


class CompatibilityModel:
    """Layer 1: deterministic profile-compatibility model (no training, no labels)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.engine = CompatibilityEngine(config)

    @property
    def config(self) -> Dict[str, Any]:
        return self.engine.config

    def check_eligibility(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> Dict[str, Any]:
        return self.engine.check_eligibility(profile_a, profile_b)

    def predict_pair(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> Dict[str, Any]:
        return self.engine.predict_pair(profile_a, profile_b)

    def predict_matches(self, user: Dict[str, Any], candidates: Iterable[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        return self.engine.predict_matches(user, candidates, top_k)

    def score_pair(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> Dict[str, Any]:
        """Scores WITHOUT the eligibility gate. For analysis/testing only; never use to recommend."""
        return self.engine.score_pair(profile_a, profile_b)


# ==========================================================================
# v2.2.0 (append-only): personalized recommendation layer.
# `CompatibilityModel` above is UNCHANGED and keeps working on its own.
# Layers (each returns its own separate signal):
#   eligibility -> core compatibility -> location -> preferences -> behavior -> mutual interest -> ranking
# ==========================================================================
from datetime import datetime as _datetime  # noqa: E402
from typing import Callable, Tuple  # noqa: E402

from .behavior import DECISION_ACTIONS, summarize_behavior, usable_events, utcnow  # noqa: E402
from .compatibility_engine import CATEGORIES  # noqa: E402
from .location import GazetteerResolver, GeoResolver, compare_locations  # noqa: E402
from .mutual_interest import UNAVAILABLE, MutualInterestModel  # noqa: E402
from .personalization import UserPreferenceModel  # noqa: E402
from .preferences import check_hard_preferences, evaluate_bilateral_preferences, evaluate_preferences, intention_compatibility  # noqa: E402
from .ranking import combine_signals  # noqa: E402
from .search_intent import learn_search_intent, score_search_intent  # noqa: E402
from .explainability import explain_recommendation  # noqa: E402
from .personality import evaluate_personality_compatibility  # noqa: E402
from .interests import UserInterestProfile  # noqa: E402

_CATEGORY_LABELS = {"demographics": "age and generation", "career_education": "career and education",
                    "values_culture": "values and culture", "lifestyle": "lifestyle", "family": "family",
                    "attraction": "physical attributes"}
_EXCLUDE_ACTIONS = DECISION_ACTIONS + ("MATCH", "UNMATCH")


def _pid(profile: Dict[str, Any]) -> Any:
    return profile.get("id", profile.get("user_id"))


def check_extended_pair_eligibility(
    compat_engine: CompatibilityEngine,
    user: Dict[str, Any],
    candidate: Dict[str, Any],
    config: Dict[str, Any],
    user_preferences: Optional[Dict[str, Any]] = None,
    candidate_preferences: Optional[Dict[str, Any]] = None,
    geo_resolver: Optional[GeoResolver] = None,
    user_label: str = "Your hard preference",
    candidate_label: str = "Candidate's hard preference",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Evaluates base adulthood/sex-orientation gate, hard criteria/exclusions, and max distance."""
    base = compat_engine.check_eligibility(user, candidate)
    prefs_user = user_preferences or user.get("preferences") or user.get("user_preferences")
    prefs_cand = candidate_preferences or candidate.get("preferences") or candidate.get("user_preferences")
    resolver = geo_resolver or GazetteerResolver.default()
    loc = compare_locations(user, candidate, config, resolver, prefs_user, prefs_cand)
    reasons: List[str] = [] if base["eligible"] else [base["reason"]]
    if base["eligible"]:
        if prefs_user:
            reasons += check_hard_preferences(prefs_user, candidate, config, user_label)
        if config.get("preferences", {}).get("hard_preferences_mutual", True) and prefs_cand:
            reasons += check_hard_preferences(prefs_cand, user, config, candidate_label)
        if loc.get("within_max_distance") is False:
            reasons.append(f"Beyond a hard maximum distance ({loc['distance_km']} km away)")
    reason_str = base["reason"] if (base["eligible"] and not reasons) else ("; ".join(reasons) if reasons else base["reason"])
    elig = {
        "eligible": not reasons and base["eligible"],
        "reason": reason_str,
        "reasons": reasons if reasons else ([] if base["eligible"] else [base["reason"]]),
    }
    return elig, loc


class RecommendationModel:
    """Personalized recommendations. Reuses CompatibilityModel; never re-implements its formulas."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, compatibility_model: Optional[CompatibilityModel] = None,
                 geo_resolver: Optional[GeoResolver] = None, mutual_interest_model: Optional[MutualInterestModel] = None):
        self.compatibility = compatibility_model or CompatibilityModel(config)
        self.config = self.compatibility.config
        self.resolver = geo_resolver or GazetteerResolver.default()
        self.mutual_interest = mutual_interest_model or UNAVAILABLE

    # ------------------------------------------------------------ eligibility
    def check_extended_eligibility(self, user, candidate, user_preferences=None, candidate_preferences=None):
        """Base eligibility (sex/orientation/adult) + hard preferences + hard max distance. Returns (eligibility, location)."""
        elig, loc = check_extended_pair_eligibility(
            self.compatibility.engine, user, candidate, self.config,
            user_preferences=user_preferences, candidate_preferences=candidate_preferences,
            geo_resolver=self.resolver,
            user_label="Your hard preference", candidate_label="Candidate's hard preference",
        )
        return {"eligible": elig["eligible"], "reasons": elig["reasons"] if not elig["eligible"] else []}, loc

    # ------------------------------------------------------------- one candidate
    def evaluate_candidate(self, user, candidate, user_preferences=None, candidate_preferences=None,
                           preference_model: Optional[UserPreferenceModel] = None,
                           search_intent: Optional[Dict[str, Any]] = None,
                           user_personality: Optional[Dict[str, Any]] = None,
                           candidate_personality: Optional[Dict[str, Any]] = None,
                           interest_profile: Optional[UserInterestProfile] = None,
                           personalization_enabled: bool = True) -> Dict[str, Any]:
        cfg = self.config
        uid, cid = _pid(user), _pid(candidate)
        elig, loc = self.check_extended_eligibility(user, candidate, user_preferences, candidate_preferences)

        pers_eval = None
        if user_personality is not None or candidate_personality is not None:
            pers_eval = evaluate_personality_compatibility(user_personality, candidate_personality, cfg)
            if pers_eval.get("hard_failures"):
                elig["reasons"].extend(pers_eval["hard_failures"])
                elig["eligible"] = False

        record: Dict[str, Any] = {"user_id": uid, "candidate_id": cid, "eligibility": elig, "package_version": cfg["package_version"]}
        if not elig["eligible"]:
            record.update(compatibility=None, location=None, preferences=None, relationship_intention=None, behavior=None,
                          mutual_interest=None, ranking={"final_score": None, "components": [], "weights_are_validated": False},
                          explanation=list(elig["reasons"]))
            return record

        comp = self.compatibility.score_pair(user, candidate)
        if candidate_preferences:
            pref = evaluate_bilateral_preferences(user_preferences, user, candidate_preferences, candidate, cfg)
        else:
            pref = evaluate_preferences(user_preferences, candidate, cfg)
        intention = intention_compatibility(user.get("relationship_intention"), candidate.get("relationship_intention"), cfg)

        if not personalization_enabled:
            behavior = {"score": None, "confidence": 0.0, "status": "disabled", "evidence_count": 0, "supporting_features": [], "baseline_score": None}
            mutual = {"probability": None, "confidence": 0.0, "status": "disabled", "model_version": None}
        else:
            if preference_model is not None:
                behavior = preference_model.score_candidate(user, candidate)
                behavior["baseline_score"] = None if preference_model.overall_like_rate is None else round(100 * preference_model.overall_like_rate, 4)
            else:
                behavior = {"score": None, "confidence": 0.0, "status": "cold_start", "evidence_count": 0, "supporting_features": [], "baseline_score": None}
            mutual = self.mutual_interest.predict_mutual(user, candidate, self.compatibility.engine, cfg, self.resolver)

        signals = {
            "compatibility": {"score": comp["adjusted_score"], "confidence": None},
            "location": {"score": loc["location_score"], "confidence": loc["location_confidence"]},
            "preferences": {"score": pref["score"], "confidence": pref["confidence"] / 100.0},
            "relationship_intention": {"score": intention["score"], "confidence": 1.0},
            "behavior": {"score": behavior["score"], "confidence": behavior["confidence"] / 100.0},
            "mutual_interest": {"score": None if mutual["probability"] is None else 100.0 * mutual["probability"],
                                "confidence": mutual["confidence"] / 100.0},
        }
        search_signal = None
        if personalization_enabled and search_intent is not None and search_intent.get("status") != "unavailable":
            search_signal = score_search_intent(user, candidate, search_intent, cfg, self.resolver)
            signals["search_intent"] = {"score": search_signal["score"], "confidence": search_signal["confidence"]}

        if pers_eval is not None and pers_eval.get("status") == "known" and pers_eval.get("score") is not None:
            signals["personality"] = {"score": pers_eval["score"], "confidence": pers_eval["confidence"] / 100.0}

        if personalization_enabled and interest_profile is not None and interest_profile.status == "sufficient_data":
            inter_res = interest_profile.score_candidate(candidate)
            if inter_res.get("score") is not None and inter_res.get("status") == "known":
                signals["interests"] = {"score": inter_res["score"], "confidence": inter_res["confidence"] / 100.0}
                record["interests"] = inter_res

        ranking = combine_signals(signals, cfg)
        record.update(
            compatibility={"score": comp["compatibility_score"], "confidence": comp["confidence_score"], "adjusted_score": comp["adjusted_score"],
                           "categories": comp["categories"], "components": comp["components"], "explanation": comp["explanation"]},
            location={k: loc[k] for k in ("distance_km", "location_score", "location_confidence", "location_available", "location_status",
                                          "preferred_distance_km", "preferred_distance_source", "within_preferred_distance",
                                          "max_distance_km", "within_max_distance", "same_region", "same_country", "warnings")},
            preferences=({
                "score": pref["score"], "confidence": pref["confidence"], "status": pref["status"],
                "criteria": pref["criteria"], "warnings": pref["warnings"],
                **({"user_to_candidate": pref["user_to_candidate"], "candidate_to_user": pref["candidate_to_user"]}
                   if "user_to_candidate" in pref else {})
            }),
            relationship_intention=intention, behavior=behavior, mutual_interest=mutual, ranking=ranking)
        if pers_eval is not None:
            record["personality"] = pers_eval
        if search_signal is not None:
            record["search_intent"] = search_signal
            record["search_intent_score"] = search_signal["score"]
            record["search_intent_confidence"] = search_signal["confidence"]
            record["search_intent_status"] = search_signal["status"]
        record["explanation"] = self._explain(record)
        return record

    # -------------------------------------------------------------- explanations
    def _explain(self, r: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        comp, loc, pref, intent, beh, mi = (r["compatibility"], r["location"], r["preferences"],
                                            r["relationship_intention"], r["behavior"], r["mutual_interest"])
        search = r.get("search_intent")
        strong = [_CATEGORY_LABELS[c] for c, s in comp["categories"].items() if s is not None and s >= 75]
        if strong:
            lines.append("Strong profile alignment on " + ", ".join(strong) + ".")
        lines += comp["explanation"]
        status = loc["location_status"]
        if status == "known":
            lines.append(f"Candidate is approximately {loc['distance_km']:g} km away.")
            lines.append("Candidate is within your preferred distance." if loc["within_preferred_distance"]
                         else "Candidate is farther than your preferred distance (soft preference; still eligible).")
        elif status in ("unknown", "partial_unknown"):
            lines.append("Location information is unavailable, so no location penalty was applied.")
        elif status == "unresolved":
            lines.append("Location could not be resolved reliably, so no location signal was used and no penalty was applied.")
        elif status == "coarse":
            lines.append("Only region/country-level location is available, so no distance signal was used.")
        if pref["status"] == "known":
            for name, m in sorted(pref["criteria"].items()):
                if m == 1.0:
                    lines.append(f"Candidate matches your preferred {name.replace('_', ' ')}.")
                elif m == 0.0:
                    lines.append(f"Candidate does not match your preferred {name.replace('_', ' ')} (soft preference; still eligible).")
        if intent["status"] == "known":
            lines.append("Stated relationship intentions are aligned." if intent["score"] >= 75 else
                         "Stated relationship intentions differ." if intent["score"] <= 25 else "Stated relationship intentions are partly aligned.")
        margin = float(self.config["explanation_behavior_margin"])
        if beh["status"] == "cold_start":
            lines.append("No interaction history yet, so behavioral personalization is not used.")
        elif beh["status"] == "insufficient_data":
            lines.append(f"Behavioral evidence is limited ({beh['evidence_count']} decisions), so personalization is not used yet.")
        elif beh["score"] is not None and beh["baseline_score"] is not None:
            if beh["score"] >= beh["baseline_score"] + margin:
                lines.append("Your interactions suggest profiles like this are liked more often than your average.")
            elif beh["score"] <= beh["baseline_score"] - margin:
                lines.append("Your interactions suggest profiles like this are liked less often than your average.")
            if beh["confidence"] < 50:
                lines.append("Behavioral evidence is limited.")
        if search is not None:
            if search["status"] == "insufficient_data":
                lines.append("Search-intent contribution is limited because the evidence is sparse.")
            elif search["score"] is not None and search["supporting_attributes"]:
                labels = ", ".join(search["supporting_attributes"])
                lines.append(f"Candidate aligns with your recent searches for {labels.replace('_', ' ')}.")
        if mi["status"] == "available":
            lines.append(f"Interaction-based model estimates mutual interest at {100 * mi['probability']:.0f}% (not a relationship-success probability).")
        pers = r.get("personality")
        if pers is not None and pers.get("status") == "known":
            lines.extend(pers.get("explanations", []))
        inter = r.get("interests")
        if inter is not None and inter.get("status") == "known":
            alg = inter.get("aligned_interests", [])
            details = inter.get("aligned_interest_details", [])
            external_alg = []
            external_tokens = set()
            for item in details:
                prov = item.get("provenance", [])
                if prov:
                    name = item.get("display_name", "")
                    external_tokens.add(item.get("token", ""))
                    providers = sorted({p.get("provider", "").replace("_", " ").title() for p in prov if p.get("provider")})
                    conf = max([p.get("confidence", 0.0) for p in prov] or [0.0])
                    pct = int(round(conf * 100))
                    external_alg.append(f"{name} ({', '.join(providers)}: {pct}% confidence)")
            if external_alg:
                lines.append("Shared interests in: " + ", ".join(external_alg) + ".")
            behavioral_only = [a for a in alg if a not in external_tokens]
            if behavioral_only:
                lines.append("Shared behavioral interests in: " + ", ".join(behavioral_only) + ".")
            elif not external_alg and alg:
                lines.append("Shared behavioral interests in: " + ", ".join(alg) + ".")
        return lines

    # -------------------------------------------------------------- recommendations
    def behavior_summary(self, user_id, interactions, now: Optional[_datetime] = None) -> Dict[str, Any]:
        return summarize_behavior(interactions or [], user_id, self.config, now or utcnow())

    def fit_preference_model(self, user, interactions, profile_lookup, now) -> UserPreferenceModel:
        return UserPreferenceModel(self.config, self.resolver).fit(user, interactions or [], profile_lookup, now)

    def recommend(self, user: Dict[str, Any], candidates, user_preferences: Optional[Dict[str, Any]] = None,
                  preferences_lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
                  interactions=None, profile_lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
                  personality_lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
                  user_personality: Optional[Dict[str, Any]] = None,
                  interest_profile: Optional[UserInterestProfile] = None,
                  privacy_settings: Optional[Dict[str, Any]] = None,
                  now: Optional[_datetime] = None, limit: int = 20) -> List[Dict[str, Any]]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        now = now or utcnow()
        candidates = list(candidates)
        by_id = {str(_pid(c)): c for c in candidates if _pid(c) is not None}
        lookup = profile_lookup or (lambda i: by_id.get(str(i)))
        events = list(interactions or [])
        uid = _pid(user)

        p_enabled = bool((privacy_settings or {}).get("personalization_enabled", True))
        pref_model = None
        if p_enabled and self.config.get("behavior_enabled", True):
            pref_model = self.fit_preference_model(user, events, lookup, now)
        search_intent = learn_search_intent(uid, events, self.config, now) if p_enabled else None

        excluded = set()
        if self.config.get("exclude_decided_candidates", True):
            kept, _ = usable_events(events, uid, now)
            excluded = {str(e["candidate_id"]) for e in kept if e["action"] in _EXCLUDE_ACTIONS}

        results = []
        for candidate in candidates:
            if str(_pid(candidate)) in excluded:
                continue
            cprefs = preferences_lookup(str(_pid(candidate))) if preferences_lookup and _pid(candidate) is not None else None
            cand_pers = personality_lookup(str(_pid(candidate))) if personality_lookup and _pid(candidate) is not None else None
            rec = self.evaluate_candidate(
                user, candidate, user_preferences, cprefs, pref_model, search_intent,
                user_personality=user_personality, candidate_personality=cand_pers,
                interest_profile=interest_profile, personalization_enabled=p_enabled,
            )
            if rec["eligibility"]["eligible"]:
                results.append(rec)
        results.sort(key=lambda r: (-(r["ranking"]["final_score"] if r["ranking"]["final_score"] is not None else -1.0),
                                    -r["compatibility"]["adjusted_score"], str(r["candidate_id"])))
        return results[:limit]

    def explain_candidate(self, user: Dict[str, Any], candidate: Dict[str, Any],
                          user_preferences: Optional[Dict[str, Any]] = None,
                          candidate_preferences: Optional[Dict[str, Any]] = None,
                          preference_model: Optional[UserPreferenceModel] = None,
                          search_intent: Optional[Dict[str, Any]] = None,
                          user_personality: Optional[Dict[str, Any]] = None,
                          candidate_personality: Optional[Dict[str, Any]] = None,
                          interest_profile: Optional[UserInterestProfile] = None,
                          privacy_settings: Optional[Dict[str, Any]] = None,
                          interactions: Optional[Iterable[Dict[str, Any]]] = None,
                          profile_lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
                          now: Optional[_datetime] = None) -> Dict[str, Any]:
        """Provides an explainable, transparent breakdown for why a candidate was or was not recommended."""
        now = now or utcnow()
        events = list(interactions or [])
        p_enabled = bool((privacy_settings or {}).get("personalization_enabled", True))
        lookup = profile_lookup or (lambda i: None)
        pref_model = preference_model
        if pref_model is None and events and p_enabled and self.config.get("behavior_enabled", True):
            pref_model = self.fit_preference_model(user, events, lookup, now)
        intent = search_intent
        if intent is None and events and p_enabled:
            intent = learn_search_intent(_pid(user), events, self.config, now)
        inter_profile = interest_profile
        if inter_profile is None and events and p_enabled:
            inter_profile = UserInterestProfile(self.config).fit(user, events, lookup, now)
        eval_record = self.evaluate_candidate(
            user, candidate,
            user_preferences=user_preferences,
            candidate_preferences=candidate_preferences,
            preference_model=pref_model,
            search_intent=intent,
            user_personality=user_personality,
            candidate_personality=candidate_personality,
            interest_profile=inter_profile,
            personalization_enabled=p_enabled,
        )
        return explain_recommendation(eval_record)


def _extended_check_eligibility(
    self,
    profile_a: Dict[str, Any],
    profile_b: Dict[str, Any],
    user_preferences: Optional[Dict[str, Any]] = None,
    candidate_preferences: Optional[Dict[str, Any]] = None,
    preferences_a: Optional[Dict[str, Any]] = None,
    preferences_b: Optional[Dict[str, Any]] = None,
    resolver: Optional[GeoResolver] = None,
) -> Dict[str, Any]:
    prefs_a = user_preferences or preferences_a
    prefs_b = candidate_preferences or preferences_b
    elig, _ = check_extended_pair_eligibility(
        self.engine, profile_a, profile_b, self.config,
        user_preferences=prefs_a, candidate_preferences=prefs_b,
        geo_resolver=resolver,
        user_label="Your hard preference", candidate_label="Candidate's hard preference",
    )
    return elig


def _extended_predict_pair(
    self,
    profile_a: Dict[str, Any],
    profile_b: Dict[str, Any],
    user_preferences: Optional[Dict[str, Any]] = None,
    candidate_preferences: Optional[Dict[str, Any]] = None,
    preferences_a: Optional[Dict[str, Any]] = None,
    preferences_b: Optional[Dict[str, Any]] = None,
    resolver: Optional[GeoResolver] = None,
) -> Dict[str, Any]:
    prefs_a = user_preferences or preferences_a
    prefs_b = candidate_preferences or preferences_b
    gate, _ = check_extended_pair_eligibility(
        self.engine, profile_a, profile_b, self.config,
        user_preferences=prefs_a, candidate_preferences=prefs_b,
        geo_resolver=resolver,
        user_label="Your hard preference", candidate_label="Candidate's hard preference",
    )
    result: Dict[str, Any] = {
        "user_a": profile_a.get("id", profile_a.get("user_id")),
        "user_b": profile_b.get("id", profile_b.get("user_id")),
        "eligible": gate["eligible"],
        "eligibility_reason": gate["reason"],
    }
    if not gate["eligible"]:
        reasons = gate.get("reasons") or [gate["reason"]]
        result.update(
            compatibility_score=None,
            confidence_score=None,
            adjusted_score=None,
            categories={c: None for c in CATEGORIES},
            components=None,
            explanation=reasons,
        )
    else:
        result.update(self.score_pair(profile_a, profile_b))
    result["model_version"] = self.config["model_version"]
    if prefs_a is not None or prefs_b is not None:
        result["preferences"] = evaluate_bilateral_preferences(
            prefs_a, profile_a, prefs_b, profile_b, self.config
        )
    return result


def _extended_predict_matches(
    self,
    user: Dict[str, Any],
    candidates: Iterable[Dict[str, Any]],
    top_k: int = 10,
    user_preferences: Optional[Dict[str, Any]] = None,
    candidate_preferences_lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    resolver: Optional[GeoResolver] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    eligible = []
    for candidate in candidates:
        cand_id = candidate.get("id", candidate.get("user_id"))
        cand_prefs = candidate_preferences_lookup(str(cand_id)) if candidate_preferences_lookup and cand_id is not None else None
        res = self.predict_pair(
            user, candidate,
            user_preferences=user_preferences,
            candidate_preferences=cand_prefs,
            resolver=resolver,
        )
        if res["eligible"]:
            eligible.append(res)
    eligible.sort(key=lambda r: (-r["adjusted_score"], -r["confidence_score"], str(r["user_b"])))
    return eligible[:top_k]


CompatibilityModel.check_eligibility = _extended_check_eligibility
CompatibilityModel.predict_pair = _extended_predict_pair
CompatibilityModel.predict_matches = _extended_predict_matches


def _extended_explain_pair(
    self,
    profile_a: Dict[str, Any],
    profile_b: Dict[str, Any],
    user_preferences: Optional[Dict[str, Any]] = None,
    candidate_preferences: Optional[Dict[str, Any]] = None,
    preferences_a: Optional[Dict[str, Any]] = None,
    preferences_b: Optional[Dict[str, Any]] = None,
    resolver: Optional[GeoResolver] = None,
) -> Dict[str, Any]:
    pred = self.predict_pair(
        profile_a, profile_b,
        user_preferences=user_preferences, candidate_preferences=candidate_preferences,
        preferences_a=preferences_a, preferences_b=preferences_b,
        resolver=resolver,
    )
    return explain_recommendation(pred)


CompatibilityModel.explain_pair = _extended_explain_pair


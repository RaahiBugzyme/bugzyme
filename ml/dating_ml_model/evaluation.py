"""Offline, chronological evaluation of recommendation ranking.

This module consumes caller-supplied profiles and validated interaction events.
It never creates labels, users, events, outcomes, or training data, and it does
not alter the production recommendation configuration.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .behavior import parse_timestamp, validate_event
from .model import RecommendationModel

POSITIVE_OUTCOMES = frozenset({"LIKE", "SUPER_LIKE", "MATCH"})
NEGATIVE_OUTCOMES = frozenset({"PASS"})
EVALUATED_OUTCOMES = POSITIVE_OUTCOMES | NEGATIVE_OUTCOMES
IGNORED_OUTCOMES = frozenset({"VIEW", "SEARCH", "SAVE", "UNMATCH", "MESSAGE"})


def calculate_ranking_metrics(
    recommended_ids: Sequence[str], positive_ids: Set[str], k: int
) -> Dict[str, Optional[float]]:
    """Calculate Precision@K, Recall@K, and NDCG@K for one evaluation case."""
    if k < 1:
        raise ValueError("k must be a positive integer")
    top = [str(value) for value in recommended_ids[:k]]
    hits = [index for index, candidate_id in enumerate(top) if candidate_id in positive_ids]
    precision = len(hits) / len(top) if top else None
    recall = len(hits) / len(positive_ids) if positive_ids else None
    dcg = sum(1.0 / _log2(index + 2) for index in hits)
    ideal_hits = min(len(positive_ids), len(top))
    idcg = sum(1.0 / _log2(index + 2) for index in range(ideal_hits))
    ndcg = dcg / idcg if idcg else None
    return {
        "precision_at_k": _round(precision),
        "recall_at_k": _round(recall),
        "ndcg_at_k": _round(ndcg),
    }


def evaluate_recommendations(
    profiles: Iterable[Dict[str, Any]],
    interactions: Iterable[Dict[str, Any]],
    cutoff: datetime,
    config: Optional[Dict[str, Any]] = None,
    preferences: Optional[Dict[str, Dict[str, Any]]] = None,
    k: int = 10,
) -> Dict[str, Any]:
    """Evaluate current ranking against outcomes occurring after ``cutoff``.

    Cutoffs are normalized to naive UTC, matching the project timestamp policy.
    Events at or after the cutoff are evaluation-only outcomes. Only events
    strictly before the cutoff are passed to the recommendation pipeline.
    """
    cutoff = parse_timestamp(cutoff)
    if cutoff is None:
        raise ValueError("cutoff must be a valid datetime")
    if k < 1:
        raise ValueError("k must be a positive integer")
    supplied_profiles = [dict(profile) for profile in profiles]
    profile_by_id = {str(_profile_id(profile)): profile for profile in supplied_profiles
                     if _profile_id(profile) is not None}
    events, invalid_events = _normalize_events(interactions)
    before = [event for event in events if event["_ts"] < cutoff]
    after = [event for event in events if event["_ts"] >= cutoff]
    base_model = RecommendationModel(config)
    production_config = copy.deepcopy(base_model.config)
    comparison_config = copy.deepcopy(production_config)
    comparison_config.setdefault("final_ranking", {}).setdefault("weights", {})["search_intent"] = 0.0

    cases: List[Dict[str, Any]] = []
    excluded = {"missing_profile": 0, "invalid_event": len(invalid_events),
                "insufficient_outcomes": 0}
    for user_id, user in sorted(profile_by_id.items()):
        outcomes, missing_outcomes = _outcome_labels(after, user_id, set(profile_by_id))
        excluded["missing_profile"] += missing_outcomes
        if not outcomes[0] and not outcomes[1]:
            excluded["insufficient_outcomes"] += 1
            continue
        history = [event for event in before if str(event["user_id"]) == user_id]
        candidates = [profile for candidate_id, profile in sorted(profile_by_id.items())
                      if candidate_id != user_id]
        current = RecommendationModel(production_config)
        without_search = RecommendationModel(comparison_config)
        current_rows = current.recommend(
            user, candidates, user_preferences=(preferences or {}).get(user_id),
            interactions=history, profile_lookup=profile_by_id.get, now=cutoff, limit=len(candidates) or 1,
        )
        no_search_rows = without_search.recommend(
            user, candidates, user_preferences=(preferences or {}).get(user_id),
            interactions=history, profile_lookup=profile_by_id.get, now=cutoff, limit=len(candidates) or 1,
        )
        current_ids = [str(row["candidate_id"]) for row in current_rows]
        no_search_ids = [str(row["candidate_id"]) for row in no_search_rows]
        current_eligible_ids = sorted(current_ids)
        no_search_eligible_ids = sorted(no_search_ids)
        common_ids = set(current_ids) & set(no_search_ids)
        if not common_ids:
            excluded["insufficient_outcomes"] += 1
            continue
        current_ids = [candidate_id for candidate_id in current_ids if candidate_id in common_ids]
        no_search_ids = [candidate_id for candidate_id in no_search_ids if candidate_id in common_ids]
        positive_ids, negative_ids = outcomes
        cases.append({
            "user_id": user_id,
            "profile_group": _profile_group(user),
            "search_history_before_cutoff": any(event["action"] == "SEARCH" for event in history),
            "history_event_count": len(history),
            "outcome_event_count": len(positive_ids | negative_ids),
            "candidates_evaluated": len(common_ids),
            "current_eligible_candidate_ids": current_eligible_ids,
            "without_search_intent_eligible_candidate_ids": no_search_eligible_ids,
            "eligible_candidate_ids": sorted(common_ids),
            "positive_outcomes": len(positive_ids),
            "negative_outcomes": len(negative_ids),
            "current": _case_result(current_ids, positive_ids, negative_ids, k),
            "without_search_intent": _case_result(no_search_ids, positive_ids, negative_ids, k),
        })

    return _report(cases, excluded, invalid_events, cutoff, k, len(profile_by_id),
                   len(events), config is None)


def write_evaluation_report(report: Dict[str, Any], path: str) -> None:
    """Write a deterministic JSON evaluation report."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _normalize_events(events: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    valid: List[Dict[str, Any]] = []
    invalid: List[str] = []
    for index, event in enumerate(events):
        try:
            clean = validate_event(dict(event))
            timestamp = parse_timestamp(clean["timestamp"])
            if timestamp is None:
                raise ValueError("invalid timestamp")
            valid.append({**clean, "_ts": timestamp})
        except (TypeError, ValueError):
            invalid.append(str(index))
    valid.sort(key=lambda event: (event["_ts"], str(event["user_id"]),
                                 str(event.get("candidate_id")), event["action"]))
    return valid, invalid


def _outcome_labels(events: Iterable[Dict[str, Any]], user_id: str,
                    known_profile_ids: Set[str]) -> Tuple[Tuple[Set[str], Set[str]], int]:
    latest: Dict[str, Tuple[datetime, str]] = {}
    missing = 0
    for event in events:
        if str(event["user_id"]) != user_id or event["action"] not in (EVALUATED_OUTCOMES | {"UNMATCH"}):
            continue
        candidate_id = event.get("candidate_id")
        if candidate_id is None:
            continue
        if str(candidate_id) not in known_profile_ids:
            missing += 1
            continue
        latest[str(candidate_id)] = (event["_ts"], event["action"])
    positive = {candidate for candidate, (_, action) in latest.items() if action in POSITIVE_OUTCOMES}
    negative = {candidate for candidate, (_, action) in latest.items() if action in NEGATIVE_OUTCOMES}
    return (positive, negative), missing


def _case_result(recommended: List[str], positive: Set[str], negative: Set[str], k: int) -> Dict[str, Any]:
    metrics = calculate_ranking_metrics(recommended, positive, k)
    return {**metrics, "recommended_at_k": [str(value) for value in recommended[:k]],
            "positive_outcomes": len(positive), "negative_outcomes": len(negative)}


def _report(cases: List[Dict[str, Any]], excluded: Dict[str, int], invalid: List[str],
            cutoff: datetime, k: int, profile_count: int, event_count: int,
            default_config: bool) -> Dict[str, Any]:
    current = _aggregate(cases, "current")
    without_search = _aggregate(cases, "without_search_intent")
    return {
        "status": "available" if current["users_evaluated"] else "insufficient_data",
        "cutoff": cutoff.isoformat(),
        "k": k,
        "profiles_supplied": profile_count,
        "events_supplied": event_count,
        "users_evaluated": current["users_evaluated"],
        "candidates_evaluated": sum(case["candidates_evaluated"] for case in cases),
        "positive_observed_outcomes": sum(case["positive_outcomes"] for case in cases),
        "negative_observed_outcomes": sum(case["negative_outcomes"] for case in cases),
        "coverage": _round(current["users_evaluated"] / profile_count if profile_count else None),
        "excluded": excluded,
        "invalid_event_indexes": invalid,
        "profiles": {
            "complete": _group_summary(cases, "complete"),
            "incomplete": _group_summary(cases, "incomplete"),
            "without_search_history": _group_summary(cases, "no_search_history"),
        },
        "metrics": {"current": current, "without_search_intent": without_search},
        "cases": cases,
        "definitions": {
            "positive_outcomes": sorted(POSITIVE_OUTCOMES),
            "negative_outcomes": sorted(NEGATIVE_OUTCOMES),
            "ignored_for_labels": sorted(IGNORED_OUTCOMES),
            "label_resolution": "latest LIKE, SUPER_LIKE, PASS, or MATCH per candidate after cutoff wins",
            "compatibility_note": "Outcome labels are observed interaction outcomes, not compatibility scores or relationship-success labels.",
            "chronology": "Cutoffs and event timestamps are compared in UTC. Only events strictly before cutoff are supplied to recommendations; events at or after cutoff are evaluation outcomes.",
            "search_comparison": "The comparison sets search_intent ranking weight to zero in an evaluation-only config copy. Both variants receive the same profiles, cutoff, preferences, and pre-cutoff history; metrics use their common eligible candidate IDs.",
            "unobserved_candidates": "Unknown, not confirmed negative. Only explicit PASS events are negative labels.",
            "metric_policy": "Precision@K counts observed positives in the recommended top-K; Recall@K divides observed positive hits by observed positive labels; NDCG@K discounts observed positive hits. Unobserved candidates are neither positive nor negative.",
            "match_state_policy": "MATCH is positive until a later UNMATCH neutralizes it; UNMATCH is never a confirmed negative. A later MATCH becomes positive again.",
            "config_source": "project defaults" if default_config else "caller-supplied copy",
        },
    }


def _aggregate(cases: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    values = [case[key] for case in cases]
    return {"users_evaluated": len(values),
            "precision_at_k": _mean(values, "precision_at_k"),
            "recall_at_k": _mean(values, "recall_at_k"),
            "ndcg_at_k": _mean(values, "ndcg_at_k")}


def _group_summary(cases: List[Dict[str, Any]], group: str) -> Dict[str, Any]:
    selected = [case for case in cases if
                (case["profile_group"] == group if group in {"complete", "incomplete"}
                 else not case["search_history_before_cutoff"])]
    return {"users_evaluated": len(selected),
            "precision_at_k": _mean([case["current"] for case in selected], "precision_at_k"),
            "recall_at_k": _mean([case["current"] for case in selected], "recall_at_k"),
            "ndcg_at_k": _mean([case["current"] for case in selected], "ndcg_at_k")}


def _profile_group(profile: Dict[str, Any]) -> str:
    required = ("id", "age", "sex", "orientation", "job", "education",
                "religion", "city", "state", "country")
    return "complete" if all(profile.get(field) not in (None, "") for field in required) else "incomplete"


def _profile_id(profile: Dict[str, Any]) -> Any:
    return profile.get("id", profile.get("user_id"))


def _mean(rows: List[Dict[str, Any]], field: str) -> Optional[float]:
    values = [row[field] for row in rows if row.get(field) is not None]
    return _round(sum(values) / len(values) if values else None)


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 6)


def _log2(value: float) -> float:
    import math
    return math.log(value, 2)



def compute_ranking_metrics_for_user(
    recommended_candidate_ids: Sequence[str],
    positive_candidate_ids: Set[str],
    k_values: Sequence[int] = (3, 5, 10),
) -> Dict[str, float]:
    """Computes ranking metrics (Precision@K, Recall@K, HitRate@K, NDCG@K, MRR) for a single user."""
    rec_ids = [str(c) for c in recommended_candidate_ids]
    pos_ids = {str(c) for c in positive_candidate_ids}
    total_pos = len(pos_ids)
    metrics: Dict[str, float] = {}

    mrr = 0.0
    for rank, cid in enumerate(rec_ids, start=1):
        if cid in pos_ids:
            mrr = 1.0 / rank
            break
    metrics["mrr"] = round(mrr, 4)

    for k in k_values:
        if k < 1:
            continue
        top_k = rec_ids[:k]
        hits = [idx for idx, cid in enumerate(top_k) if cid in pos_ids]
        num_hits = len(hits)

        precision = (num_hits / len(top_k)) if top_k else 0.0
        recall = (num_hits / total_pos) if total_pos > 0 else 0.0
        hit_rate = 1.0 if num_hits > 0 else 0.0

        dcg = sum((1.0 / _log2(idx + 2)) for idx in hits)
        ideal_hits = min(total_pos, len(top_k))
        idcg = sum((1.0 / _log2(idx + 2)) for idx in range(ideal_hits))
        ndcg = (dcg / idcg) if idcg > 0 else 0.0

        metrics[f"precision@{k}"] = round(precision, 4)
        metrics[f"recall@{k}"] = round(recall, 4)
        metrics[f"hit_rate@{k}"] = round(hit_rate, 4)
        metrics[f"ndcg@{k}"] = round(ndcg, 4)

    return metrics


class PersonalizationEvaluationHarness:
    """Evaluates ranking performance comparing baseline vs personalized models."""

    def __init__(self, data_source_note: str = "offline_benchmarks"):
        self.data_source_note = data_source_note

    def evaluate_system(
        self,
        baseline_ranker: Any,
        personalized_ranker: Any,
        test_users: Sequence[Dict[str, Any]],
        candidate_pool: Sequence[Dict[str, Any]],
        ground_truth: Dict[str, Set[str]],
        k_list: Sequence[int] = (3, 5, 10),
    ) -> Dict[str, Any]:
        """Compares baseline ranking vs personalized ranking across test users."""
        baseline_metrics_agg: Dict[str, float] = {}
        personalized_metrics_agg: Dict[str, float] = {}
        users_evaluated = 0
        rank_shifts: List[float] = []

        for user in test_users:
            uid = str(user.get("id", user.get("user_id")))
            positives = {str(c) for c in ground_truth.get(uid, set())}
            if not positives:
                continue

            base_recs = baseline_ranker(user, candidate_pool)
            base_ids = [str(r.get("candidate_id", r.get("id"))) for r in base_recs]
            base_m = compute_ranking_metrics_for_user(base_ids, positives, k_list)

            pers_recs = personalized_ranker(user, candidate_pool)
            pers_ids = [str(r.get("candidate_id", r.get("id"))) for r in pers_recs]
            pers_m = compute_ranking_metrics_for_user(pers_ids, positives, k_list)

            for key, val in base_m.items():
                baseline_metrics_agg[key] = baseline_metrics_agg.get(key, 0.0) + val
            for key, val in pers_m.items():
                personalized_metrics_agg[key] = personalized_metrics_agg.get(key, 0.0) + val

            overlap = set(base_ids[:5]) & set(pers_ids[:5])
            rank_shifts.append(5.0 - len(overlap))
            users_evaluated += 1

        if users_evaluated > 0:
            for k in baseline_metrics_agg:
                baseline_metrics_agg[k] = round(baseline_metrics_agg[k] / users_evaluated, 4)
            for k in personalized_metrics_agg:
                personalized_metrics_agg[k] = round(personalized_metrics_agg[k] / users_evaluated, 4)

        avg_shift = round(sum(rank_shifts) / len(rank_shifts), 2) if rank_shifts else 0.0

        return {
            "users_evaluated": users_evaluated,
            "data_source": self.data_source_note,
            "baseline_metrics": baseline_metrics_agg,
            "personalized_metrics": personalized_metrics_agg,
            "average_top5_rank_shift": avg_shift,
            "limitations": [
                "Evaluation measures algorithm ranking metrics on specified holdout interactions.",
                "Does not assert real-world relationship success or marriage probability without longitudinal outcomes.",
            ],
        }


if __name__ == "__main__":
    print(json.dumps({
        "status": "unavailable",
        "reason": "No genuine evaluation profiles or interaction events were supplied.",
        "metrics": None,
    }, indent=2, sort_keys=True))


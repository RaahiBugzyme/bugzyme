import json
from datetime import datetime, timezone, timedelta

from dating_ml_model.evaluation import calculate_ranking_metrics, evaluate_recommendations
from dating_ml_model import RecommendationModel


CUTOFF = datetime(2026, 10, 1, 12, 0, 0)


def profile(profile_id, **values):
    result = {
        "id": profile_id,
        "age": 30,
        "sex": "m" if profile_id != "u1" else "f",
        "orientation": "straight",
        "job": "science / tech / engineering",
    }
    result.update(values)
    return result


PROFILES = [
    profile("u1"),
    profile("tech"),
    profile("health", job="medicine / health"),
]


def event(user_id, candidate_id, action, timestamp, **values):
    return {
        "user_id": user_id,
        "candidate_id": candidate_id,
        "action": action,
        "timestamp": timestamp,
        **values,
    }


def genuine_events():
    return [
        event("u1", None, "SEARCH", "2026-09-28T12:00:00Z",
              search_criteria={"profession_group": "technology_science"}),
        event("u1", None, "SEARCH", "2026-09-29T12:00:00Z",
              search_criteria={"profession_group": "technology_science"}),
        event("u1", None, "SEARCH", "2026-09-30T12:00:00Z",
              search_criteria={"profession_group": "technology_science"}),
        event("u1", "tech", "LIKE", "2026-10-02T12:00:00Z"),
        event("u1", "health", "PASS", "2026-10-02T13:00:00Z"),
    ]


def test_metric_calculation_is_deterministic_and_known():
    expected = {
        "precision_at_k": 0.5,
        "recall_at_k": 1.0,
        "ndcg_at_k": 1.0,
    }
    assert calculate_ranking_metrics(["positive", "negative"], {"positive"}, 2) == expected
    assert calculate_ranking_metrics(["positive", "negative"], {"positive"}, 2) == expected


def test_chronological_split_does_not_leak_future_events_into_recommendations():
    report = evaluate_recommendations(PROFILES, genuine_events(), CUTOFF, k=2)
    case = report["cases"][0]

    assert case["history_event_count"] == 3
    assert case["outcome_event_count"] == 2
    assert case["search_history_before_cutoff"] is True
    assert case["current"]["recommended_at_k"] == case["without_search_intent"]["recommended_at_k"]
    assert "compared in UTC" in report["definitions"]["chronology"]
    assert "Only events strictly before cutoff" in report["definitions"]["chronology"]


def test_cutoff_normalizes_naive_utc_and_aware_offsets_and_excludes_exact_cutoff():
    events = [
        event("u1", None, "SEARCH", "2026-10-01T11:00:00+00:00",
              search_criteria={"city": "Pune"}),
        event("u1", None, "SEARCH", "2026-10-01T17:30:00+05:30",
              search_criteria={"city": "Mumbai"}),
        event("u1", "tech", "LIKE", "2026-10-01T12:00:00Z"),
    ]
    aware = evaluate_recommendations(PROFILES, events, CUTOFF.replace(tzinfo=timezone.utc), k=2)
    offset = evaluate_recommendations(
        PROFILES, events,
        datetime(2026, 10, 1, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        k=2,
    )
    naive = evaluate_recommendations(PROFILES, events, CUTOFF, k=2)

    assert aware["cutoff"] == offset["cutoff"] == naive["cutoff"] == "2026-10-01T12:00:00"
    assert aware["cases"][0]["history_event_count"] == 1
    assert aware == offset == naive


def test_evaluation_labels_are_separate_from_compatibility_scores():
    report = evaluate_recommendations(PROFILES, genuine_events(), CUTOFF, k=2)

    assert report["positive_observed_outcomes"] == 1
    assert report["negative_observed_outcomes"] == 1
    assert "compatibility" not in report["definitions"]["positive_outcomes"]
    assert "relationship-success" in report["definitions"]["compatibility_note"]


def test_match_unmatch_state_is_neutral_and_can_become_positive_again():
    events = [
        event("u1", "tech", "MATCH", "2026-10-02T12:00:00Z"),
        event("u1", "tech", "UNMATCH", "2026-10-03T12:00:00Z"),
    ]
    report = evaluate_recommendations(PROFILES, events, CUTOFF, k=2)
    assert report["positive_observed_outcomes"] == 0
    assert report["negative_observed_outcomes"] == 0
    assert "UNMATCH neutralizes" in report["definitions"]["match_state_policy"]

    rematched = evaluate_recommendations(PROFILES, [
        *events, event("u1", "tech", "MATCH", "2026-10-04T12:00:00Z"),
    ], CUTOFF, k=2)
    assert rematched["positive_observed_outcomes"] == 1


def test_match_unmatch_histories_are_independent_per_candidate():
    profiles = [*PROFILES, profile("other")]
    events = [
        event("u1", "tech", "MATCH", "2026-10-02T12:00:00Z"),
        event("u1", "tech", "UNMATCH", "2026-10-03T12:00:00Z"),
        event("u1", "other", "MATCH", "2026-10-02T12:00:00Z"),
    ]
    report = evaluate_recommendations(profiles, events, CUTOFF, k=3)
    assert report["positive_observed_outcomes"] == 1
    assert report["cases"][0]["positive_outcomes"] == 1


def test_missing_profile_outcomes_are_excluded_and_counted():
    report = evaluate_recommendations(PROFILES, [
        event("u1", "ghost", "LIKE", "2026-10-02T12:00:00Z"),
        event("u1", "tech", "LIKE", "2026-10-02T12:01:00Z"),
    ], CUTOFF, k=2)
    assert report["positive_observed_outcomes"] == 1
    assert report["excluded"]["missing_profile"] == 1
    assert report["cases"][0]["positive_outcomes"] == 1


def test_unobserved_candidates_are_not_confirmed_pass_labels():
    metrics = calculate_ranking_metrics(["observed", "unobserved"], {"observed"}, 2)
    assert metrics["precision_at_k"] == 0.5
    assert metrics["recall_at_k"] == 1.0
    assert metrics["ndcg_at_k"] == 1.0
    report = evaluate_recommendations(PROFILES, [
        event("u1", "tech", "LIKE", "2026-10-02T12:00:00Z"),
    ], CUTOFF, k=2)
    assert report["negative_observed_outcomes"] == 0
    assert "Unknown, not confirmed negative" in report["definitions"]["unobserved_candidates"]


def test_incomplete_profiles_and_missing_data_are_evaluated_without_penalty_or_crash():
    profiles = [
        profile("u1", city="Pune", state="Maharashtra", country="India"),
        profile("incomplete", age=30, city=None, state=None, country="India"),
    ]
    events = [
        event("u1", "incomplete", "LIKE", "2026-10-02T12:00:00Z"),
    ]
    report = evaluate_recommendations(profiles, events, CUTOFF, k=1)

    assert report["status"] == "available"
    assert report["profiles"]["incomplete"]["users_evaluated"] == 1
    assert report["candidates_evaluated"] == 1


def test_insufficient_samples_report_unavailable_metrics():
    report = evaluate_recommendations([], [], CUTOFF, k=2)

    assert report["status"] == "insufficient_data"
    assert report["users_evaluated"] == 0
    assert report["metrics"]["current"]["precision_at_k"] is None
    assert report["metrics"]["without_search_intent"]["ndcg_at_k"] is None


def test_report_output_is_reproducible_and_json_serializable():
    first = evaluate_recommendations(PROFILES, genuine_events(), CUTOFF, k=2)
    second = evaluate_recommendations(PROFILES, genuine_events(), CUTOFF, k=2)

    assert first == second
    json.dumps(first, sort_keys=True)


def test_search_comparison_has_identical_cases_and_does_not_mutate_config():
    config = json.loads(json.dumps(RecommendationModel().config))
    config["final_ranking"]["weights"]["search_intent"] = 0.25
    config["marker"] = "unchanged"
    original = json.loads(json.dumps(config))
    report = evaluate_recommendations(PROFILES, genuine_events(), CUTOFF, config=config, k=2)

    assert config == original
    for case in report["cases"]:
        assert case["current_eligible_candidate_ids"] == case["without_search_intent_eligible_candidate_ids"]
        assert case["eligible_candidate_ids"] == case["current_eligible_candidate_ids"]
        assert case["positive_outcomes"] >= 0
        assert case["outcome_event_count"] == case["positive_outcomes"] + case["negative_outcomes"]

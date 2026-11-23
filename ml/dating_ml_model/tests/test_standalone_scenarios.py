"""Deterministic automated tests for Standalone Model Validation Scenarios.

Verifies:
1. Scenario 01: Initial recommendations for new user with zero history (Cold Start).
2. Scenario 02: Recommendations with incomplete profile information.
3. Scenario 03: Filtering by explicit dealbreakers and hard eligibility rules.
4. Scenario 04: Bilateral preference compatibility and directional asymmetry.
5. Scenario 05: Behavior-based personalization after controlled interactions.
6. Scenario 06: Interest personalization after searches, views, likes, saves and passes.
7. Scenario 07: Optional self-reported personality compatibility.
8. Scenario 08: Explanations showing why candidates were ranked or excluded.
9. Scenario 09: Personalization opt-out and privacy restrictions.
10. Scenario 10: Cold-start behavior after interaction history is deleted.
11. Persistence Audit: In-memory vs disk boundaries across restarts.
12. Baseline vs. Personalized Ranking Comparison: Demonstrates rank shifts and score adjustments.
"""
import pytest
from dating_ml_model.standalone_validation import StandaloneValidationRunner


@pytest.fixture(scope="module")
def validation_results():
    runner = StandaloneValidationRunner()
    return runner.run_all_scenarios()


def test_scenario_01_cold_start(validation_results):
    res = validation_results["scenarios"]["scenario_01_cold_start"]
    assert res["verified"] is True
    assert res["behavior_status"] == "cold_start"
    assert res["behavior_score"] is None
    assert res["final_score"] is not None
    assert res["candidates_recommended_count"] > 0


def test_scenario_02_incomplete_profiles(validation_results):
    res = validation_results["scenarios"]["scenario_02_incomplete_profiles"]
    assert res["verified"] is True
    assert res["candidate_eligible"] is True
    assert res["location_status"] in ("unknown", "partial_unknown")


def test_scenario_03_dealbreakers_and_eligibility(validation_results):
    res = validation_results["scenarios"]["scenario_03_dealbreakers_and_eligibility"]
    assert res["verified"] is True
    assert res["underage_excluded"] is True
    assert res["same_sex_excluded"] is True
    assert res["missing_age_excluded"] is True
    assert res["smoker_dealbreaker_excluded"] is True
    assert len(res["smoker_hard_failures"]) > 0


def test_scenario_04_bilateral_preferences(validation_results):
    res = validation_results["scenarios"]["scenario_04_bilateral_preferences"]
    assert res["verified"] is True
    assert res["asymmetry_verified"] is True
    assert res["user_to_candidate_score"] != res["candidate_to_user_score"]


def test_scenario_05_behavior_personalization(validation_results):
    res = validation_results["scenarios"]["scenario_05_behavior_personalization"]
    assert res["verified"] is True
    assert res["behavior_status"] == "sufficient_data"
    assert res["behavior_score"] is not None
    assert res["behavior_evidence_count"] >= 10


def test_scenario_06_interest_personalization(validation_results):
    res = validation_results["scenarios"]["scenario_06_interest_personalization"]
    assert res["verified"] is True
    assert res["interest_profile_status"] == "sufficient_data"
    assert res["tech_candidate_interest_score"] > res["finance_candidate_interest_score"]
    assert len(res["aligned_interests_tech"]) > 0


def test_scenario_07_personality_compatibility(validation_results):
    res = validation_results["scenarios"]["scenario_07_personality_compatibility"]
    assert res["verified"] is True
    assert res["introvert_pair_status"] == "known"
    assert res["introvert_pair_score"] > res["extrovert_pair_score"]
    assert res["unspecified_pair_status"] == "unavailable"
    assert res["unspecified_pair_score"] is None


def test_scenario_08_explanations(validation_results):
    res = validation_results["scenarios"]["scenario_08_explanations"]
    assert res["verified"] is True
    assert res["eligible_has_disclaimer"] is True
    assert "probability" in res["eligible_disclaimer_text"].lower()
    assert len(res["ineligible_hard_failures"]) > 0


def test_scenario_09_privacy_and_opt_out(validation_results):
    res = validation_results["scenarios"]["scenario_09_privacy_and_opt_out"]
    assert res["verified"] is True
    assert res["disabled_behavior_status"] == "disabled"
    assert res["disabled_behavior_score"] is None
    assert res["chat_text_stripped"] is True
    assert res["chat_length_preserved"] is True


def test_scenario_10_deletion_cold_start(validation_results):
    res = validation_results["scenarios"]["scenario_10_deletion_cold_start"]
    assert res["verified"] is True
    assert res["initial_events_count"] > 0
    assert res["remaining_events_count"] == 0
    assert res["post_deletion_behavior_status"] == "cold_start"
    assert res["post_deletion_behavior_score"] is None


def test_persistence_audit_boundaries(validation_results):
    res = validation_results["persistence_audit"]
    assert res["restart_behavior_verified"] is True
    assert res["csv_profiles_loaded"] == 5
    assert res["initial_interactions_loaded"] == 1
    assert res["in_memory_mutations_count"] == 2
    assert res["post_restart_interactions_count"] == 1
    assert "database-backed" in res["persistence_limitation_documented"]


def test_baseline_vs_personalized_comparison(validation_results):
    comp = validation_results["baseline_vs_personalized_comparison"]
    assert comp["candidates_compared_count"] > 0
    assert "disclaimer" in comp
    for r in comp["rankings"]:
        assert r["baseline_rank"] is not None
        assert r["personalized_rank"] is not None
        assert r["baseline_final_score"] is not None
        assert r["personalized_final_score"] is not None

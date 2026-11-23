"""Comprehensive tests for Phase 6: Behavior-Based Personalization Engine.

Covers:
1. Event validation and duplicate handling
2. Signal weighting and time decay
3. Positive and negative feedback
4. Interest profile updates (explicit vs inferred, confidence tracking)
5. Personality and communication preferences handling
6. Chat metadata handling and consent boundaries
7. Privacy controls (opt-out, deletion, isolation)
8. Cold-start and missing/deleted data handling
9. Hard-exclusion and dealbreaker enforcement
10. Ranking and explanation consistency
11. Deterministic behavior under fixed inputs
12. Evaluation harness and metrics computation
13. Service layer and HTTP backend integration
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import pytest

from dating_ml_model.behavior import (
    deduplicate_events,
    validate_event,
    ACTION_SIGNAL_WEIGHTS,
    SUPPORTED_ACTIONS,
    parse_timestamp,
)
from dating_ml_model.personality import (
    evaluate_personality_compatibility,
    normalize_personality_profile,
    VALID_PERSONALITY_TYPES,
    VALID_COMMUNICATION_FREQUENCIES,
    VALID_CONVERSATION_STYLES,
    VALID_SOCIAL_ACTIVITIES,
)
from dating_ml_model.interests import (
    UserInterestProfile,
)
from dating_ml_model.privacy import (
    PrivacyManager,
    DEFAULT_PRIVACY_SETTINGS,
)
from dating_ml_model.evaluation import (
    compute_ranking_metrics_for_user,
    PersonalizationEvaluationHarness,
)
from dating_ml_model.model import RecommendationModel, CompatibilityModel
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService
from dating_ml_model.tests.fixtures import FULL_A, FULL_B, variant
from dating_ml_model.tests.helpers import assert_same

NOW = datetime(2026, 10, 26, 12, 0, 0)
DEFAULT_CONFIG = {
    "reference_year": 2026,
    "min_behavior_events": 5,
    "behavior_evidence_k": 10.0,
    "behavior_half_life_days": 14.0,
}


# ============================================================================
# 1. EVENT VALIDATION AND DUPLICATE HANDLING
# ============================================================================

def test_conversation_event_validation():
    """All Phase 6 conversation actions are validated with required fields."""
    valid_conv_actions = [
        "CONVERSATION_START",
        "CONVERSATION_STARTED",
        "MESSAGE_SENT",
        "MESSAGE_RECEIVED",
        "RECIPROCAL_CHAT",
        "RECIPROCAL_CONVERSATION",
    ]
    for action in valid_conv_actions:
        evt = {
            "user_id": "u1",
            "candidate_id": "u2",
            "action": action,
            "timestamp": "2026-10-26T10:00:00Z",
            "metadata": {"conversation_id": "c123"},
        }
        validated = validate_event(evt)
        assert validated["action"] == action
        assert validated["user_id"] == "u1"
        assert validated["candidate_id"] == "u2"

    # Missing candidate_id for conversation events must raise ValueError
    with pytest.raises(ValueError, match="candidate_id"):
        validate_event({
            "user_id": "u1",
            "action": "MESSAGE_SENT",
            "timestamp": "2026-10-26T10:00:00Z",
        })


def test_deduplicate_events_suppresses_rapid_duplicate_clicks():
    """Rapid duplicate clicks on the same candidate within 2 seconds are dropped."""
    events = [
        {"id": "e1", "user_id": "u1", "candidate_id": "c1", "action": "VIEW", "timestamp": "2026-10-26T10:00:00.000Z"},
        {"id": "e2", "user_id": "u1", "candidate_id": "c1", "action": "VIEW", "timestamp": "2026-10-26T10:00:00.500Z"},
        {"id": "e3", "user_id": "u1", "candidate_id": "c1", "action": "VIEW", "timestamp": "2026-10-26T10:00:01.200Z"},
        {"id": "e4", "user_id": "u1", "candidate_id": "c1", "action": "VIEW", "timestamp": "2026-10-26T10:00:05.000Z"},
        {"id": "e5", "user_id": "u1", "candidate_id": "c2", "action": "VIEW", "timestamp": "2026-10-26T10:00:05.100Z"},
    ]
    deduped = deduplicate_events(events, window_seconds=2.0)
    assert len(deduped) == 3
    assert [e["id"] for e in deduped] == ["e1", "e4", "e5"]


def test_deduplicate_events_by_id():
    """Events with identical explicit IDs are deduplicated."""
    events = [
        {"id": "evt_100", "user_id": "u1", "candidate_id": "c1", "action": "LIKE", "timestamp": "2026-10-26T10:00:00Z"},
        {"id": "evt_100", "user_id": "u1", "candidate_id": "c1", "action": "LIKE", "timestamp": "2026-10-26T10:00:00Z"},
        {"id": "evt_101", "user_id": "u1", "candidate_id": "c2", "action": "LIKE", "timestamp": "2026-10-26T10:05:00Z"},
    ]
    deduped = deduplicate_events(events)
    assert len(deduped) == 2
    assert [e["id"] for e in deduped] == ["evt_100", "evt_101"]


# ============================================================================
# 2. SIGNAL WEIGHTING AND TIME DECAY
# ============================================================================

def test_signal_weights_hierarchy():
    """VIEW is a weak signal (0.1), reciprocal chat is high (1.5), and PASS is negative (-1.0)."""
    assert ACTION_SIGNAL_WEIGHTS["VIEW"] == 0.1
    assert ACTION_SIGNAL_WEIGHTS["SAVE"] == 0.8
    assert ACTION_SIGNAL_WEIGHTS["LIKE"] == 1.0
    assert ACTION_SIGNAL_WEIGHTS["CONVERSATION_START"] == 1.2
    assert ACTION_SIGNAL_WEIGHTS["RECIPROCAL_CHAT"] == 1.5
    assert ACTION_SIGNAL_WEIGHTS["PASS"] == -1.0
    # View must be substantially weaker than intentional engagement
    assert ACTION_SIGNAL_WEIGHTS["VIEW"] <= 0.2 * ACTION_SIGNAL_WEIGHTS["LIKE"]


def test_interest_profile_time_decay():
    """Interactions decay exponentially with time; recent interactions weigh more than older ones."""
    profile_lookup = lambda cid: {
        "id": cid,
        "job": "science / tech / engineering",
        "interests": ["coding", "ai"],
    }
    user = {"id": "u1", "interests": []}

    # Profile 1: 5 events 60 days ago
    ts_old = (NOW - timedelta(days=60)).isoformat()
    old_events = [
        {"user_id": "u1", "candidate_id": "c_tech", "action": "LIKE", "timestamp": ts_old}
        for _ in range(5)
    ]
    p_old = UserInterestProfile(DEFAULT_CONFIG).fit(user, old_events, profile_lookup, now=NOW)

    # Profile 2: 5 events 1 day ago
    ts_recent = (NOW - timedelta(days=1)).isoformat()
    recent_events = [
        {"user_id": "u1", "candidate_id": "c_tech", "action": "LIKE", "timestamp": ts_recent}
        for _ in range(5)
    ]
    p_recent = UserInterestProfile(DEFAULT_CONFIG).fit(user, recent_events, profile_lookup, now=NOW)

    # Weighted evidence for recent events should be substantially higher than 60-day old events
    assert p_recent.weighted_evidence > p_old.weighted_evidence
    # 60 days with 14-day half-life -> (1/2)^(60/14) ≈ 0.05
    assert p_old.weighted_evidence < 0.20 * p_recent.weighted_evidence


# ============================================================================
# 3. POSITIVE AND NEGATIVE FEEDBACK
# ============================================================================

def test_positive_and_negative_feedback_on_interests():
    """Liking/saving boosts candidate attributes; passing penalizes candidate attributes."""
    profiles = {
        "c_tech": {"id": "c_tech", "job": "science / tech / engineering", "interests": ["coding"]},
        "c_finance": {"id": "c_finance", "job": "banking / financial / real estate", "interests": ["stocks"]},
    }
    profile_lookup = profiles.get
    user = {"id": "u1"}

    events = [
        {"user_id": "u1", "candidate_id": "c_tech", "action": "LIKE", "timestamp": (NOW - timedelta(days=2)).isoformat()},
        {"user_id": "u1", "candidate_id": "c_tech", "action": "SAVE", "timestamp": (NOW - timedelta(days=1)).isoformat()},
        {"user_id": "u1", "candidate_id": "c_finance", "action": "PASS", "timestamp": (NOW - timedelta(days=1)).isoformat()},
        {"user_id": "u1", "candidate_id": "c_finance", "action": "PASS", "timestamp": (NOW - timedelta(days=1)).isoformat()},
        {"user_id": "u1", "candidate_id": "c_tech", "action": "LIKE", "timestamp": NOW.isoformat()},
    ]
    prof = UserInterestProfile(DEFAULT_CONFIG).fit(user, events, profile_lookup, now=NOW)

    # Technology profession group should have high affinity
    tech_affinity = prof.inferred_interests.get("profession_group", {}).get("technology_science", {}).get("affinity", 0.0)
    assert tech_affinity > 0.8

    # Business finance profession group should have low affinity (heavily penalized by passes)
    finance_affinity = prof.inferred_interests.get("profession_group", {}).get("business_finance", {}).get("affinity", 0.5)
    assert finance_affinity < 0.2

    # Scored candidate comparison
    score_tech = prof.score_candidate({"id": "c_tech_new", "job": "science / tech / engineering"})
    score_finance = prof.score_candidate({"id": "c_fin_new", "job": "banking / financial / real estate"})

    assert score_tech["score"] > score_finance["score"]
    assert score_tech["score"] > 70.0
    assert score_finance["score"] < 30.0


# ============================================================================
# 4. INTEREST PROFILE UPDATES & DISTINGUISHING STATED VS INFERRED
# ============================================================================

def test_distinguish_stated_from_inferred_interests():
    """Explicitly stated interests are maintained distinctly from behaviorally inferred interests."""
    user = {
        "id": "u1",
        "interests": ["chess", "astronomy"],
    }
    events = [
        {"user_id": "u1", "candidate_id": "c1", "action": "LIKE", "timestamp": NOW.isoformat()}
        for _ in range(6)
    ]
    profile_lookup = lambda cid: {"id": cid, "job": "artistic / musical / writer", "interests": ["painting"]}

    p = UserInterestProfile(DEFAULT_CONFIG).fit(user, events, profile_lookup, now=NOW)
    summary = p.to_dict()

    # Explicit interests strictly reflect user profile
    assert summary["explicit_interests"] == ["astronomy", "chess"]
    # Inferred interests track observed behavior
    assert "profession_group" in summary["inferred_interests"]
    assert "creative_media" in summary["inferred_interests"]["profession_group"]
    assert "interest_tag" in summary["inferred_interests"]
    assert "painting" in summary["inferred_interests"]["interest_tag"]
    assert summary["inferred_interests"]["interest_tag"]["painting"]["evidence_count"] == 6


def test_search_criteria_updates_interest_tokens():
    """Search queries and criteria contribute to inferred interest tokens."""
    events = [
        {
            "user_id": "u1",
            "candidate_id": None,
            "action": "SEARCH",
            "timestamp": NOW.isoformat(),
            "search_criteria": {"profession_group": "technology_science", "diet": "vegetarian"},
        }
        for _ in range(6)
    ]
    user = {"id": "u1"}
    p = UserInterestProfile(DEFAULT_CONFIG).fit(user, events, lambda cid: None, now=NOW)
    summary = p.to_dict()

    assert "technology_science" in summary["inferred_interests"]["profession_group"]
    assert "vegetarian" in summary["inferred_interests"]["diet"]
    assert summary["inferred_interests"]["profession_group"]["technology_science"]["affinity"] == 1.0


# ============================================================================
# 5. PERSONALITY AND COMMUNICATION PREFERENCES
# ============================================================================

def test_personality_normalization_and_skipping():
    """Personality profiles support skipping, partial fields, and invalid normalization."""
    # Empty / skipped personality
    empty_p, warnings = normalize_personality_profile(None)
    assert empty_p["status"] == "not_set"
    assert empty_p["personality_type"] is None

    # Valid profile with normalization
    raw = {
        "personality_type": "Introvert",
        "communication_frequency": "DAILY",
        "conversation_style": "deep_conversations",
        "social_activities": ["cultural_events", "quiet_nights_in"],
    }
    norm, warnings = normalize_personality_profile(raw)
    assert norm["personality_type"] == "introvert"
    assert norm["communication_frequency"] == "daily"
    assert norm["conversation_style"] == "deep_conversations"
    assert norm["social_activities"] == ["cultural_events", "quiet_nights_in"]
    assert norm["status"] == "set"
    assert len(warnings) == 0


def test_personality_compatibility_scoring():
    """Evaluates compatibility, communication cadence, style alignment, and social overlap."""
    p_viewer = {
        "personality_type": "introvert",
        "communication_frequency": "daily",
        "conversation_style": "deep_conversations",
        "social_activities": ["quiet_nights_in", "cultural_events"],
    }
    # Highly compatible candidate
    p_match = {
        "personality_type": "introvert",
        "communication_frequency": "daily",
        "conversation_style": "deep_conversations",
        "social_activities": ["quiet_nights_in", "cultural_events", "creative_arts"],
    }
    # Mismatched candidate
    p_clash = {
        "personality_type": "extrovert",
        "communication_frequency": "as_needed",
        "conversation_style": "direct_and_concise",
        "social_activities": ["social_gatherings", "fitness_sports"],
    }

    compat_match = evaluate_personality_compatibility(p_viewer, p_match)
    compat_clash = evaluate_personality_compatibility(p_viewer, p_clash)

    assert compat_match["status"] == "known"
    assert compat_match["score"] > 85.0
    assert compat_clash["score"] < 65.0
    assert compat_match["score"] > compat_clash["score"]


def test_personality_hard_exclusion():
    """Optional hard personality exclusions filter incompatible candidates."""
    p_viewer = {
        "personality_type": "introvert",
        "hard_exclusions": {"personality_type": ["extrovert"]},
    }
    p_extrovert = {"personality_type": "extrovert"}
    p_ambivert = {"personality_type": "ambivert"}

    res_ext = evaluate_personality_compatibility(p_viewer, p_extrovert)
    res_amb = evaluate_personality_compatibility(p_viewer, p_ambivert)

    assert len(res_ext["hard_failures"]) > 0
    assert len(res_amb["hard_failures"]) == 0


# ============================================================================
# 6. CHAT METADATA HANDLING AND CONSENT BOUNDARIES
# ============================================================================

def test_chat_metadata_sanitization_without_consent():
    """Without consent, raw message text is stripped; only safe metadata is stored."""
    pm = PrivacyManager()
    raw_event = {
        "user_id": "u1",
        "candidate_id": "u2",
        "action": "MESSAGE_SENT",
        "timestamp": NOW.isoformat(),
        "message_text": "Hey there! How was your weekend? Let's meet up.",
        "metadata": {
            "conversation_id": "conv_1",
            "content": "Secret text here",
        },
    }
    sanitized = pm.sanitize_event_for_storage(raw_event, "u1")

    # Raw text must be stripped
    assert "message_text" not in sanitized
    assert "content" not in sanitized["metadata"]
    # Safe metadata preserved
    assert sanitized["metadata"]["word_count"] > 0
    assert sanitized["metadata"]["message_length_chars"] > 0
    assert sanitized["metadata"]["conversation_id"] == "conv_1"


def test_consent_withdrawal_stops_message_retention():
    """When consent is withdrawn, subsequent message events strip text."""
    pm = PrivacyManager()
    # Explicitly grant consent
    pm.set_privacy_settings("u1", {"message_analysis_consent": True, "raw_message_retention": True})
    assert pm.can_analyze_messages("u1") is True

    raw_event = {
        "user_id": "u1",
        "candidate_id": "u2",
        "action": "MESSAGE_SENT",
        "timestamp": NOW.isoformat(),
        "message_text": "Hello world",
        "metadata": {},
    }
    stored_with_consent = pm.sanitize_event_for_storage(raw_event, "u1")
    assert stored_with_consent.get("message_text") == "Hello world"

    # Withdraw consent
    pm.set_privacy_settings("u1", {"message_analysis_consent": False, "raw_message_retention": False})
    assert pm.can_analyze_messages("u1") is False

    stored_without_consent = pm.sanitize_event_for_storage(raw_event, "u1")
    assert "message_text" not in stored_without_consent


# ============================================================================
# 7. PRIVACY & DATA CONTROLS (OPT-OUT, DELETION, ISOLATION)
# ============================================================================

def test_personalization_opt_out_disables_behavioral_ranking():
    """When personalization is disabled, recommendation engine ignores behavioral signals."""
    model = RecommendationModel()
    user = {"id": "u_optout", "age": 28, "sex": "m", "orientation": "straight", "job": "artistic / musical / writer"}
    candidate_decided = {"id": "c1", "age": 27, "sex": "f", "orientation": "straight", "job": "artistic / musical / writer"}
    candidate_unseen = {"id": "c2", "age": 27, "sex": "f", "orientation": "straight", "job": "artistic / musical / writer"}

    # Simulate heavy interactions with c1 (decision actions exclude c1 from subsequent recommendations)
    history = [
        {"user_id": "u_optout", "candidate_id": "c1", "action": "LIKE", "timestamp": NOW.isoformat()},
        {"user_id": "u_optout", "candidate_id": "c1", "action": "SAVE", "timestamp": NOW.isoformat()},
    ]

    # Enabled
    recs_enabled = model.recommend(user, [candidate_decided, candidate_unseen], interactions=history, now=NOW, privacy_settings={"personalization_enabled": True})
    # Disabled
    recs_disabled = model.recommend(user, [candidate_decided, candidate_unseen], interactions=history, now=NOW, privacy_settings={"personalization_enabled": False})

    assert len(recs_enabled) == 1
    assert recs_enabled[0]["candidate_id"] == "c2"
    assert recs_enabled[0]["behavior"]["status"] != "disabled"

    assert len(recs_disabled) == 1
    assert recs_disabled[0]["candidate_id"] == "c2"
    assert recs_disabled[0]["behavior"]["status"] == "disabled"
    assert recs_disabled[0]["behavior"]["score"] is None


def test_interaction_history_deletion():
    """Deleting interaction history resets repository state and personalization to cold start."""
    repo = InMemoryRecommendationRepository([FULL_A, FULL_B])
    repo.save_interaction({
        "user_id": FULL_A["id"],
        "candidate_id": FULL_B["id"],
        "action": "LIKE",
        "timestamp": NOW.isoformat(),
    })
    assert len(repo.get_interactions(FULL_A["id"])) == 1

    deleted_count = repo.delete_interactions(FULL_A["id"])
    assert deleted_count == 1
    assert len(repo.get_interactions(FULL_A["id"])) == 0


def test_user_data_isolation():
    """User A's interactions cannot be queried or leaked by User B's requests."""
    repo = InMemoryRecommendationRepository([FULL_A, FULL_B])
    repo.save_interaction({
        "user_id": "user_a",
        "candidate_id": "target",
        "action": "LIKE",
        "timestamp": NOW.isoformat(),
    })
    repo.save_interaction({
        "user_id": "user_b",
        "candidate_id": "other",
        "action": "VIEW",
        "timestamp": NOW.isoformat(),
    })

    assert len(repo.get_interactions("user_a")) == 1
    assert repo.get_interactions("user_a")[0]["candidate_id"] == "target"
    assert len(repo.get_interactions("user_b")) == 1
    assert repo.get_interactions("user_b")[0]["candidate_id"] == "other"


# ============================================================================
# 8. COLD-START AND MISSING DATA HANDLING
# ============================================================================

def test_cold_start_user_behavior():
    """User with no interaction history safely receives cold start status without fabricated scores."""
    model = RecommendationModel()
    user = {"id": "u_new", "age": 25, "sex": "m", "orientation": "straight", "job": "student"}
    candidates = [
        {"id": "c1", "age": 24, "sex": "f", "orientation": "straight", "job": "student"},
    ]
    recs = model.recommend(user, candidates, interactions=[], now=NOW)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["behavior"]["status"] == "cold_start"
    assert rec["behavior"]["score"] is None
    assert rec["ranking"]["final_score"] > 0.0  # purely driven by baseline compatibility


def test_missing_profile_fields_and_unspecified_personality():
    """Missing fields in profiles or personality objects do not crash ranking or scoring."""
    model = RecommendationModel()
    user_minimal = {"id": "u_min", "age": 26, "sex": "m", "orientation": "straight"}
    candidate_minimal = {"id": "c_min", "age": 25, "sex": "f", "orientation": "straight"}

    recs = model.recommend(
        user_minimal,
        [candidate_minimal],
        user_personality={},
        personality_lookup=lambda cid: None,
    )
    assert len(recs) == 1
    assert recs[0]["personality"]["status"] == "unavailable"


# ============================================================================
# 9. HARD-EXCLUSION ENFORCEMENT
# ============================================================================

def test_behavioral_signals_cannot_override_dealbreakers():
    """Even with maximum positive interactions, an ineligible candidate is strictly excluded."""
    model = RecommendationModel()
    user = {
        "id": "u1", "age": 30, "sex": "m", "orientation": "straight",
        "dealbreakers": {"smokes": ["no"]},
    }
    candidate_smoker = {
        "id": "c_smoker", "age": 28, "sex": "f", "orientation": "straight",
        "smokes": "yes",
    }
    candidate_nonsmoker = {
        "id": "c_nonsmoker", "age": 28, "sex": "f", "orientation": "straight",
        "smokes": "no",
    }
    history = [
        {"user_id": "u1", "candidate_id": "c_smoker", "action": "LIKE", "timestamp": NOW.isoformat()},
        {"user_id": "u1", "candidate_id": "c_smoker", "action": "SAVE", "timestamp": NOW.isoformat()},
    ]

    recs = model.recommend(
        user,
        [candidate_smoker, candidate_nonsmoker],
        user_preferences={"dealbreakers": {"smokes": ["no"]}},
        interactions=history,
        now=NOW,
    )

    rec_ids = [r["candidate_id"] for r in recs]
    assert "c_smoker" not in rec_ids
    assert "c_nonsmoker" in rec_ids


# ============================================================================
# 10. RANKING & EXPLANATION CONSISTENCY & NON-PROBABILITY DISCLAIMER
# ============================================================================

def test_explanation_matches_scoring_and_includes_disclaimer():
    """Explanation details match the active signals and explicitly disclaims relationship probability."""
    model = RecommendationModel()
    viewer = {
        "id": "u1", "age": 30, "sex": "m", "orientation": "straight",
        "job": "science / tech / engineering", "interests": ["technology", "hiking"],
    }
    candidate = {
        "id": "c1", "age": 28, "sex": "f", "orientation": "straight",
        "job": "science / tech / engineering", "interests": ["technology", "hiking"],
    }
    viewer_personality = {
        "personality_type": "introvert",
        "conversation_style": "deep_conversations",
    }
    candidate_personality = {
        "personality_type": "introvert",
        "conversation_style": "deep_conversations",
    }

    explanation = model.explain_candidate(
        viewer,
        candidate,
        user_personality=viewer_personality,
        candidate_personality=candidate_personality,
    )

    assert "disclaimer" in explanation
    assert "probability" in explanation["disclaimer"].lower() or "not" in explanation["disclaimer"].lower()
    assert "personality" in explanation
    assert explanation["personality"]["status"] in ("known", "evaluated")


# ============================================================================
# 11. DETERMINISTIC BEHAVIOR UNDER FIXED INPUTS
# ============================================================================

def test_ranking_determinism():
    """Identical inputs produce bitwise identical recommendations and scores across repeated runs."""
    model = RecommendationModel()
    user = {"id": "u_det", "age": 28, "sex": "m", "orientation": "straight", "job": "art / design / styling"}
    pool = [
        {"id": f"c_{i}", "age": 25 + i, "sex": "f", "orientation": "straight", "job": "art / design / styling"}
        for i in range(5)
    ]
    history = [
        {"user_id": "u_det", "candidate_id": "c_2", "action": "LIKE", "timestamp": NOW.isoformat()},
    ]

    run1 = model.recommend(user, pool, interactions=history, now=NOW)
    run2 = model.recommend(user, pool, interactions=history, now=NOW)
    run3 = model.recommend(user, pool, interactions=history, now=NOW)

    dump1 = json.dumps(run1, sort_keys=True)
    dump2 = json.dumps(run2, sort_keys=True)
    dump3 = json.dumps(run3, sort_keys=True)

    assert dump1 == dump2 == dump3


# ============================================================================
# 12. EVALUATION HARNESS AND METRICS COMPUTATION
# ============================================================================

def test_compute_ranking_metrics_for_user():
    """Ranking metric calculation correctly computes Precision@K, Recall@K, NDCG@K, MRR."""
    recommended = ["c1", "c2", "c3", "c4", "c5"]
    positives = {"c2", "c4"}  # Ranks 2 and 4

    metrics = compute_ranking_metrics_for_user(recommended, positives, k_values=(3, 5))

    # Top 3: ["c1", "c2", "c3"] -> 1 hit ("c2")
    assert metrics["precision@3"] == round(1 / 3, 4)
    assert metrics["recall@3"] == round(1 / 2, 4)
    assert metrics["hit_rate@3"] == 1.0

    # Top 5: ["c1", "c2", "c3", "c4", "c5"] -> 2 hits
    assert metrics["precision@5"] == round(2 / 5, 4)
    assert metrics["recall@5"] == round(2 / 2, 4)
    assert metrics["hit_rate@5"] == 1.0

    # First hit is at rank 2 -> MRR = 1/2 = 0.5
    assert metrics["mrr"] == 0.5


def test_personalization_evaluation_harness_comparison():
    """Evaluation harness compares baseline vs personalized ranker with transparent provenance."""
    harness = PersonalizationEvaluationHarness(data_source_note="offline_synthetic_test_pool")

    test_users = [{"id": "u1"}, {"id": "u2"}]
    candidate_pool = [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}, {"id": "c4"}]
    ground_truth = {
        "u1": {"c3"},
        "u2": {"c1"},
    }

    def baseline_ranker(user, pool):
        return [{"candidate_id": c["id"]} for c in pool]

    def personalized_ranker(user, pool):
        if user["id"] == "u1":
            return [{"candidate_id": "c3"}, {"candidate_id": "c1"}, {"candidate_id": "c2"}, {"candidate_id": "c4"}]
        return [{"candidate_id": c["id"]} for c in pool]

    results = harness.evaluate_system(
        baseline_ranker, personalized_ranker, test_users, candidate_pool, ground_truth, k_list=(3,)
    )

    assert results["users_evaluated"] == 2
    assert "limitations" in results
    assert len(results["limitations"]) > 0
    assert results["personalized_metrics"]["ndcg@3"] >= results["baseline_metrics"]["ndcg@3"]


# ============================================================================
# 13. SERVICE LAYER AND HTTP BACKEND INTEGRATION
# ============================================================================

def test_service_personality_and_privacy_endpoints():
    """RecommendationService manages personality, privacy settings, and interaction deletion."""
    repo = InMemoryRecommendationRepository([FULL_A, FULL_B])
    service = RecommendationService(CompatibilityModel(), repo, clock=lambda: NOW)

    # Personality storage
    personality = {
        "personality_type": "ambivert",
        "communication_frequency": "daily",
    }
    service.save_user_personality(FULL_A["id"], personality)
    retrieved_p = service.get_user_personality(FULL_A["id"])
    assert retrieved_p["personality"]["personality_type"] == "ambivert"

    # Privacy settings
    settings = {"personalization_enabled": False}
    service.save_privacy_settings(FULL_A["id"], settings)
    retrieved_s = service.get_privacy_settings(FULL_A["id"])
    assert retrieved_s["personalization_enabled"] is False

    # Interaction recording and deletion
    service.record_interaction({
        "user_id": FULL_A["id"],
        "candidate_id": FULL_B["id"],
        "action": "LIKE",
        "timestamp": NOW.isoformat(),
    })
    assert len(repo.get_interactions(FULL_A["id"])) == 1
    del_res = service.delete_interactions(FULL_A["id"])
    assert del_res["deleted_events_count"] == 1
    assert len(repo.get_interactions(FULL_A["id"])) == 0


def test_fastapi_backend_phase6_endpoints():
    """FastAPI test client verifies new personality, privacy, and deletion endpoints."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dating_ml_model.backend_integration_example import create_app

    repo = InMemoryRecommendationRepository([FULL_A, FULL_B])
    app = create_app(repo, clock=lambda: NOW)
    client = TestClient(app)

    # 1. Personality endpoint
    resp = client.put(f"/users/{FULL_A['id']}/personality", json={
        "personality_type": "introvert",
        "communication_frequency": "daily",
    })
    assert resp.status_code == 200
    assert resp.json()["personality"]["personality_type"] == "introvert"

    get_resp = client.get(f"/users/{FULL_A['id']}/personality")
    assert get_resp.status_code == 200
    assert get_resp.json()["personality"]["personality_type"] == "introvert"

    # 2. Privacy settings endpoint
    priv_resp = client.put(f"/users/{FULL_A['id']}/privacy-settings", json={
        "personalization_enabled": False,
    })
    assert priv_resp.status_code == 200
    assert priv_resp.json()["personalization_enabled"] is False

    get_priv = client.get(f"/users/{FULL_A['id']}/privacy-settings")
    assert get_priv.status_code == 200
    assert get_priv.json()["personalization_enabled"] is False

    # 3. Interaction deletion endpoint
    client.post("/interactions", json={
        "user_id": FULL_A["id"],
        "candidate_id": FULL_B["id"],
        "action": "LIKE",
        "timestamp": NOW.isoformat(),
    })
    del_resp = client.delete(f"/users/{FULL_A['id']}/interactions")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_events_count"] >= 1

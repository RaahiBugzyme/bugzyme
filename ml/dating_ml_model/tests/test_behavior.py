import copy
from datetime import timedelta

import pytest

from dating_ml_model import RecommendationModel
from dating_ml_model import behavior as B
from dating_ml_model.personalization import UserPreferenceModel
from dating_ml_model.tests.reco_fixtures import HEALTH, NOW, TECH, man, woman

M = RecommendationModel()
CFG = M.config
USER = woman("u", age=30, city="Pune", state="Maharashtra", country="India", height=65)


def event(cand, action, days_ago=1.0, user="u"):
    return {"user_id": user, "candidate_id": cand, "action": action, "timestamp": (NOW - timedelta(days=days_ago)).isoformat() + "Z"}


def candidates(n, job=TECH, prefix="c", **kw):
    return {f"{prefix}{i}": man(f"{prefix}{i}", job=job, **kw) for i in range(n)}


def fit(events, profiles, cfg=CFG):
    return UserPreferenceModel(cfg).fit(USER, events, profiles.get, NOW)


def summary(events, cfg=CFG):
    return B.summarize_behavior(events, "u", cfg, NOW)


# ---- event schema ---------------------------------------------------------------------------------
def test_event_validation():
    ok = B.validate_event({"user_id": 1, "candidate_id": 2, "action": "like", "timestamp": "2026-01-01T00:00:00+05:30", "source": "feed"})
    assert ok["action"] == "LIKE" and ok["timestamp"] == "2025-12-31T18:30:00Z" and ok["user_id"] == "1"
    for bad in ({"candidate_id": 2, "action": "LIKE", "timestamp": NOW}, {"user_id": 1, "candidate_id": 1, "action": "LIKE", "timestamp": NOW},
                {"user_id": 1, "candidate_id": 2, "action": "HUG", "timestamp": NOW}, {"user_id": 1, "candidate_id": 2, "action": "LIKE"},
                {"user_id": 1, "candidate_id": 2, "action": "LIKE", "timestamp": "yesterday"}):
        with pytest.raises(ValueError):
            B.validate_event(bad)
    assert set(B.SUPPORTED_ACTIONS) >= {"VIEW", "LIKE", "PASS", "MATCH"}


@pytest.mark.parametrize("action", B.SUPPORTED_ACTIONS)
def test_event_contract_covers_every_action(action):
    contract = B.EVENT_CONTRACT[action]
    assert set(contract) == {"requires_candidate_id", "requires_search_metadata",
                             "contributes_to_personalization", "counts_toward_behavioral_summary",
                             "excludes_candidate", "changes_relationship_state"}


def test_search_event_uses_event_type_without_candidate_id():
    out = B.validate_event({
        "user_id": "u", "event_type": "search", "timestamp": "2026-10-01T00:00:00Z",
        "search_criteria": {"max_distance_km": 25, "relationship_intention": ["long_term"]},
    })
    assert out["action"] == out["event_type"] == "SEARCH"
    assert out["candidate_id"] is None
    assert out["search_criteria"] == {"max_distance_km": 25, "relationship_intention": ["long_term"]}


def test_search_event_allows_partially_specified_or_null_criteria():
    partial = B.validate_event({"user_id": "u", "event_type": "SEARCH", "timestamp": "2026-10-01T00:00:00Z",
                                "search_criteria": {"max_distance_km": None, "age": {"min": 25}}})
    empty = B.validate_event({"user_id": "u", "action": "SEARCH", "timestamp": "2026-10-01T00:00:01Z",
                              "search_criteria": None})
    assert partial["search_criteria"]["max_distance_km"] is None
    assert empty["search_criteria"] is None


@pytest.mark.parametrize("event", [
    {"user_id": "u", "action": "LIKE", "timestamp": "2026-10-01T00:00:00Z"},
    {"user_id": "u", "candidate_id": None, "action": "MESSAGE", "timestamp": "2026-10-01T00:00:00Z"},
    {"user_id": "u", "candidate_id": "c", "action": "LIKE", "event_type": "PASS",
     "timestamp": "2026-10-01T00:00:00Z"},
    {"user_id": "u", "event_type": "SEARCH", "timestamp": "2026-10-01T00:00:00Z",
     "search_criteria": []},
    {"user_id": None, "candidate_id": "c", "action": "LIKE", "timestamp": "2026-10-01T00:00:00Z"},
    {"user_id": "u", "candidate_id": "c", "action": "LIKE", "timestamp": None},
])
def test_invalid_event_contract_inputs_are_rejected(event):
    with pytest.raises(ValueError):
        B.validate_event(event)


def test_search_is_counted_but_does_not_become_decision_evidence():
    s = summary([{"user_id": "u", "event_type": "SEARCH", "timestamp": NOW.isoformat() + "Z"}])
    assert s["total_searches"] == 1
    assert s["evidence_count"] == 0


def test_usable_events_are_chronological():
    events = [
        {"user_id": "u", "candidate_id": "b", "action": "VIEW", "timestamp": "2026-10-03T00:00:00Z"},
        {"user_id": "u", "event_type": "SEARCH", "timestamp": "2026-10-01T00:00:00Z"},
        {"user_id": "u", "candidate_id": "a", "action": "VIEW", "timestamp": "2026-10-02T00:00:00Z"},
    ]
    kept, _ = B.usable_events(events, "u", NOW + timedelta(days=3))
    assert [event["action"] for event in kept] == ["SEARCH", "VIEW", "VIEW"]


# ---- VIEW / LIKE / PASS / MATCH counting + rates --------------------------------------------------------
def test_counts_and_rates():
    events = [event("a", "VIEW"), event("a", "LIKE"), event("b", "VIEW"), event("b", "PASS"), event("c", "LIKE"),
              event("c", "MATCH"), event("d", "SUPER_LIKE"), event("e", "SAVE"), event("f", "MESSAGE")]
    s = summary(events)
    assert (s["total_views"], s["total_likes"], s["total_super_likes"], s["total_passes"], s["total_matches"]) == (2, 3, 1, 1, 1)
    assert s["like_rate"] == 0.75 and s["pass_rate"] == 0.25 and s["match_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert s["other_event_counts"] == {"MESSAGE": 1} or s["other_event_counts"] == {"SAVE": 1, "MESSAGE": 1}
    assert s["evidence_count"] == 4                                       # a,b,c,d decided; VIEW/MATCH/SAVE are not decisions


def test_other_users_events_are_ignored():
    assert summary([event("a", "LIKE", user="someone_else")])["total_events"] == 0


# ---- evidence thresholds / status ------------------------------------------------------------------------
def test_zero_interactions_is_cold_start():
    s = summary([])
    assert (s["behavior_status"], s["behavior_confidence"], s["evidence_count"], s["like_rate"]) == ("cold_start", 0.0, 0, None)


def test_views_only_is_still_cold_start():
    assert summary([event("a", "VIEW"), event("b", "VIEW")])["behavior_status"] == "cold_start"


@pytest.mark.parametrize("n", [1, 2, 9])
def test_few_interactions_are_insufficient(n):
    s = summary([event(f"c{i}", "LIKE") for i in range(n)])
    assert s["behavior_status"] == "insufficient_data" and 0 < s["behavior_confidence"] < 50


def test_minimum_threshold_activates_sufficient_data():
    assert summary([event(f"c{i}", "LIKE") for i in range(10)])["behavior_status"] == "sufficient_data"
    cfg = copy.deepcopy(CFG)
    cfg["min_behavior_events"] = 4
    assert summary([event(f"c{i}", "LIKE") for i in range(4)], cfg)["behavior_status"] == "sufficient_data"


def test_confidence_grows_gradually_with_evidence():
    confs = [summary([event(f"c{i}", "LIKE", 0.1) for i in range(n)])["behavior_confidence"] for n in (1, 5, 10, 50, 500)]
    assert confs == sorted(confs) and confs[0] < 10 and confs[-1] > 90


def test_behavior_can_be_disabled():
    cfg = copy.deepcopy(CFG)
    cfg["behavior_enabled"] = False
    assert summary([event(f"c{i}", "LIKE") for i in range(20)], cfg)["behavior_status"] == "disabled"


# ---- recency ---------------------------------------------------------------------------------------------------
def test_recency_weight_half_life_and_decay_options():
    assert B.recency_weight(0, CFG) == 1 and B.recency_weight(30, CFG) == pytest.approx(0.5) and B.recency_weight(60, CFG) == pytest.approx(0.25)
    cfg = copy.deepcopy(CFG)
    cfg["behavior_decay"] = 0.9
    assert B.recency_weight(2, cfg) == pytest.approx(0.81)


def test_recent_evidence_counts_more_than_old_evidence():
    recent = summary([event(f"c{i}", "LIKE", 1) for i in range(10)])
    old = summary([event(f"c{i}", "LIKE", 300) for i in range(10)])
    assert recent["weighted_evidence"] > 9 and old["weighted_evidence"] < 0.1 and recent["behavior_confidence"] > old["behavior_confidence"]
    assert summary([event("a", "LIKE", 2)])["recent_events"] == 1 and summary([event("a", "LIKE", 100)])["recent_events"] == 0


def test_future_events_are_ignored_no_leakage():
    s = summary([event(f"c{i}", "LIKE", -5) for i in range(12)] + [event("old", "LIKE", 1)])
    assert s["evidence_count"] == 1 and s["ignored_future_events"] == 12


# ---- learning from profile FEATURES (not IDs) ----------------------------------------------------------------------
def planted_log(n_tech=8, n_health=8, tech_action="LIKE", health_action="PASS", tech_days=1.0, health_days=1.0):
    profiles = {**candidates(n_tech, TECH, "t"), **candidates(n_health, HEALTH, "h")}
    events = [event(f"t{i}", tech_action, tech_days) for i in range(n_tech)] + [event(f"h{i}", health_action, health_days) for i in range(n_health)]
    return profiles, events


def test_learns_profession_group_preference_from_features():
    profiles, events = planted_log()
    model = fit(events, profiles)
    learned = model.learned_preferences()["profession_group"]
    assert learned["technology_science"]["preference"] > 0.5 > learned["health_education"]["preference"]
    assert learned["technology_science"]["evidence_count"] == 8
    for entry in learned.values():
        assert set(entry) == {"preference", "confidence", "evidence_count", "weighted_evidence", "last_updated"}
    new_tech, new_health = man("new_t"), man("new_h", job=HEALTH)                       # NEW people the user has never seen
    assert model.score_candidate(USER, new_tech)["score"] > model.score_candidate(USER, new_health)["score"]


def test_repeated_like_does_not_inflate_evidence():
    profiles = candidates(1)
    model = fit([event("c0", "LIKE", d) for d in (5, 4, 3, 2, 1)], profiles)
    assert model.summary["evidence_count"] == 1 and model.summary["total_likes"] == 5 and model.summary["behavior_status"] == "insufficient_data"


def test_repeated_pass_only_user_gets_low_scores_and_no_overclaim():
    profiles = candidates(12)
    model = fit([event(f"c{i}", "PASS") for i in range(12)], profiles)
    out = model.score_candidate(USER, man("x"))
    assert out["status"] == "sufficient_data" and out["score"] < 30 and model.overall_like_rate == 0


def test_repeated_like_only_user():
    profiles = candidates(12)
    model = fit([event(f"c{i}", "LIKE") for i in range(12)], profiles)
    assert model.score_candidate(USER, man("x"))["score"] > 70


def test_latest_decision_wins_when_a_user_changes_their_mind():
    profiles = candidates(1)
    assert B.latest_decisions(B.usable_events([event("c0", "LIKE", 5), event("c0", "PASS", 1)], "u", NOW)[0])["c0"]["action"] == "PASS"


def test_mixed_and_conflicting_signals_stay_near_baseline_with_low_confidence():
    profiles = {**candidates(5, TECH, "tl"), **candidates(5, TECH, "tp")}
    events = [event(f"tl{i}", "LIKE") for i in range(5)] + [event(f"tp{i}", "PASS") for i in range(5)]
    model = fit(events, profiles)
    pref = model.learned_preferences()["profession_group"]["technology_science"]["preference"]
    assert pref == pytest.approx(0.5, abs=0.05) and model.overall_like_rate == pytest.approx(0.5)
    assert model.score_candidate(USER, man("x"))["score"] == pytest.approx(50, abs=5)


def test_low_evidence_value_is_shrunk_toward_users_baseline():
    profiles = {**candidates(10, TECH, "t"), "single": man("single", job=HEALTH)}
    events = [event(f"t{i}", "PASS") for i in range(10)] + [event("single", "LIKE")]
    entry = fit(events, profiles).learned_preferences()["profession_group"]["health_education"]
    assert entry["evidence_count"] == 1 and entry["confidence"] < 0.2 and entry["preference"] < 0.9      # one like is not a strong preference


def test_old_likes_vs_recent_likes_change_what_is_learned():
    p1, e1 = planted_log(tech_action="PASS", tech_days=1, health_action="LIKE", health_days=300)     # recently passes tech, old likes health
    p2, e2 = planted_log(tech_action="PASS", tech_days=300, health_action="LIKE", health_days=1)     # old passes tech, recent likes health
    t1 = fit(e1, p1).learned_preferences()["profession_group"]["technology_science"]
    t2 = fit(e2, p2).learned_preferences()["profession_group"]["technology_science"]
    assert t1["weighted_evidence"] > 10 * t2["weighted_evidence"]


def test_decisions_with_missing_candidate_profile_are_skipped_not_guessed():
    profiles = candidates(10)
    events = [event(f"c{i}", "LIKE") for i in range(10)] + [event("ghost", "PASS")]
    model = fit(events, profiles)
    assert model.skipped_missing_profile == 1 and model.summary["evidence_count"] == 11


def test_missing_profile_attributes_do_not_create_tokens():
    profiles = {f"c{i}": {"id": f"c{i}", "age": 30, "sex": "m", "orientation": "straight"} for i in range(10)}      # sparse candidates
    model = fit([event(f"c{i}", "LIKE") for i in range(10)], profiles)
    assert set(model.learned_preferences()) <= {"age_difference", "generation"}             # only what is actually known
    assert model.score_candidate(USER, {"id": "x"})["status"] == "no_applicable_evidence"
    assert model.score_candidate(USER, {"id": "x"})["score"] is None


def test_no_strong_claims_below_threshold():
    profiles, events = planted_log(n_tech=2, n_health=0)
    model = fit(events, profiles)
    out = model.score_candidate(USER, man("x"))
    assert out["status"] == "insufficient_data" and out["score"] is None
    assert model.to_dict()["learned_preferences"] == {} and "evidence" in model.to_dict()["note"]
    assert fit([], {}).score_candidate(USER, man("x")) == {"score": None, "confidence": 0.0, "status": "cold_start", "evidence_count": 0, "supporting_features": []}


# ---- cold start and gradual personalization in the full pipeline -------------------------------------------------------
def test_cold_start_pipeline_uses_profile_preferences_and_location_only():
    u = woman("u", city="Pune", state="Maharashtra", country="India", age=30)
    recs = M.recommend(u, [man("a", city="Pune", state="Maharashtra", country="India"), man("b", job=HEALTH)],
                       user_preferences={"criteria": {"profession_group": {"values": ["technology_science"]}}}, interactions=[], now=NOW)
    assert len(recs) == 2
    for r in recs:
        assert r["behavior"]["status"] == "cold_start" and r["behavior"]["score"] is None and r["behavior"]["confidence"] == 0
        assert r["mutual_interest"]["probability"] is None and r["mutual_interest"]["status"] == "insufficient_behavioral_data"
        assert {c["signal"] for c in r["ranking"]["components"] if c["used"]} <= {"compatibility", "location", "preferences", "relationship_intention"}
    assert recs[0]["candidate_id"] == "a"


@pytest.mark.parametrize("n,status,uses_behavior", [(0, "cold_start", False), (1, "insufficient_data", False), (2, "insufficient_data", False),
                                                    (10, "sufficient_data", True), (40, "sufficient_data", True)])
def test_behavior_activates_gradually_and_never_dominates(n, status, uses_behavior):
    profiles = {**candidates(n, TECH, "t"), "new": man("new")}
    events = [event(f"t{i}", "LIKE") for i in range(n)]
    rec = M.recommend(USER, list(profiles.values()), interactions=events, profile_lookup=profiles.get, now=NOW, limit=50)
    new = next(r for r in rec if r["candidate_id"] == "new")
    assert new["behavior"]["status"] == status
    comps = {c["signal"]: c for c in new["ranking"]["components"]}
    assert comps["behavior"]["used"] is uses_behavior
    if uses_behavior:
        assert comps["behavior"]["effective_weight"] < comps["behavior"]["base_weight"] <= 0.5 * comps["compatibility"]["effective_weight"]


def test_behavior_weight_increases_with_more_evidence_but_stays_below_compatibility():
    weights = []
    for n in (10, 30, 200):
        profiles = {**candidates(n, TECH, "t"), "new": man("new")}
        events = [event(f"t{i}", "LIKE", 0.5) for i in range(n)]
        rec = M.recommend(USER, [profiles["new"]], interactions=events, profile_lookup=profiles.get, now=NOW)
        weights.append(next(c["effective_weight"] for c in rec[0]["ranking"]["components"] if c["signal"] == "behavior"))
    assert weights == sorted(weights) and weights[-1] < 0.10 and weights[0] > 0

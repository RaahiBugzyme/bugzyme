"""Regression tests for the interests signal in production ranking.

Verifies that:
- The default config.json contains "interests" weight > 0.
- Google-derived (and manual) interests correctly influence final_score when
  consent is granted and the candidate has matching interest tokens.
- Consent-disabled or missing-interest cases produce neutral (unchanged) results.
- The interests signal never overrides eligibility decisions.
- Ranking order shifts predictably when interests are enabled vs disabled.
- Missing Google interest data does not penalize users (cold-start is neutral).

All providers are mocks (no live Google/Gemini API calls).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pytest

from dating_ml_model import RecommendationModel
from dating_ml_model.interests import UserInterestProfile
from dating_ml_model.model import CompatibilityModel
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService

NOW = datetime(2026, 10, 30, 10, 0, 0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _man(pid: str, **kw) -> Dict[str, Any]:
    base = {
        "id": pid, "age": 30, "sex": "m", "orientation": "straight",
        "job": "science / tech / engineering",
        "education": "graduated from college/university",
        "religion": "agnosticism", "drinks": "socially", "smokes": "no",
        "offspring": "wants kids",
    }
    base.update(kw)
    return base


def _woman(pid: str, **kw) -> Dict[str, Any]:
    return _man(pid, sex="f", **kw)


def _make_service(users, interest_weight: float = 0.05) -> RecommendationService:
    """Build a RecommendationService with an isolated config that sets interests weight explicitly."""
    base_model = RecommendationModel()
    cfg = dict(base_model.config)
    weights = dict(cfg["final_ranking"]["weights"])
    weights["interests"] = interest_weight
    cfg["final_ranking"] = dict(cfg["final_ranking"])
    cfg["final_ranking"]["weights"] = weights
    model = RecommendationModel(config=cfg)
    repo = InMemoryRecommendationRepository(users)
    return RecommendationService(model.compatibility, repo, recommendation_model=model, clock=lambda: NOW)


# ---------------------------------------------------------------------------
# T1-1  Default config.json contains interests weight > 0
# ---------------------------------------------------------------------------

class TestConfigHasInterestsWeight:
    def test_default_config_interests_weight_positive(self):
        model = RecommendationModel()
        weights = model.config["final_ranking"]["weights"]
        assert "interests" in weights, (
            "config.json must include 'interests' under final_ranking.weights"
        )
        assert weights["interests"] > 0, (
            f"interests weight must be > 0, got {weights['interests']}"
        )

    def test_interests_weight_is_consumed_by_combine_signals(self):
        """combine_signals must include an 'interests' component row when signal is present."""
        from dating_ml_model.ranking import combine_signals

        model = RecommendationModel()
        cfg = model.config
        signals = {
            "compatibility": {"score": 70.0, "confidence": None},
            "interests": {"score": 90.0, "confidence": 0.8},
        }
        result = combine_signals(signals, cfg)
        comps = {c["signal"]: c for c in result["components"]}
        assert "interests" in comps
        assert comps["interests"]["used"] is True
        assert comps["interests"]["effective_weight"] > 0

    def test_interests_absent_from_signals_does_not_crash(self):
        """If signals dict has no 'interests' key, combine_signals must still work."""
        from dating_ml_model.ranking import combine_signals

        model = RecommendationModel()
        cfg = model.config
        signals = {"compatibility": {"score": 70.0, "confidence": None}}
        result = combine_signals(signals, cfg)
        assert result["final_score"] is not None


# ---------------------------------------------------------------------------
# T1-2  Google interests shift ranking when consent is granted
# ---------------------------------------------------------------------------

class TestGoogleInterestsShiftRanking:
    """Verify that Google-derived (and manual) interests re-rank eligible candidates."""

    def _setup(self, interest_weight: float = 0.05):
        user = _woman("u_seeker", age=28)
        # cand_match has interests that overlap the user's imported Google interests
        cand_match = _man(
            "c_match", age=29,
            interests=["rock_climbing", "jazz", "hiking"],
        )
        # cand_no_match has completely different interests
        cand_no_match = _man(
            "c_nomatch", age=29,
            interests=["knitting", "pottery"],
        )
        service = _make_service([user, cand_match, cand_no_match], interest_weight)

        # Import Google interests for the seeker
        service.import_external_interests(
            "u_seeker", "google",
            {"items": [
                {"title": "Rock Climbing", "is_topic": True, "confidence": 0.95},
                {"title": "Jazz", "is_topic": True, "confidence": 0.90},
            ]},
            user_confirmed=True,
        )
        return service

    def test_ranking_favours_interest_match_when_consent_granted(self):
        service = self._setup()
        service.set_external_interest_consent("u_seeker", "google", True)

        recs = service.get_recommendations("u_seeker", limit=10)
        assert len(recs) == 2
        ids = [str(r["candidate_id"]) for r in recs]
        assert ids[0] == "c_match", (
            f"c_match should rank first (shared interests) but got {ids}"
        )
        # interests signal must appear and be used
        top = recs[0]
        assert top.get("interests") is not None
        assert top["interests"]["status"] == "known"
        assert top["interests"]["score"] > 50.0
        assert any(
            c["signal"] == "interests" and c["used"]
            for c in top["ranking"]["components"]
        )

    def test_ranking_without_consent_is_unaffected_by_interests(self):
        """Without consent the interests signal must be absent (cold_start / neutral)."""
        service = self._setup()
        # Do NOT grant consent

        recs = service.get_recommendations("u_seeker", limit=10)
        for r in recs:
            assert r.get("interests") is None, (
                "interests signal must not appear without consent"
            )
            assert all(
                not c["used"]
                for c in r["ranking"]["components"]
                if c["signal"] == "interests"
            )

    def test_final_scores_differ_between_consent_and_no_consent(self):
        """The final_score for c_match must be higher when consent is active."""
        service_on = self._setup()
        service_on.set_external_interest_consent("u_seeker", "google", True)

        service_off = self._setup()
        # No consent for service_off

        recs_on = service_on.get_recommendations("u_seeker", limit=10)
        recs_off = service_off.get_recommendations("u_seeker", limit=10)

        score_on = next(
            r["ranking"]["final_score"] for r in recs_on if r["candidate_id"] == "c_match"
        )
        score_off = next(
            r["ranking"]["final_score"] for r in recs_off if r["candidate_id"] == "c_match"
        )
        # When interests are active the matching candidate must score higher
        assert score_on > score_off, (
            f"c_match score with interests={score_on:.4f} should exceed without={score_off:.4f}"
        )

    def test_component_scores_unchanged_by_interests_signal(self):
        """Core compatibility scores must be identical regardless of interest consent."""
        service_on = self._setup()
        service_on.set_external_interest_consent("u_seeker", "google", True)
        service_off = self._setup()

        recs_on = service_on.get_recommendations("u_seeker", limit=10)
        recs_off = service_off.get_recommendations("u_seeker", limit=10)

        for cid in ("c_match", "c_nomatch"):
            sc_on = next(r["compatibility"]["adjusted_score"] for r in recs_on if r["candidate_id"] == cid)
            sc_off = next(r["compatibility"]["adjusted_score"] for r in recs_off if r["candidate_id"] == cid)
            assert sc_on == sc_off, (
                f"compatibility score for {cid} changed: {sc_on} vs {sc_off}"
            )


# ---------------------------------------------------------------------------
# T1-3  Missing Google data is neutral (cold-start)
# ---------------------------------------------------------------------------

class TestMissingGoogleDataIsNeutral:
    def test_no_external_interests_no_penalty(self):
        """A user with no imported external interests must not be penalized in ranking."""
        user = _woman("u_cold", age=28)
        cand = _man("c_warm", age=29, interests=["rock_climbing"])
        service = _make_service([user, cand])
        # No interests imported at all
        service.set_external_interest_consent("u_cold", "google", True)

        recs = service.get_recommendations("u_cold", limit=5)
        assert len(recs) == 1
        r = recs[0]
        # No interests block at all (cold_start path)
        assert r.get("interests") is None
        # final_score must still be computable
        assert r["ranking"]["final_score"] is not None

    def test_cold_start_interest_profile_does_not_contribute_to_ranking(self):
        """Cold-start UserInterestProfile must produce score=None; ranking must ignore it."""
        model = RecommendationModel()
        user = _woman("u_cold2", age=28)
        cand = _man("c_warm2", age=29)
        # Explicitly create a cold-start interest profile
        cold_profile = UserInterestProfile(model.config)
        cold_profile.fit(user, [], lambda _: None, NOW)
        assert cold_profile.status == "cold_start"
        result = cold_profile.score_candidate(cand)
        assert result["score"] is None

        # evaluate_candidate with cold profile must not include interests signal
        rec = model.evaluate_candidate(user, cand, interest_profile=cold_profile)
        assert rec.get("interests") is None
        assert rec["ranking"]["final_score"] is not None


# ---------------------------------------------------------------------------
# T1-4  Interests never override eligibility
# ---------------------------------------------------------------------------

class TestInterestsNeverOverrideEligibility:
    def test_underage_excluded_even_with_100pct_interest_match(self):
        model = RecommendationModel()
        user = _woman("u_g", age=25)
        ext_interests = [
            {"canonical_token": "interest_tag:rock_climbing", "provider": "google",
             "confidence": 1.0, "affinity": 1.0}
        ]
        interest_prof = UserInterestProfile(model.config).fit(
            user, [], lambda _: None, NOW, external_interests=ext_interests
        )
        cand_minor = _man("c_minor", age=16, interests=["rock_climbing"])
        rec = model.evaluate_candidate(user, cand_minor, interest_profile=interest_prof)
        assert rec["eligibility"]["eligible"] is False
        assert rec["ranking"]["final_score"] is None

    def test_orientation_mismatch_excluded_even_with_interest_match(self):
        model = RecommendationModel()
        user = _woman("u_straight", age=25, orientation="straight")
        ext_interests = [
            {"canonical_token": "interest_tag:hiking", "provider": "google",
             "confidence": 1.0, "affinity": 1.0}
        ]
        interest_prof = UserInterestProfile(model.config).fit(
            user, [], lambda _: None, NOW, external_interests=ext_interests
        )
        cand_gay = _man("c_gay", age=25, orientation="gay", interests=["hiking"])
        rec = model.evaluate_candidate(user, cand_gay, interest_profile=interest_prof)
        assert rec["eligibility"]["eligible"] is False
        assert rec["ranking"]["final_score"] is None


# ---------------------------------------------------------------------------
# T1-5  Consent revocation immediately disables the signal
# ---------------------------------------------------------------------------

class TestConsentRevocationDisablesSignal:
    def test_revoke_stops_interests_from_influencing_ranking(self):
        user = _woman("u_rev", age=28)
        cand = _man("c_rev_cand", age=29, interests=["jazz", "rock_climbing"])
        service = _make_service([user, cand])

        service.import_external_interests(
            "u_rev", "google",
            {"items": [{"title": "Jazz", "is_topic": True, "confidence": 0.90}]},
            user_confirmed=True,
        )
        service.set_external_interest_consent("u_rev", "google", True)

        recs_before = service.get_recommendations("u_rev", limit=5)
        assert recs_before[0].get("interests") is not None

        service.set_external_interest_consent("u_rev", "google", False)
        recs_after = service.get_recommendations("u_rev", limit=5)
        assert recs_after[0].get("interests") is None


# ---------------------------------------------------------------------------
# T1-6  Weight comparison — 0.0 vs configured weight
# ---------------------------------------------------------------------------

class TestInterestWeightComparison:
    """Prove that non-zero weight changes final_score for a candidate with matching interests."""

    def _recs(self, interest_weight: float, consent: bool):
        user = _woman("u_wt", age=28)
        cand = _man("c_wt", age=29, interests=["jazz"])
        service = _make_service([user, cand], interest_weight)
        service.import_external_interests(
            "u_wt", "google",
            {"items": [{"title": "Jazz", "is_topic": True, "confidence": 0.95}]},
            user_confirmed=True,
        )
        if consent:
            service.set_external_interest_consent("u_wt", "google", True)
        return service.get_recommendations("u_wt", limit=5)

    def test_nonzero_weight_produces_higher_score_than_zero_weight(self):
        recs_zero = self._recs(0.0, consent=True)
        recs_nonzero = self._recs(0.05, consent=True)
        score_zero = recs_zero[0]["ranking"]["final_score"]
        score_nonzero = recs_nonzero[0]["ranking"]["final_score"]
        assert score_nonzero > score_zero, (
            f"Non-zero interest weight should increase score for matching candidate. "
            f"zero={score_zero:.4f} nonzero={score_nonzero:.4f}"
        )

    def test_zero_weight_matches_no_consent_baseline(self):
        """Zero-weight with consent must produce same final_score as no-consent case."""
        recs_zero_consent = self._recs(0.0, consent=True)
        recs_no_consent = self._recs(0.0, consent=False)
        # Both should produce identical final_scores since effective weight is 0 in both
        s1 = recs_zero_consent[0]["ranking"]["final_score"]
        s2 = recs_no_consent[0]["ranking"]["final_score"]
        assert s1 == s2, (
            f"Zero-weight + consent should equal no-consent: {s1} vs {s2}"
        )

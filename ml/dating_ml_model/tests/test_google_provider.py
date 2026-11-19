"""Tests for StandardizedGoogleInterestProvider and validate_google_payload.

No live Google API calls. Tests verify:
1. validate_google_payload rejects structural errors.
2. StandardizedGoogleInterestProvider correctly processes valid payloads.
3. Confidence calibration, duplicate deduplication, provenance integrity.
4. Provider integrates into RecommendationService via import_external_interests.
5. Data freshness warnings are surfaced but do not block processing.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from dating_ml_model.google_interest_provider import (
    GooglePayloadValidationError,
    StandardizedGoogleInterestProvider,
    validate_google_payload,
    MAX_ITEMS_PER_PAYLOAD,
    MIN_CONFIDENCE_WARN_THRESHOLD,
)
from dating_ml_model.external_interests import ExternalInterestPayload
from dating_ml_model.model import RecommendationModel
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService

NOW = datetime(2026, 10, 30, 10, 0, 0)
_HASH = hashlib.sha256(b"test_google_account").hexdigest()[:16]


def _valid_payload(**overrides) -> dict:
    base = {
        "account_id_hash": _HASH,
        "items": [
            {"topic_name": "Jazz Music", "topic_id": "/m/03_d0", "confidence": 0.90},
            {"topic_name": "Rock Climbing", "is_topic": True, "confidence": 0.85},
        ],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "api_version": "youtube/v3",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. validate_google_payload
# ---------------------------------------------------------------------------

class TestValidateGooglePayload:
    def test_valid_payload_passes(self):
        result = validate_google_payload(_valid_payload())
        assert "_validation_warnings" in result
        assert isinstance(result["_validation_warnings"], list)

    def test_missing_account_id_hash_raises(self):
        payload = _valid_payload()
        del payload["account_id_hash"]
        with pytest.raises(GooglePayloadValidationError, match="account_id_hash"):
            validate_google_payload(payload)

    def test_empty_account_id_hash_raises(self):
        with pytest.raises(GooglePayloadValidationError, match="account_id_hash"):
            validate_google_payload(_valid_payload(account_id_hash=""))

    def test_missing_items_raises(self):
        payload = _valid_payload()
        del payload["items"]
        with pytest.raises(GooglePayloadValidationError, match="items.*required"):
            validate_google_payload(payload)

    def test_items_not_a_list_raises(self):
        with pytest.raises(GooglePayloadValidationError, match="must be a list"):
            validate_google_payload(_valid_payload(items="not a list"))

    def test_too_many_items_raises(self):
        items = [{"topic_name": f"Topic {i}"} for i in range(MAX_ITEMS_PER_PAYLOAD + 1)]
        with pytest.raises(GooglePayloadValidationError, match="exceeds maximum"):
            validate_google_payload(_valid_payload(items=items))

    def test_item_not_a_dict_raises(self):
        with pytest.raises(GooglePayloadValidationError, match="must be a dict"):
            validate_google_payload(_valid_payload(items=["not a dict"]))

    def test_item_missing_topic_name_raises(self):
        with pytest.raises(GooglePayloadValidationError, match="topic_name"):
            validate_google_payload(_valid_payload(items=[{"confidence": 0.9}]))

    def test_item_invalid_confidence_type_raises(self):
        with pytest.raises(GooglePayloadValidationError, match="confidence.*number"):
            validate_google_payload(_valid_payload(items=[
                {"topic_name": "Jazz", "confidence": "high"}
            ]))

    def test_item_confidence_out_of_range_raises(self):
        with pytest.raises(GooglePayloadValidationError, match="\\[0.0, 1.0\\]"):
            validate_google_payload(_valid_payload(items=[
                {"topic_name": "Jazz", "confidence": 1.5}
            ]))

    def test_low_confidence_adds_warning_not_error(self):
        result = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Jazz", "confidence": 0.30}
        ]))
        assert any("low confidence" in w for w in result["_validation_warnings"])

    def test_stale_fetched_at_adds_warning(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        result = validate_google_payload(_valid_payload(fetched_at=old_date))
        assert any("days ago" in w for w in result["_validation_warnings"])

    def test_recent_fetched_at_no_freshness_warning(self):
        recent = datetime.now(timezone.utc).isoformat()
        result = validate_google_payload(_valid_payload(fetched_at=recent))
        assert not any("days ago" in w for w in result["_validation_warnings"])

    def test_empty_items_list_is_valid(self):
        result = validate_google_payload(_valid_payload(items=[]))
        assert "_validation_warnings" in result


# ---------------------------------------------------------------------------
# 2. StandardizedGoogleInterestProvider.extract_interests
# ---------------------------------------------------------------------------

class TestStandardizedGoogleInterestProvider:
    def setup_method(self):
        self.provider = StandardizedGoogleInterestProvider()
        self.uid = "user_prod_001"

    def test_provider_id_is_google(self):
        assert self.provider.provider_id == "google"

    def test_supported_scopes_include_youtube_readonly(self):
        assert "https://www.googleapis.com/auth/youtube.readonly" in self.provider.supported_scopes

    def test_returns_external_interest_payload(self):
        payload = validate_google_payload(_valid_payload())
        result = self.provider.extract_interests(self.uid, payload)
        assert isinstance(result, ExternalInterestPayload)
        assert result.user_id == self.uid
        assert result.provider == "google"

    def test_account_id_hash_preserved_not_rehashed(self):
        payload = validate_google_payload(_valid_payload(account_id_hash=_HASH))
        result = self.provider.extract_interests(self.uid, payload)
        assert result.external_account_id_hash == _HASH

    def test_two_items_produce_two_interests(self):
        payload = validate_google_payload(_valid_payload())
        result = self.provider.extract_interests(self.uid, payload)
        assert len(result.interests) == 2

    def test_canonical_tokens_have_correct_format(self):
        payload = validate_google_payload(_valid_payload())
        result = self.provider.extract_interests(self.uid, payload)
        for interest in result.interests:
            assert interest.canonical_token.startswith("interest_tag:")

    def test_topic_id_gives_higher_confidence_than_subscription(self):
        payload = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Jazz", "topic_id": "/m/03_d0"},
            {"topic_name": "Hiking"},
        ]))
        result = self.provider.extract_interests(self.uid, payload)
        jazz = next(i for i in result.interests if "jazz" in i.canonical_token)
        hiking = next(i for i in result.interests if "hiking" in i.canonical_token)
        assert jazz.confidence >= hiking.confidence

    def test_duplicate_topics_deduplicated(self):
        payload = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Jazz Music", "topic_id": "/m/03_d0"},
            {"topic_name": "Jazz Music", "topic_id": "/m/03_d0"},  # duplicate
        ]))
        result = self.provider.extract_interests(self.uid, payload)
        assert len(result.interests) == 1
        assert any("duplicate" in w for w in result.warnings)

    def test_empty_topic_name_skipped(self):
        payload = _valid_payload(items=[
            {"topic_name": "Jazz"},
            {"topic_name": "   "},  # empty after strip
        ])
        result = self.provider.extract_interests(self.uid, payload)
        assert len(result.interests) == 1

    def test_user_confirmed_flag_preserved(self):
        payload = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Jazz", "user_confirmed": True},
        ]))
        result = self.provider.extract_interests(self.uid, payload)
        assert result.interests[0].user_confirmed is True

    def test_unconfirmed_flag_preserved(self):
        payload = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Jazz"},  # no user_confirmed key → defaults False
        ]))
        result = self.provider.extract_interests(self.uid, payload)
        assert result.interests[0].user_confirmed is False

    def test_category_inferred_when_absent(self):
        payload = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Rock Climbing", "is_topic": True},
        ]))
        result = self.provider.extract_interests(self.uid, payload)
        assert result.interests[0].category == "outdoors"

    def test_explicit_category_overrides_inference(self):
        payload = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Rock Climbing", "category": "fitness"},
        ]))
        result = self.provider.extract_interests(self.uid, payload)
        assert result.interests[0].category == "fitness"

    def test_metadata_marks_synthetic_false(self):
        payload = validate_google_payload(_valid_payload())
        result = self.provider.extract_interests(self.uid, payload)
        assert result.raw_metadata.get("synthetic") is False

    def test_validation_warnings_propagated(self):
        payload = validate_google_payload(_valid_payload(items=[
            {"topic_name": "Jazz", "confidence": 0.20},  # low confidence warning
        ]))
        result = self.provider.extract_interests(self.uid, payload)
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# 3. Integration with RecommendationService
# ---------------------------------------------------------------------------

class TestStandardizedProviderServiceIntegration:
    def test_provider_integrates_via_import_external_interests(self):
        user = {"id": "u_prod", "age": 28, "sex": "m", "orientation": "straight"}
        candidate = {
            "id": "c_prod", "age": 27, "sex": "f", "orientation": "straight",
            "interests": ["jazz", "rock_climbing"],
        }
        repo = InMemoryRecommendationRepository([user, candidate])
        model = RecommendationModel()
        service = RecommendationService(
            model.compatibility, repo, recommendation_model=model,
            clock=lambda: NOW
        )

        payload = validate_google_payload({
            "account_id_hash": _HASH,
            "items": [
                {"topic_name": "Jazz Music", "topic_id": "/m/03_d0", "confidence": 0.90},
                {"topic_name": "Rock Climbing", "is_topic": True, "confidence": 0.85},
            ],
        })
        provider = StandardizedGoogleInterestProvider()

        result = service.import_external_interests(
            "u_prod", "google", payload,
            provider_instance=provider,
            user_confirmed=True,
        )
        assert result["imported_count"] == 2
        assert result["provider"] == "google"

    def test_consent_required_before_interests_used_in_ranking(self):
        user = {"id": "u_consent_test", "age": 28, "sex": "m", "orientation": "straight"}
        candidate = {
            "id": "c_consent_cand", "age": 27, "sex": "f", "orientation": "straight",
            "interests": ["jazz_music"],
        }
        repo = InMemoryRecommendationRepository([user, candidate])
        model = RecommendationModel()
        service = RecommendationService(
            model.compatibility, repo, recommendation_model=model,
            clock=lambda: NOW
        )

        payload = validate_google_payload({
            "account_id_hash": _HASH,
            "items": [{"topic_name": "Jazz Music", "topic_id": "/m/03_d0", "confidence": 0.90}],
        })
        service.import_external_interests(
            "u_consent_test", "google", payload,
            provider_instance=StandardizedGoogleInterestProvider(),
        )

        # No consent — interests must not appear
        recs_no_consent = service.get_recommendations("u_consent_test", limit=5)
        assert recs_no_consent[0].get("interests") is None

        # Grant consent — interests must appear
        service.set_external_interest_consent("u_consent_test", "google", True)
        recs_consented = service.get_recommendations("u_consent_test", limit=5)
        assert recs_consented[0].get("interests") is not None

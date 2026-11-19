import os

import pytest

from dating_ml_model.preference_interpreter import (
    GeminiProviderUnavailable,
    GeminiPreferenceClient,
    _parse_json_response,
    interpret_preference_request,
)


class FakeGeminiClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def __call__(self, request):
        if self.error:
            raise self.error
        return self.response


def test_fake_gemini_valid_hard_and_soft_responses_are_normalized():
    hard = interpret_preference_request(
        "exclude Konkan region",
        ai_client=FakeGeminiClient({
            "status": "confirmation_required",
            "preferences": {"hard_exclusions": {"region": {"values": ["Konkan"]}}},
        }),
    )
    assert hard["preferences"]["hard_exclusions"]["region"]["values"] == ["konkan"]
    assert hard["confirmed"] is False

    soft = interpret_preference_request(
        "prefer software professionals",
        ai_client=FakeGeminiClient({
            "status": "confirmation_required",
            "preferences": {"criteria": {"profession": {"values": ["Software"], "hard": False}}},
        }),
    )
    assert soft["preferences"]["criteria"]["profession"] == {"values": ["software"], "hard": False}


def test_fake_gemini_ambiguous_response_is_returned_for_clarification():
    result = interpret_preference_request(
        "Konkani people",
        ai_client=FakeGeminiClient({
            "status": "clarification_required",
            "question": "Do you mean Konkani as a language or a region?",
        }),
    )
    assert result["status"] == "clarification_required"


def test_malformed_gemini_output_is_rejected():
    with pytest.raises(ValueError, match="not valid JSON"):
        _parse_json_response("not-json")
    with pytest.raises(ValueError, match="structured"):
        interpret_preference_request("exclude Konkan region", ai_client=FakeGeminiClient({"status": "unknown"}))


@pytest.mark.parametrize("response", [
    {"status": "confirmation_required", "preferences": {
        "hard_exclusions": {"region": {"values": ["Konkan"]}},
    }},
    {"status": "confirmation_required", "preferences": {
        "criteria": {"profession": {"values": ["Software"], "hard": False}},
    }},
])
def test_actual_structured_provider_payloads_are_accepted(response):
    result = interpret_preference_request("request", ai_client=FakeGeminiClient(response))
    assert result["status"] == "confirmation_required"


def test_valid_preference_removes_empty_optional_fields():
    result = interpret_preference_request("exclude Konkan region", ai_client=FakeGeminiClient({
        "status": "confirmation_required",
        "preferences": {
            "criteria": {},
            "hard_exclusions": {
                "region": {"values": ["Konkan"]},
                "religion": {"values": []},
                "profession": {"values": []},
            },
        },
    }))
    assert result["status"] == "confirmation_required"
    assert result["preferences"]["hard_exclusions"] == {"region": {"values": ["konkan"]}}


def test_all_empty_preference_fields_are_rejected():
    with pytest.raises(ValueError, match="invalid preferences"):
        interpret_preference_request("unclear", ai_client=FakeGeminiClient({
            "status": "confirmation_required",
            "preferences": {
                "criteria": {"region": {"values": [], "hard": False}},
                "hard_exclusions": {"region": {"values": []}},
            },
        }))


@pytest.mark.parametrize("response", [
    {"status": "confirmation_required", "preferences": {"criteria": {"city": {"values": ["Pune"], "hard": False}}}},
    {"status": "confirmation_required", "preferences": {"hard_exclusions": {"region": {"operator": "exclude", "values": ["Konkan"]}}}},
    {"status": "confirmation_required", "preferences": {"criteria": {"region": {"values": [""], "hard": False}}}},
])
def test_invalid_fields_operators_and_values_are_rejected(response):
    with pytest.raises(ValueError, match="AI"):
        interpret_preference_request("request", ai_client=FakeGeminiClient(response))


def test_invalid_non_empty_values_are_rejected():
    with pytest.raises(ValueError, match="invalid preference value"):
        interpret_preference_request("request", ai_client=FakeGeminiClient({
            "status": "confirmation_required",
            "preferences": {"hard_exclusions": {"region": {"values": ["Konkan", 7]}}},
        }))


def test_clarification_payload_cannot_contain_preferences():
    with pytest.raises(ValueError, match="clarification"):
        interpret_preference_request("Konkani", ai_client=FakeGeminiClient({
            "status": "clarification_required",
            "question": "Which meaning?",
            "preferences": {},
        }))


def test_provider_failure_uses_deterministic_local_fallback():
    result = interpret_preference_request(
        "Exclude the Konkan region",
        ai_client=FakeGeminiClient(error=GeminiProviderUnavailable("offline")),
    )
    assert result["preferences"]["hard_exclusions"]["region"]["values"] == ["konkan"]


def test_confirmation_is_required_and_revalidated_before_save():
    from dating_ml_model.repository import InMemoryRecommendationRepository
    from dating_ml_model.service import RecommendationService
    from dating_ml_model.model import CompatibilityModel
    from dating_ml_model.tests.reco_fixtures import PROFILES

    repo = InMemoryRecommendationRepository(PROFILES)
    service = RecommendationService(CompatibilityModel(), repo)
    interpreted = {"status": "confirmation_required",
                   "preferences": {"hard_exclusions": {"region": {"values": ["Konkan"]}}},
                   "confirmed": False}
    with pytest.raises(ValueError, match="confirmed"):
        service.confirm_interpreted_preferences("u1", interpreted)
    interpreted["confirmed"] = True
    saved = service.confirm_interpreted_preferences("u1", interpreted)
    assert saved["normalized"]["hard_exclusions"]["region"]["values"] == ["konkan"]
    assert repo.get_user_preferences("u1")["hard_exclusions"]["region"]["values"] == ["konkan"]


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY is not configured")
def test_live_gemini_preference_smoke():
    result = interpret_preference_request("exclude the Konkan region")
    assert result["status"] in {"confirmation_required", "clarification_required"}

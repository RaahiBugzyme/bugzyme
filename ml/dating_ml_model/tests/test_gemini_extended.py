"""Tests for the extended Gemini preference interpreter (v3 expansion).

All tests use fake/mock clients — no live Gemini API calls.
Covers the expanded field set: age, lifestyle, relationship_intention, diet,
smokes, drinks, drugs, children, profession, region, religion (exclusion).
"""
from __future__ import annotations

import pytest

from dating_ml_model.preference_interpreter import (
    GeminiProviderUnavailable,
    _validate_extended_ai_shape,
    _local_interpret_extended,
    interpret_extended_preference_request,
    EXTENDED_RANGE_FIELDS,
    EXTENDED_SET_FIELDS,
    EXTENDED_HARD_EXCLUSION_FIELDS,
)


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def __call__(self, _request: str):
        if self.error:
            raise self.error
        return self.response


# ---------------------------------------------------------------------------
# Schema constants sanity
# ---------------------------------------------------------------------------

class TestExtendedConstants:
    def test_age_in_range_fields(self):
        assert "age" in EXTENDED_RANGE_FIELDS

    def test_children_in_set_fields(self):
        assert "children" in EXTENDED_SET_FIELDS

    def test_hard_exclusions_restricted(self):
        assert set(EXTENDED_HARD_EXCLUSION_FIELDS) == {"region", "religion", "profession"}


# ---------------------------------------------------------------------------
# _validate_extended_ai_shape
# ---------------------------------------------------------------------------

class TestValidateExtendedAiShape:
    def test_valid_age_range(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"criteria": {"age": {"min": 25.0, "max": 35.0, "hard": False}}},
        }
        result = _validate_extended_ai_shape(raw)
        assert result["preferences"]["criteria"]["age"]["min"] == 25.0
        assert result["preferences"]["criteria"]["age"]["hard"] is False

    def test_valid_set_criterion_smokes(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"criteria": {"smokes": {"values": ["no"], "hard": False}}},
        }
        result = _validate_extended_ai_shape(raw)
        assert result["preferences"]["criteria"]["smokes"]["values"] == ["no"]

    def test_valid_hard_exclusion_region(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"hard_exclusions": {"region": {"values": ["Konkan"]}}},
        }
        result = _validate_extended_ai_shape(raw)
        assert result["preferences"]["hard_exclusions"]["region"]["values"] == ["Konkan"]

    def test_unsupported_field_rejected(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"criteria": {"city": {"values": ["Mumbai"], "hard": False}}},
        }
        with pytest.raises(ValueError, match="unsupported preference field"):
            _validate_extended_ai_shape(raw)

    def test_missing_hard_flag_rejected(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"criteria": {"smokes": {"values": ["no"]}}},
        }
        with pytest.raises(ValueError, match="hard as a boolean"):
            _validate_extended_ai_shape(raw)

    def test_range_field_without_min_or_max_rejected(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"criteria": {"age": {"hard": False}}},
        }
        with pytest.raises(ValueError, match="min or max"):
            _validate_extended_ai_shape(raw)

    def test_set_field_with_invalid_value_rejected(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"criteria": {"diet": {"values": ["vegan", 42], "hard": False}}},
        }
        with pytest.raises(ValueError, match="invalid value"):
            _validate_extended_ai_shape(raw)

    def test_hard_exclusion_of_unsupported_field_rejected(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {"hard_exclusions": {"age": {"values": ["30"]}}},
        }
        with pytest.raises(ValueError, match="unsupported hard_exclusion field"):
            _validate_extended_ai_shape(raw)

    def test_clarification_with_extra_keys_rejected(self):
        raw = {
            "status": "clarification_required",
            "question": "Which diet?",
            "preferences": {},
        }
        with pytest.raises(ValueError, match="unsupported fields"):
            _validate_extended_ai_shape(raw)

    def test_unknown_top_level_key_rejected(self):
        raw = {
            "status": "confirmation_required",
            "preferences": {},
            "extra_key": "bad",
        }
        with pytest.raises(ValueError, match="unsupported top-level fields"):
            _validate_extended_ai_shape(raw)


# ---------------------------------------------------------------------------
# _local_interpret_extended — deterministic fallback
# ---------------------------------------------------------------------------

class TestLocalInterpretExtended:
    def test_age_range_between_syntax(self):
        result = _local_interpret_extended("I want someone between 25 and 35")
        assert result["status"] == "confirmation_required"
        age = result["preferences"]["criteria"]["age"]
        assert age["min"] == 25.0
        assert age["max"] == 35.0
        assert age["hard"] is False

    def test_age_range_ages_to_syntax(self):
        result = _local_interpret_extended("Looking for ages 28 to 40")
        assert result["status"] == "confirmation_required"
        age = result["preferences"]["criteria"]["age"]
        assert age["min"] == 28.0
        assert age["max"] == 40.0

    def test_age_minimum(self):
        result = _local_interpret_extended("at least 30 years old")
        assert result["status"] == "confirmation_required"
        age = result["preferences"]["criteria"]["age"]
        assert age["min"] == 30.0
        assert age["max"] is None

    def test_age_maximum(self):
        result = _local_interpret_extended("under 40 years old")
        assert result["status"] == "confirmation_required"
        age = result["preferences"]["criteria"]["age"]
        assert age["min"] is None
        assert age["max"] == 40.0

    def test_long_term_relationship_intention(self):
        result = _local_interpret_extended("looking for a long-term relationship")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["relationship_intention"]["values"]
        assert "long_term" in val

    def test_casual_relationship_intention(self):
        result = _local_interpret_extended("open to casual dating")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["relationship_intention"]["values"]
        assert "casual" in val

    def test_vegan_diet(self):
        result = _local_interpret_extended("prefer someone vegan")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["diet"]["values"]
        assert "vegan" in val

    def test_non_smoker(self):
        result = _local_interpret_extended("only non-smokers please")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["smokes"]["values"]
        assert "no" in val

    def test_non_drinker(self):
        result = _local_interpret_extended("doesn't drink alcohol")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["drinks"]["values"]
        assert "not at all" in val or "rarely" in val

    def test_drug_free(self):
        result = _local_interpret_extended("must be drug-free")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["drugs"]["values"]
        assert "never" in val

    def test_wants_kids(self):
        result = _local_interpret_extended("I want kids someday")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["children"]["values"]
        assert "yes" in val

    def test_no_kids(self):
        result = _local_interpret_extended("child-free lifestyle preferred")
        assert result["status"] == "confirmation_required"
        val = result["preferences"]["criteria"]["children"]["values"]
        assert "no" in val

    def test_original_fallback_for_region_exclusion(self):
        result = _local_interpret_extended("exclude the Konkan region")
        # Should route to original _local_interpret which handles region exclusion
        assert result["status"] == "confirmation_required"

    def test_empty_request_returns_clarification(self):
        result = _local_interpret_extended("")
        assert result["status"] == "clarification_required"


# ---------------------------------------------------------------------------
# interpret_extended_preference_request — full function
# ---------------------------------------------------------------------------

class TestInterpretExtendedPreferenceRequest:
    def test_fake_client_age_range(self):
        result = interpret_extended_preference_request(
            "ages 25 to 35",
            ai_client=FakeClient({
                "status": "confirmation_required",
                "preferences": {"criteria": {"age": {"min": 25.0, "max": 35.0, "hard": False}}},
            }),
        )
        assert result["status"] == "confirmation_required"
        assert result["confirmed"] is False
        assert result["preferences"]["criteria"]["age"]["min"] == 25.0

    def test_fake_client_smokes_soft(self):
        result = interpret_extended_preference_request(
            "non-smokers only",
            ai_client=FakeClient({
                "status": "confirmation_required",
                "preferences": {"criteria": {"smokes": {"values": ["no"], "hard": False}}},
            }),
        )
        assert result["status"] == "confirmation_required"
        assert result["preferences"]["criteria"]["smokes"]["values"] == ["no"]

    def test_fake_client_diet_vegan(self):
        result = interpret_extended_preference_request(
            "vegan diet preferred",
            ai_client=FakeClient({
                "status": "confirmation_required",
                "preferences": {"criteria": {"diet": {"values": ["vegan"], "hard": False}}},
            }),
        )
        assert result["status"] == "confirmation_required"

    def test_fake_client_relationship_intention(self):
        result = interpret_extended_preference_request(
            "looking for something serious",
            ai_client=FakeClient({
                "status": "confirmation_required",
                "preferences": {"criteria": {"relationship_intention": {"values": ["serious"], "hard": False}}},
            }),
        )
        assert result["status"] == "confirmation_required"
        assert "relationship_intention" in result["preferences"]["criteria"]

    def test_fake_client_hard_exclusion_religion(self):
        result = interpret_extended_preference_request(
            "exclude scientology",
            ai_client=FakeClient({
                "status": "confirmation_required",
                "preferences": {"hard_exclusions": {"religion": {"values": ["scientology"]}}},
            }),
        )
        assert result["status"] == "confirmation_required"
        assert "religion" in result["preferences"]["hard_exclusions"]

    def test_clarification_required(self):
        result = interpret_extended_preference_request(
            "someone compatible",
            ai_client=FakeClient({
                "status": "clarification_required",
                "question": "What specific attribute are you looking for?",
            }),
        )
        assert result["status"] == "clarification_required"
        assert "question" in result

    def test_provider_failure_uses_local_fallback(self):
        result = interpret_extended_preference_request(
            "between 25 and 35",
            ai_client=FakeClient(error=GeminiProviderUnavailable("offline")),
        )
        assert result["status"] == "confirmation_required"
        assert "age" in result["preferences"]["criteria"]

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="structured"):
            interpret_extended_preference_request(
                "test",
                ai_client=FakeClient({"status": "invalid_status"}),
            )

    def test_unsupported_field_in_client_response_raises(self):
        with pytest.raises(ValueError):
            interpret_extended_preference_request(
                "test",
                ai_client=FakeClient({
                    "status": "confirmation_required",
                    "preferences": {"criteria": {"city": {"values": ["Pune"], "hard": False}}},
                }),
            )

    def test_confirmed_false_always(self):
        result = interpret_extended_preference_request(
            "non-smokers please",
            ai_client=FakeClient({
                "status": "confirmation_required",
                "preferences": {"criteria": {"smokes": {"values": ["no"], "hard": False}}},
            }),
        )
        assert result.get("confirmed") is False

    def test_no_client_uses_local_fallback(self):
        """Without GEMINI_API_KEY, extended local fallback must be used."""
        import os
        orig = os.environ.pop("GEMINI_API_KEY", None)
        try:
            result = interpret_extended_preference_request("looking for long-term")
            assert result["status"] == "confirmation_required"
        finally:
            if orig:
                os.environ["GEMINI_API_KEY"] = orig

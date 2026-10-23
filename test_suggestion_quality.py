
from app.ai.suggestions import _validate_suggestions


HINGLISH_TRANSCRIPT = """
Aarav: Hey, aaj ka din kaisa tha?
Meera: Yaar kaafi tiring tha, office mein bahut kaam tha.
Aarav: Ab ghar aake kya plan hai?
Meera: Bas kuch dekhungi ya music sunungi.
Aarav: Kal comedy try ki thi?
Meera: Haan yaar, ab koi genuinely funny recommendation do.
"""

ANALYSIS = {
    "current_topic": "Funny entertainment recommendations",
    "last_message_intent": "Asking for a genuinely funny recommendation",
    "conversation_tone": "casual",
    "conversation_state": "conversation slowing down",
    "next_reply_strategy": "Give a relevant funny recommendation",
}


def make_suggestions(natural, playful, thoughtful):
    return [
        {"style": "natural", "message": natural},
        {"style": "playful", "message": playful},
        {"style": "thoughtful", "message": thoughtful},
    ]


def test_accepts_relevant_hinglish_suggestions():
    suggestions = make_suggestions(
        "Ek baar Brooklyn Nine-Nine try karo, kaafi funny hai.",
        "Tumhare comedy standards ke liye The Office ka challenge hai 😂",
        "Modern Family dekho, uski comedy naturally mood fresh kar deti hai.",
    )

    valid, issues = _validate_suggestions(
        suggestions, HINGLISH_TRANSCRIPT, ANALYSIS
    )

    assert len(valid) == 3, f"Expected 3 valid suggestions, got: {issues}"
    assert not issues


def test_rejects_english_only_suggestions_for_hinglish():
    suggestions = make_suggestions(
        "You should try a funny sitcom tonight.",
        "Maybe your comedy standards are too high today.",
        "A good comedy show might improve your mood.",
    )

    valid, issues = _validate_suggestions(
        suggestions, HINGLISH_TRANSCRIPT, ANALYSIS
    )

    assert not valid
    assert any("English-only" in issue for issue in issues), issues


def test_rejects_duplicate_suggestions():
    suggestions = make_suggestions(
        "Ek funny comedy show try karo aaj.",
        "Ek funny comedy show try karo aaj.",
        "Koi funny comedy show try karo aaj.",
    )

    valid, issues = _validate_suggestions(
        suggestions, HINGLISH_TRANSCRIPT, ANALYSIS
    )

    assert not valid
    assert any("repetitive" in issue.lower() for issue in issues), issues


def test_rejects_suggestions_over_word_limit():
    long_message = (
        "Ek baar koi bahut hi funny comedy show try karo "
        "jo tumhara mood fresh kare aur tumhe bahut zyada hasaye aaj"
    )

    suggestions = make_suggestions(
        long_message,
        "Tumhare comedy standards kaafi high lag rahe hain aaj 😂",
        "Modern Family try karo, uski comedy kaafi relatable hai.",
    )

    valid, issues = _validate_suggestions(
        suggestions, HINGLISH_TRANSCRIPT, ANALYSIS
    )

    assert not valid
    assert any("20-word maximum" in issue for issue in issues), issues


def test_rejects_unsupported_specific_details():
    suggestions = make_suggestions(
        "Kal 8 PM par Netflix pe comedy night karte hain.",
        "Friday ko 7 PM par movie dekhne chalte hain.",
        "Saturday ko Delhi ke ek cafe mein comedy dekhte hain.",
    )

    valid, issues = _validate_suggestions(
        suggestions, HINGLISH_TRANSCRIPT, ANALYSIS
    )

    assert not valid
    assert issues, "Expected unsupported specifics to be flagged"


def test_validator_does_not_guarantee_semantic_relevance():
    # This documents a known limitation:
    # current validation checks structure and language, not actual relevance.
    suggestions = make_suggestions(
        "Aaj weather kaafi nice lag raha hai yaar.",
        "Chalo aaj clouds ko funny names dete hain 😂",
        "Kabhi kabhi rainy days bhi kaafi peaceful hote hain.",
    )

    valid, issues = _validate_suggestions(
        suggestions, HINGLISH_TRANSCRIPT, ANALYSIS
    )

    # These may pass despite ignoring the request for a funny recommendation.
    # This test documents the limitation rather than asserting a failure.
    print("Validator result for potentially irrelevant replies:")
    print("Accepted:", bool(valid))
    print("Issues:", issues)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))



import json
from unittest.mock import patch

from app.ai.suggestions import _check_suggestion_relevance


def test_relevance_checker_accepts_relevant_suggestions():
    transcript = """
Aarav: Aaj kya karne ka plan hai?
Meera: Kuch khaas nahi, tum batao?
Aarav: Haan yaar, ab koi genuinely funny recommendation do.
"""

    analysis = {
        "current_topic": "funny recommendations",
        "last_message_intent": "asking for a funny recommendation",
        "next_reply_strategy": "give a funny recommendation",
    }

    suggestions = [
        {"style": "natural", "message": "Ek funny stand-up special try karo 😂"},
        {"style": "playful", "message": "Mere jokes sun lo, free comedy show hai 😂"},
        {"style": "thoughtful", "message": "Tumhe comedy movies pasand hain ya stand-up?"},
    ]

    model_response = {
        "results": [
            {"style": "natural", "relevant": True, "reason": ""},
            {"style": "playful", "relevant": True, "reason": ""},
            {"style": "thoughtful", "relevant": True, "reason": ""},
        ]
    }

    with patch(
        "app.ai.suggestions._call_model",
        return_value=json.dumps(model_response),
    ):
        issues = _check_suggestion_relevance(
            transcript, analysis, suggestions
        )

    assert issues == []


def test_relevance_checker_rejects_irrelevant_suggestions():
    transcript = """
Aarav: Aaj kya karne ka plan hai?
Meera: Kuch khaas nahi, tum batao?
Aarav: Haan yaar, ab koi genuinely funny recommendation do.
"""

    analysis = {
        "current_topic": "funny recommendations",
        "last_message_intent": "asking for a funny recommendation",
        "next_reply_strategy": "give a funny recommendation",
    }

    suggestions = [
        {"style": "natural", "message": "Weather aaj kaafi achha hai."},
        {"style": "playful", "message": "Clouds ke funny names rakhte hain 😂"},
        {"style": "thoughtful", "message": "Rainy days kaafi peaceful hote hain."},
    ]

    model_response = {
        "results": [
            {
                "style": "natural",
                "relevant": False,
                "reason": "Does not provide a funny recommendation.",
            },
            {
                "style": "playful",
                "relevant": False,
                "reason": "Changes the subject.",
            },
            {
                "style": "thoughtful",
                "relevant": False,
                "reason": "Does not address the request.",
            },
        ]
    }

    with patch(
        "app.ai.suggestions._call_model",
        return_value=json.dumps(model_response),
    ):
        issues = _check_suggestion_relevance(
            transcript, analysis, suggestions
        )

    assert len(issues) == 3
    assert any("natural" in issue for issue in issues)
    assert any("playful" in issue for issue in issues)
    assert any("thoughtful" in issue for issue in issues)



def test_generate_suggestions_retries_when_relevance_fails():
    from app.ai.suggestions import _generate_suggestions

    transcript = (
        "Aarav: Koi genuinely funny recommendation do.\n"
        "Meera: Haan, kuch funny suggest karo na."
    )

    analysis = {
        "current_topic": "funny recommendations",
        "conversation_tone": "casual Hinglish",
        "last_message_intent": "asking for a funny recommendation",
        "conversation_state": "active",
        "next_reply_strategy": "give a funny recommendation",
        "detected_language": "hinglish",
    }

    suggestions = [
        {"style": "natural", "message": "Ek funny stand-up special try karo 😂"},
        {"style": "playful", "message": "Mere jokes sun lo, free comedy show hai 😂"},
        {"style": "thoughtful", "message": "Tumhe comedy movies pasand hain ya stand-up?"},
    ]

    with (
        patch(
            "app.ai.suggestions._build_generation_prompts",
            return_value=[
                {"role": "system", "content": "Generate suggestions."},
                {"role": "user", "content": "Reply to the latest message."},
            ],
        ),
        patch(
            "app.ai.suggestions._detect_language",
            return_value={
                "language": "hinglish",
                "instruction": "Use natural Roman-script Hinglish.",
            },
        ),
        patch(
            "app.ai.suggestions._call_model",
            return_value='{"suggestions": []}',
        ) as mock_model,
        patch(
            "app.ai.suggestions._parse_suggestions",
            return_value=suggestions,
        ),
        patch(
            "app.ai.suggestions._validate_suggestions",
            return_value=(suggestions, []),
        ),
        patch(
            "app.ai.suggestions._check_suggestion_relevance",
            side_effect=[
                ["The natural suggestion is irrelevant."],
                [],
            ],
        ) as mock_relevance,
    ):
        result = _generate_suggestions(
            transcript=transcript,
            analysis=analysis,
            memories=[],
            requesting_user="Aarav",
        )

    assert result == suggestions
    assert mock_model.call_count == 2
    assert mock_relevance.call_count == 2
    assert mock_relevance.call_count == 2
    assert mock_model.call_count == 2
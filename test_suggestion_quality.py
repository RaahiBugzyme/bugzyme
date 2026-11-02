
def test_generate_suggestions_retries_when_relevance_fails():
    from unittest.mock import patch
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

    relevance_call_count = 0

    def check_relevance(*args, **kwargs):
        nonlocal relevance_call_count
        relevance_call_count += 1
        print(f"\nRELEVANCE CALL #{relevance_call_count}")

        if relevance_call_count == 1:
            return ["The natural suggestion is irrelevant."]
        if relevance_call_count == 2:
            return []
        raise AssertionError("Unexpected extra relevance-check call")

    with (
        patch(
            "app.ai.suggestions._build_generation_prompts",
            return_value=[
                {"role": "system", "content": "Generate suggestions."},
                {"role": "user", "content": "Reply to the latest message."},
            ],
        ) as mock_prompts,
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
            side_effect=[
                (suggestions, []),
                (suggestions, []),
            ],
        ) as mock_validate,
        patch(
            "app.ai.suggestions._check_suggestion_relevance",
            side_effect=check_relevance,
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
    assert mock_prompts.call_count == 2
    assert mock_validate.call_count == 2
    assert relevance_call_count == 2

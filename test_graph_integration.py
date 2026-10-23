
"""
test_graph_integration.py

Integration tests for Bugzyme's LangGraph workflow.

Uses actual death-zone detection and mocks only AI suggestion generation.
No real database or Groq API call is required.
"""

from unittest.mock import patch

from app.ai.graph import conversation_graph
from app.ai.death_zone import analyze_death_zone, is_death_zone


def make_healthy_messages():
    """Create a conversation with reasonably substantive messages."""
    return [
        {
            "sender": "Aarav" if i % 2 == 0 else "Meera",
            "text": (
                f"I had a really interesting day and learned something new {i}"
                if i % 2 == 0
                else f"That sounds interesting! What did you learn today {i}?"
            ),
        }
        for i in range(24)
    ]


def make_short_messages():
    """Create a conversation containing consistently short messages."""
    replies = ["ok", "hmm", "yes", "no", "fine", "right"]

    return [
        {
            "sender": "Aarav" if i % 2 == 0 else "Meera",
            "text": replies[i % len(replies)],
        }
        for i in range(24)
    ]


def test_actual_death_zone_detection():
    """Verify the real detection functions run."""
    healthy_messages = make_healthy_messages()
    short_messages = make_short_messages()

    healthy_result = analyze_death_zone(healthy_messages)
    short_result = analyze_death_zone(short_messages)

    assert healthy_result["status"] != "insufficient_data"
    assert short_result["status"] != "insufficient_data"

    assert isinstance(healthy_result["death_zone_score"], float)
    assert isinstance(short_result["death_zone_score"], float)

    assert 0 <= healthy_result["death_zone_score"] <= 100
    assert 0 <= short_result["death_zone_score"] <= 100

    assert is_death_zone(healthy_result) is False
    assert is_death_zone(short_result) is True

    print("PASS: Actual death-zone detection")


def test_insufficient_data_does_not_trigger_suggestions():
    """Insufficient history should route to finish."""
    messages = [
        {"sender": "Aarav", "text": "Hey"},
        {"sender": "Meera", "text": "Hello"},
    ]

    result = analyze_death_zone(messages)

    assert result["status"] == "insufficient_data"
    assert is_death_zone(result) is False

    with patch(
        "app.ai.graph.suggest_next_messages"
    ) as mock_suggestions:
        graph_result = conversation_graph.invoke(
            {"messages": messages}
        )

    mock_suggestions.assert_not_called()

    assert graph_result["should_generate"] is False
    assert graph_result["suggestion_result"] is None

    print("PASS: Insufficient data skips suggestions")


def test_healthy_conversation_skips_suggestions():
    """A healthy conversation should take the finish route."""
    messages = make_healthy_messages()

    actual_result = analyze_death_zone(messages)
    assert is_death_zone(actual_result) is False, actual_result

    with patch(
        "app.ai.graph.suggest_next_messages"
    ) as mock_suggestions:
        graph_result = conversation_graph.invoke(
            {"messages": messages}
        )

    mock_suggestions.assert_not_called()

    assert graph_result["should_generate"] is False
    assert graph_result["death_zone"]["status"] == "healthy"

    print("PASS: Healthy conversation skips suggestions")


def test_death_zone_triggers_suggestions():
    """A real death-zone result should route to the suggestion node."""
    messages = make_short_messages()

    actual_result = analyze_death_zone(messages)
    assert is_death_zone(actual_result) is True, actual_result

    mock_output = {
        "analysis": {
            "current_topic": "General conversation",
            "conversation_tone": "casual",
            "last_message_intent": "Acknowledge the message",
            "conversation_state": "stagnant",
            "next_reply_strategy": "Ask a relevant open question",
            "detected_language": "english",
        },
        "memories_used": [],
        "suggestions": [
            {
                "style": "natural",
                "message": "What have you been up to lately?",
            },
            {
                "style": "playful",
                "message": "Haha, tell me something interesting!",
            },
            {
                "style": "thoughtful",
                "message": "Anything exciting on your mind lately?",
            },
        ],
    }

    with patch(
        "app.ai.graph.suggest_next_messages",
        return_value=mock_output,
    ) as mock_suggestions:
        graph_result = conversation_graph.invoke(
            {
                "messages": messages,
                "db": object(),
                "requesting_user_id": 1,
                "requesting_user": "Aarav",
            }
        )

    mock_suggestions.assert_called_once()

    assert graph_result["should_generate"] is True
    assert graph_result["suggestion_result"] == mock_output

    assert len(
        graph_result["suggestion_result"]["suggestions"]
    ) == 3

    print("PASS: Death zone triggers suggestion generation")


def test_graph_requires_database_for_suggestions():
    """The suggestion node must reject a missing database session."""
    messages = make_short_messages()

    try:
        conversation_graph.invoke(
            {
                "messages": messages,
                "requesting_user_id": 1,
                "requesting_user": "Aarav",
            }
        )
    except ValueError as exc:
        assert "Database session is required" in str(exc)
    else:
        raise AssertionError(
            "Expected a ValueError when the database is missing"
        )

    print("PASS: Database validation")


def run_all_tests():
    tests = [
        test_actual_death_zone_detection,
        test_insufficient_data_does_not_trigger_suggestions,
        test_healthy_conversation_skips_suggestions,
        test_death_zone_triggers_suggestions,
        test_graph_requires_database_for_suggestions,
    ]

    failures = []

    print("\n" + "=" * 60)
    print("BUGZYME GRAPH INTEGRATION TESTS")
    print("=" * 60)

    for test in tests:
        try:
            test()
        except Exception as exc:
            failures.append((test.__name__, str(exc)))
            print(f"FAIL: {test.__name__}: {exc}")

    print("\n" + "=" * 60)
    print(f"Results: {len(tests) - len(failures)}/{len(tests)} passed")

    if failures:
        print("\nFailures:")
        for name, error in failures:
            print(f"- {name}: {error}")

        raise SystemExit(1)

    print("ALL INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()

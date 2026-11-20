
from unittest.mock import patch

from app.ai.graph import (
    conversation_graph,
    detect_death_zone_node,
    route_after_detection,
)


def make_messages():
    """Create sample conversation messages."""
    return [
        {
            "sender": "Aarav",
            "text": "Hey, how was your day?",
        },
        {
            "sender": "Meera",
            "text": "It was good, thanks!",
        },
        {
            "sender": "Aarav",
            "text": "What did you do today?",
        },
        {
            "sender": "Meera",
            "text": "Nothing much.",
        },
    ]


def test_graph_compiled():
    """Check that the graph is compiled."""
    assert conversation_graph is not None

    graph_structure = conversation_graph.get_graph()
    nodes = graph_structure.nodes

    assert "detect_death_zone" in nodes
    assert "generate_suggestions" in nodes
    assert "finish" in nodes

    print("PASS: Graph compilation and nodes")


def test_route_after_detection():
    """Check conditional routing."""
    state_generate = {"should_generate": True}
    state_finish = {"should_generate": False}

    assert (
        route_after_detection(state_generate)
        == "generate_suggestions"
    )

    assert route_after_detection(state_finish) == "finish"

    print("PASS: Conditional routing")


def test_detect_death_zone_node():
    """Check death-zone detection node."""
    messages = make_messages()

    with patch(
        "app.ai.graph.analyze_death_zone",
        return_value={"is_death_zone": True},
    ), patch(
        "app.ai.graph.is_death_zone",
        return_value=True,
    ):
        result = detect_death_zone_node(
            {"messages": messages}
        )

    assert result["should_generate"] is True
    assert result["death_zone"] == {
        "is_death_zone": True
    }
    assert result["suggestion_result"] is None
    assert result["error"] is None

    print("PASS: Death-zone detection node")


def test_graph_finish_route():
    """Check full graph execution without generating suggestions."""
    messages = make_messages()

    with patch(
        "app.ai.graph.analyze_death_zone",
        return_value={"is_death_zone": False},
    ), patch(
        "app.ai.graph.is_death_zone",
        return_value=False,
    ):
        result = conversation_graph.invoke(
            {"messages": messages}
        )

    assert result["should_generate"] is False
    assert result["death_zone"] == {
        "is_death_zone": False
    }
    assert result["suggestion_result"] is None

    print("PASS: Full graph execution (finish route)")


def test_graph_suggestion_route():
    """Check routing to the suggestion node using a mock."""
    messages = make_messages()

    mock_suggestions = {
        "suggestions": [
            {
                "style": "natural",
                "message": "Ask her what she enjoyed most.",
            }
        ]
    }

    with patch(
        "app.ai.graph.analyze_death_zone",
        return_value={"is_death_zone": True},
    ), patch(
        "app.ai.graph.is_death_zone",
        return_value=True,
    ), patch(
        "app.ai.graph.suggest_next_messages",
        return_value=mock_suggestions,
    ) as mock_generate:

        result = conversation_graph.invoke(
            {
                "messages": messages,
                "db": object(),
                "requesting_user_id": 1,
                "requesting_user": "Aarav",
            }
        )

    mock_generate.assert_called_once()

    assert result["should_generate"] is True
    assert result["suggestion_result"] == mock_suggestions

    print("PASS: Full graph execution (suggestion route)")


def test_graph_rejects_empty_messages():
    """Check validation for empty conversations."""
    try:
        conversation_graph.invoke({"messages": []})
    except ValueError as exc:
        assert "non-empty list" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError for empty messages"
        )

    print("PASS: Empty messages validation")


def run_all_tests():
    tests = [
        test_graph_compiled,
        test_route_after_detection,
        test_detect_death_zone_node,
        test_graph_finish_route,
        test_graph_suggestion_route,
        test_graph_rejects_empty_messages,
    ]

    failures = []

    print("\n" + "=" * 55)
    print("BUGZYME LANGGRAPH TESTS")
    print("=" * 55)

    for test in tests:
        try:
            test()
        except Exception as exc:
            failures.append((test.__name__, str(exc)))
            print(f"FAIL: {test.__name__}: {exc}")

    print("\n" + "=" * 55)
    print(f"Results: {len(tests) - len(failures)}/{len(tests)} passed")

    if failures:
        print("\nFailures:")
        for name, error in failures:
            print(f"- {name}: {error}")
        raise SystemExit(1)

    print("ALL GRAPH TESTS PASSED")
    print("=" * 55)


if __name__ == "__main__":
    run_all_tests()

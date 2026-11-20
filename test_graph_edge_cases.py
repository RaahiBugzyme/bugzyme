from unittest.mock import patch

from app.ai.graph import (
    detect_death_zone_node,
    generate_suggestions_node,
    run_conversation_workflow,
)
from app.database import SessionLocal


def test_empty_messages_rejected():
    print("\nTEST 1: Empty messages are rejected")

    try:
        detect_death_zone_node({"messages": []})
    except ValueError as exc:
        assert "non-empty list" in str(exc)
        print("PASS:", exc)
        return

    raise AssertionError("Expected ValueError for empty messages")


def test_missing_database_rejected():
    print("\nTEST 2: Missing database is rejected")

    state = {
        "requesting_user_id": 1,
        "requesting_user": "Aarav",
        "messages": [{"sender": "Aarav", "content": "Hey"}],
    }

    try:
        generate_suggestions_node(state)
    except ValueError as exc:
        assert "Database session is required" in str(exc)
        print("PASS:", exc)
        return

    raise AssertionError("Expected ValueError for missing database")


def test_missing_user_id_rejected():
    print("\nTEST 3: Missing user ID is rejected")

    state = {
        "db": object(),
        "requesting_user": "Aarav",
        "messages": [{"sender": "Aarav", "content": "Hey"}],
    }

    try:
        generate_suggestions_node(state)
    except ValueError as exc:
        assert "Requesting user ID is required" in str(exc)
        print("PASS:", exc)
        return

    raise AssertionError("Expected ValueError for missing user ID")


def test_suggestion_failure_propagates():
    print("\nTEST 4: Suggestion-generation failure propagates")

    state = {
        "db": object(),
        "requesting_user_id": 1,
        "requesting_user": "Aarav",
        "messages": [{"sender": "Aarav", "content": "Hey"}],
    }

    with patch(
        "app.ai.graph.suggest_next_messages",
        side_effect=RuntimeError("Simulated AI failure"),
    ):
        try:
            generate_suggestions_node(state)
        except RuntimeError as exc:
            assert "Simulated AI failure" in str(exc)
            print("PASS:", exc)
            return

    raise AssertionError("Expected simulated AI failure to propagate")


def test_healthy_graph_skips_suggestions():
    print("\nTEST 5: Healthy graph skips suggestions")

    db = SessionLocal()
    messages = [
        {"sender": "Aarav", "speaker": "Aarav", "content": "Hello"},
        {"sender": "Meera", "speaker": "Meera", "content": "Hi"},
    ] * 6

    try:
        with patch(
            "app.ai.graph.analyze_death_zone",
            return_value={"status": "healthy", "death_zone_score": 15.0},
        ), patch(
            "app.ai.graph.is_death_zone",
            return_value=False,
        ), patch(
            "app.ai.graph.suggest_next_messages",
        ) as mock_suggestions:
            result = run_conversation_workflow(
                db=db,
                requesting_user_id=1,
                requesting_user="Aarav",
                messages=messages,
            )

            assert result["should_generate"] is False
            assert result["suggestion_result"] is None
            mock_suggestions.assert_not_called()

        print("PASS: Healthy graph skipped suggestion generation")
    finally:
        db.close()


def test_missing_username_rejected():
    print("\nTEST 6: Missing username is rejected")

    state = {
        "db": object(),
        "requesting_user_id": 1,
        "requesting_user": "",
        "messages": [{"sender": "Aarav", "content": "Hey"}],
    }

    try:
        generate_suggestions_node(state)
    except ValueError as exc:
        assert "Requesting user name is required" in str(exc)
        print("PASS:", exc)
        return

    raise AssertionError("Expected ValueError for missing username")


def test_invalid_messages_rejected():
    print("\nTEST 7: Invalid messages are rejected")

    for invalid_messages in (None, "not a list", []):
        try:
            detect_death_zone_node({"messages": invalid_messages})
        except ValueError as exc:
            assert "non-empty list" in str(exc)
        else:
            raise AssertionError(
                f"Expected ValueError for {invalid_messages!r}"
            )

    print("PASS: Invalid message inputs were rejected")


def test_death_zone_calls_suggestions():
    print("\nTEST 8: Death-zone route calls suggestions")

    db = SessionLocal()
    messages = [
        {"sender": "Aarav", "speaker": "Aarav", "content": "Hey"},
        {"sender": "Meera", "speaker": "Meera", "content": "Fine"},
    ] * 6

    fake_result = {
        "analysis": {"detected_language": "English"},
        "memories_used": [],
        "suggestions": [
            {"style": "natural", "message": "Tell me more."},
            {"style": "playful", "message": "Give me the fun version!"},
            {"style": "thoughtful", "message": "What was the best part?"},
        ],
    }

    try:
        with patch(
            "app.ai.graph.analyze_death_zone",
            return_value={
                "status": "possible_disengagement",
                "death_zone_score": 90.0,
                "confidence": "high",
            },
        ), patch(
            "app.ai.graph.is_death_zone",
            return_value=True,
        ), patch(
            "app.ai.graph.suggest_next_messages",
            return_value=fake_result,
        ) as mock_suggestions:
            result = run_conversation_workflow(
                db=db,
                requesting_user_id=1,
                requesting_user="Aarav",
                messages=messages,
            )

            assert result["should_generate"] is True
            assert result["suggestion_result"] == fake_result
            mock_suggestions.assert_called_once()

        print("PASS: Death-zone route called suggestions exactly once")
    finally:
        db.close()


def main():
    tests = [
        test_empty_messages_rejected,
        test_missing_database_rejected,
        test_missing_user_id_rejected,
        test_suggestion_failure_propagates,
        test_healthy_graph_skips_suggestions,
        test_missing_username_rejected,
        test_invalid_messages_rejected,
        test_death_zone_calls_suggestions,
    ]

    passed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"FAIL: {test.__name__}: {type(exc).__name__}: {exc}")

    print(f"\nEDGE CASES: {passed}/{len(tests)} passed")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

from test_conversation import conversation
from app.ai.graph import run_conversation_workflow
from app.ai.death_zone import analyze_death_zone, is_death_zone
from app.database import SessionLocal


def parse_conversation(text):
    messages = []

    for line in text.strip().splitlines():
        line = line.strip()

        if not line or ":" not in line:
            continue

        speaker, content = line.split(":", 1)
        speaker = speaker.strip()
        content = content.strip()

        messages.append({
            "sender": speaker,
            "speaker": speaker,
            "content": content,
        })

    return messages


def make_low_engagement_conversation(messages):
    """Append short replies to simulate declining engagement."""
    result = [dict(message) for message in messages]

    extra_messages = [
        ("Aarav", "Hey, aaj ka din kaisa tha?"),
        ("Meera", "Theek tha"),
        ("Aarav", "Kuch interesting hua aaj?"),
        ("Meera", "Nahi"),
        ("Aarav", "Abhi kya kar rahi ho?"),
        ("Meera", "Kuch nahi"),
        ("Aarav", "Thodi der baat karein?"),
        ("Meera", "Dekhte hain"),
        ("Aarav", "Aaj work kaisa tha?"),
        ("Meera", "Theek tha"),
        ("Aarav", "Aur batao, kuch naya?"),
        ("Meera", "Kuch khaas nahi"),
    ]

    for sender, content in extra_messages:
        result.append({
            "sender": sender,
            "speaker": sender,
            "content": content,
        })

    return result


def print_detection(result):
    print("Status:", result.get("status"))
    print("Death-zone score:", result.get("death_zone_score"))
    print("Confidence:", result.get("confidence"))
    print("Engagement change:", result.get("engagement_change"))
    print("Is death zone:", is_death_zone(result))


def run_test(title, messages, db, requesting_user="Aarav"):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print("Message count:", len(messages))

    detection = analyze_death_zone(messages)

    print("\n--- DEATH-ZONE DETECTION ---")
    print_detection(detection)

    print("\n--- RUNNING LANGGRAPH ---")

    result = run_conversation_workflow(
        db=db,
        requesting_user_id=1,
        requesting_user=requesting_user,
        messages=messages,
    )

    should_generate = result.get("should_generate", False)
    suggestion_result = result.get("suggestion_result")

    print("\n--- GRAPH RESULT ---")
    print("Should generate suggestions:", should_generate)
    print("Graph error:", result.get("error"))

    if should_generate:
        assert suggestion_result, (
            "Graph decided to generate suggestions, "
            "but no suggestion result was returned."
        )

        suggestions = suggestion_result.get("suggestions", [])

        assert len(suggestions) == 3, (
            f"Expected 3 suggestions, got {len(suggestions)}"
        )

        styles = {
            item.get("style")
            for item in suggestions
        }

        expected_styles = {"natural", "playful", "thoughtful"}

        assert styles == expected_styles, (
            f"Expected styles {expected_styles}, got {styles}"
        )

        print("\n--- CONVERSATION ANALYSIS ---")
        print(suggestion_result.get("analysis"))

        print("\n--- GENERATED SUGGESTIONS ---")

        for index, suggestion in enumerate(suggestions, start=1):
            print(f"{index}. [{suggestion.get('style', 'unknown')}]")
            print(suggestion.get("message", ""))
            print()

        print("RESULT: PASS - suggestions generated and validated")
        return True

    else:
        assert suggestion_result is None, (
            "Graph skipped generation but suggestion_result was not None."
        )

        print("No suggestions generated because the graph skipped this step.")
        print("RESULT: PASS - graph followed the skip route")
        return True


def main():
    messages = parse_conversation(conversation)
    low_engagement_messages = make_low_engagement_conversation(messages)

    print("Original conversation messages:", len(messages))
    print("Low-engagement scenario messages:", len(low_engagement_messages))

    results = []

    db = SessionLocal()

    try:
        # Test A: Original conversation
        results.append(
            (
                "Original conversation",
                run_test(
                    "TEST A: ORIGINAL CONVERSATION",
                    messages,
                    db,
                ),
            )
        )

        # Test B: Conversation followed by short replies
        results.append(
            (
                "Low-engagement conversation",
                run_test(
                    "TEST B: LOW-ENGAGEMENT CONVERSATION",
                    low_engagement_messages,
                    db,
                ),
            )
        )

    except Exception as exc:
        print("\nLIVE TEST FAILED")
        print(f"{type(exc).__name__}: {exc}")
        raise

    finally:
        db.close()

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    for name, passed in results:
        print(f"{name}: {'PASS' if passed else 'FAIL'}")

    print(f"Total passed: {sum(passed for _, passed in results)}/{len(results)}")


if __name__ == "__main__":
    main()

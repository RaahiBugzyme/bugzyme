
from app.ai.suggestions import suggest_next_messages
from app.database import SessionLocal


def run_test(language, conversation, user_name):
    print("\n" + "=" * 70)
    print(f"TEST: {language.upper()} CONVERSATION")
    print("=" * 70)

    messages = [
        {"sender": sender, "content": content}
        for sender, content in conversation
    ]

    print(f"Total messages: {len(messages)}")
    print("\n--- FULL CONVERSATION ---")

    for i, (sender, content) in enumerate(conversation, start=1):
        print(f"{i:02d}. {sender}: {content}")

    print("\n--- GENERATING SUGGESTIONS ---")

    db = None

    try:
        # Create a real database session.
        db = SessionLocal()

        result = suggest_next_messages(
            db=db,
            requesting_user_id=1,
            requesting_user=user_name,
            messages=messages,
        )

        print("\n--- GENERATED SUGGESTIONS ---")

        if isinstance(result, dict):
            suggestions = result.get("suggestions", result)
        else:
            suggestions = result

        if not suggestions:
            raise AssertionError("No suggestions returned.")

        if not isinstance(suggestions, list):
            raise AssertionError(
                f"Expected a list of suggestions, got "
                f"{type(suggestions).__name__}"
            )

        for index, item in enumerate(suggestions, start=1):
            if not isinstance(item, dict):
                raise AssertionError(
                    f"Suggestion {index} is not a dictionary."
                )

            print(f"\n{index}. [{item.get('style', 'unknown')}]")
            print(item.get("message", item.get("text", "")))

        styles = {
            item.get("style")
            for item in suggestions
        }

        expected = {"natural", "playful", "thoughtful"}

        if len(suggestions) != 3:
            raise AssertionError(
                f"Expected 3 suggestions, got {len(suggestions)}"
            )

        if styles != expected:
            raise AssertionError(
                f"Expected styles {expected}, got {styles}"
            )

        print(f"\nRESULT: {language.upper()} PASS")
        return True

    except Exception as exc:
        print(f"\nRESULT: {language.upper()} FAIL")
        print(f"Error: {type(exc).__name__}: {exc}")
        return False

    finally:
        # Always close the session, even if generation fails.
        if db is not None:
            db.close()


ENGLISH_CONVERSATION = [
    ("Alex", "Hey, how was your day?"),
    ("Maya", "Pretty tiring, honestly. Had back-to-back meetings."),
    ("Alex", "That sounds exhausting. Did you get any breaks?"),
    ("Maya", "Barely got time to grab lunch 😂"),
    (
        "Alex",
        "Your lunch deserves an award for surviving that schedule."
    ),
    (
        "Maya",
        "Haha, it was just a sandwich, but thanks for the support."
    ),
    ("Alex", "Sandwiches can be heroes too."),
    ("Maya", "Clearly! What do you usually do after a long day?"),
    (
        "Alex",
        "Usually music, a little walk, or something funny to watch."
    ),
    (
        "Maya",
        "I tried watching a comedy yesterday, but nothing was funny."
    ),
    ("Alex", "Maybe your comedy standards are too high."),
    (
        "Maya",
        "Or maybe I just need someone with better recommendations 😂"
    ),
]


HINGLISH_CONVERSATION = [
    ("Aarav", "Hey, aaj ka din kaisa tha?"),
    ("Meera", "Yaar kaafi tiring tha, office mein bahut kaam tha."),
    ("Aarav", "Oof, break mila ya poora din bas kaam hi kiya?"),
    ("Meera", "Lunch bhi desk pe hi kiya 😂"),
    ("Aarav", "Ye toh lunch ke saath injustice ho gaya."),
    (
        "Meera",
        "Hahaha exactly, aaram se khana bhi naseeb nahi hua."
    ),
    ("Aarav", "Ab ghar aake kya plan hai, madam?"),
    (
        "Meera",
        "Bas kuch dekhungi ya music sunungi, mood pe depend karta hai."
    ),
    (
        "Aarav",
        "Nice, comfort show ya music dono kaafi solid options hain."
    ),
    ("Meera", "Kal comedy try ki thi but kuch bhi funny nahi laga."),
    (
        "Aarav",
        "Lagta hai aaj tumhe hasana difficult challenge hai 😂"
    ),
    (
        "Meera",
        "Haan yaar, ab koi genuinely funny recommendation do."
    ),
]


if __name__ == "__main__":
    results = []

    results.append(
        run_test(
            "English",
            ENGLISH_CONVERSATION,
            "Alex",
        )
    )

    results.append(
        run_test(
            "Hinglish",
            HINGLISH_CONVERSATION,
            "Aarav",
        )
    )

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"English:  {'PASS' if results[0] else 'FAIL'}")
    print(f"Hinglish: {'PASS' if results[1] else 'FAIL'}")
    print(f"Total passed: {sum(results)}/2")

    if not all(results):
        raise SystemExit(1)

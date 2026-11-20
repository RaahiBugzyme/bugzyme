
from app.database import SessionLocal
from app.ai.personalization import suggest_next_messages

USER_ID = 1
USER_NAME = "Aarav"

MESSAGES = [
    {"sender": "Aarav", "content": "Hey, how was your day?"},
    {"sender": "Meera", "content": "Pretty good! Work was a little busy."},
    {"sender": "Aarav", "content": "Achha, busy day ke baad relax kaise karti ho?"},
    {"sender": "Meera", "content": "Usually music sunti hoon ya koi show dekhti hoon."},
]


def main():
    db = SessionLocal()

    try:
        print("\n=== GENERATING PERSONALIZED SUGGESTIONS ===")

        result = suggest_next_messages(
            db=db,
            requesting_user_id=USER_ID,
            requesting_user=USER_NAME,
            messages=MESSAGES,
        )

        analysis = result.get("analysis", {})
        memories = result.get("memories_used", [])
        suggestions = result.get("suggestions", [])

        print("\n=== CONVERSATION ANALYSIS ===")
        print(analysis)

        print("\n=== RELEVANT MEMORIES ===")
        print(memories)

        print("\n=== AI SUGGESTIONS ===")
        for suggestion in suggestions:
            print(
                f"[{suggestion.get('style')}] "
                f"{suggestion.get('message')}"
            )

        assert len(suggestions) == 3, (
            f"Expected 3 suggestions, got {len(suggestions)}"
        )

        expected_styles = {"natural", "playful", "thoughtful"}
        actual_styles = {item.get("style") for item in suggestions}

        assert actual_styles == expected_styles, (
            f"Unexpected suggestion styles: {actual_styles}"
        )

        print("\nPASS: Exactly 3 suggestions with all required styles.")

    finally:
        db.close()
        print("\nDatabase connection closed.")


if __name__ == "__main__":
    main()

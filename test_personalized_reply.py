from app.database import SessionLocal
from app.ai.personalization import (
    build_personalized_context,
    generate_personalized_reply,
)

USER_ID = 1
QUERY = "What sports do I like?"


def main():
    db = SessionLocal()

    try:
        # Step 1: Retrieve relevant memories.
        print("\n=== STEP 1: RETRIEVING MEMORIES ===")

        context = build_personalized_context(
            db=db,
            user_id=USER_ID,
            message=QUERY,
        )

        print("\n=== RETRIEVED PERSONALIZED CONTEXT ===")
        print(context)

        # Step 2: Generate a personalized reply.
        print("\n=== STEP 2: GENERATING AI REPLY ===")
        print("Sending context and query to the AI model...")

        reply = generate_personalized_reply(
            context=context,
            message=QUERY,
        )

        print("\n=== PERSONALIZED AI REPLY ===")
        print(reply)

    except Exception as exc:
        print(f"\nERROR: {type(exc).__name__}: {exc}")
        raise

    finally:
        db.close()
        print("\nDatabase connection closed.")


if __name__ == "__main__":
    main()

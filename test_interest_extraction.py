
from groq import BadRequestError
from test_conversation import conversation
from app.ai.interest_extraction import extract_interests


def main():
    print("Extracting interests from the test conversation...\n")

    try:
        interests = extract_interests(conversation)
    except BadRequestError as exc:
        print("Groq rejected the extraction request.")
        print(exc)
        return
    except Exception as exc:
        print(f"Extraction failed: {type(exc).__name__}: {exc}")
        return

    if not isinstance(interests, dict):
        print("Error: expected a dictionary from extract_interests().")
        return

    for key, label in [
        ("user_1_interests", "Aarav / User 1"),
        ("user_2_interests", "Meera / User 2"),
    ]:
        values = interests.get(key, [])

        print(f"\n=== {label} ===")

        if not isinstance(values, list):
            print("Invalid interest list returned.")
            continue

        if not values:
            print("No interests extracted.")
            continue

        for interest in values:
            if isinstance(interest, str) and interest.strip():
                print(f"- {interest.strip()}")

    print("\nExtraction-only test completed.")
    print("No database records were saved or modified.")


if __name__ == "__main__":
    main()

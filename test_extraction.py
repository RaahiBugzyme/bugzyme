

from app.ai.extraction import extract_memories
from test_conversation import conversation


def main():
    memories = extract_memories(conversation)

    print(f"\nTotal memories extracted: {len(memories)}")
    print("\n=== EXTRACTED MEMORIES ===")

    for i, memory in enumerate(memories, start=1):
        print(f"\n{i}. [{memory['memory_type']}]")
        print(f"   Memory: {memory['memory_text']}")
        print(f"   Confidence: {memory['confidence']}")


if __name__ == "__main__":
    main()

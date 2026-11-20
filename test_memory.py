from app.database import SessionLocal
from app.ai.memory import save_memory, search_memories

db = SessionLocal()

try:
    memory = save_memory(
        db=db,
        user_id=1,
        memory_text="Sandeep prefers casual conversations and simple questions.",
        memory_type="preference",
    )

    print("Saved memory:", memory.memory_text)

    results = search_memories(
        db=db,
        user_id=1,
        query="What communication style does Sandeep prefer?",
    )

    print("\nSearch results:")

    for result in results:
        print(result)

finally:
    db.close()
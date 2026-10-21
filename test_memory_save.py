
from app.database import SessionLocal
from app.ai.memory import save_memory
from app.models import UserMemory

db = SessionLocal()

try:
    # Use an existing test user ID from your database.
    TEST_USER_ID = 1
    TEST_TEXT = "Testing duplicate memory prevention."

    first = save_memory(
        db=db,
        user_id=TEST_USER_ID,
        memory_text=TEST_TEXT,
        memory_type="general",
        confidence=0.9,
    )

    second = save_memory(
        db=db,
        user_id=TEST_USER_ID,
        memory_text=TEST_TEXT,
        memory_type="general",
        confidence=0.9,
    )

    count = (
        db.query(UserMemory)
        .filter(
            UserMemory.user_id == TEST_USER_ID,
            UserMemory.memory_text.ilike(TEST_TEXT),
        )
        .count()
    )

    print("First memory ID:", first.id)
    print("Second memory ID:", second.id)
    print("Matching database records:", count)

finally:
    db.close()

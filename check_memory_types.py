
from app.database import SessionLocal
from app.models import UserMemory

def main():
    db = SessionLocal()

    try:
        memories = (
            db.query(UserMemory)
            .filter(UserMemory.user_id == 1)
            .order_by(UserMemory.id)
            .all()
        )

        for memory in memories:
            print(
                f"ID: {memory.id} | "
                f"Type: {memory.memory_type} | "
                f"Text: {memory.memory_text}"
            )
    finally:
        db.close()

if __name__ == "__main__":
    main()

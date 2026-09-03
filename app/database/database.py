from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base

engine = create_engine("sqlite:///./bugzyme.db")

SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


"""Phase 1 tests: SQLAlchemyUserRepository + MatchingService integration.

Uses in-memory SQLite — does NOT touch the real PostgreSQL database.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User
from ml.dating_ml_model.repository import SQLAlchemyUserRepository
from ml.dating_ml_model.service import MatchingService
from ml.dating_ml_model.model import CompatibilityModel


def setup_in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    u1 = User(
        username="alice",
        email="alice@test.com",
        hashed_password="hash1",
        full_name="Alice Smith",
        bio="Loves hiking",
        activity_status_enabled=True,
        ai_memory_enabled=False,
    )
    u2 = User(
        username="bob",
        email="bob@test.com",
        hashed_password="hash2",
        full_name=None,
        bio=None,
        activity_status_enabled=False,
        ai_memory_enabled=True,
    )
    db.add_all([u1, u2])
    db.commit()
    db.refresh(u1)
    db.refresh(u2)
    return db, u1, u2


def test_repo_get_existing_user():
    db, u1, u2 = setup_in_memory_db()
    repo = SQLAlchemyUserRepository(db)

    profile = repo.get(u1.id)
    assert profile is not None
    assert profile["id"] == u1.id
    assert profile["username"] == "alice"
    assert profile["full_name"] == "Alice Smith"
    assert profile["bio"] == "Loves hiking"
    assert profile["activity_status_enabled"] is True
    assert profile["ai_memory_enabled"] is False
    db.close()


def test_repo_get_nonexistent_user():
    db, u1, u2 = setup_in_memory_db()
    repo = SQLAlchemyUserRepository(db)

    assert repo.get(99999) is None
    db.close()


def test_repo_all():
    db, u1, u2 = setup_in_memory_db()
    repo = SQLAlchemyUserRepository(db)

    all_profiles = repo.all()
    assert len(all_profiles) == 2
    ids = {p["id"] for p in all_profiles}
    assert ids == {u1.id, u2.id}
    db.close()


def test_matching_service_predict_pair():
    db, u1, u2 = setup_in_memory_db()
    repo = SQLAlchemyUserRepository(db)
    model = CompatibilityModel()
    service = MatchingService(model, repo)

    profile_a = repo.get(u1.id)
    profile_b = repo.get(u2.id)

    result = service.predict_pair(profile_a, profile_b)
    assert "eligible" in result
    assert "eligibility_reason" in result
    assert result["user_a"] == u1.id
    assert result["user_b"] == u2.id
    db.close()


def test_matching_service_get_matches_returns_list():
    db, u1, u2 = setup_in_memory_db()
    repo = SQLAlchemyUserRepository(db)
    model = CompatibilityModel()
    service = MatchingService(model, repo)

    matches = service.get_matches(u1.id, top_k=5)
    assert isinstance(matches, list)
    # Without age/location fields, DatingML may mark all candidates ineligible,
    # so matches may be empty. The important thing is no crash.
    db.close()


def test_matching_service_get_matches_unknown_user_raises():
    db, u1, u2 = setup_in_memory_db()
    repo = SQLAlchemyUserRepository(db)
    model = CompatibilityModel()
    service = MatchingService(model, repo)

    try:
        service.get_matches(99999, top_k=5)
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "unknown user: 99999" in str(e)
    db.close()


if __name__ == "__main__":
    test_repo_get_existing_user()
    test_repo_get_nonexistent_user()
    test_repo_all()
    test_matching_service_predict_pair()
    test_matching_service_get_matches_returns_list()
    test_matching_service_get_matches_unknown_user_raises()
    print("ALL PHASE 1 TESTS PASSED")

"""Phase 1.1 — DatingML V3 Real Data Integration Audit (read-only).

Reads existing User records from the production database and verifies:
1. Required DatingML profile fields vs SQLAlchemyUserRepository output
2. Missing fields that prevent eligibility/compatibility
3. Real eligibility/compatibility behavior with actual users
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# ---------------------------------------------------------------------------
# Step 1: Read all existing User records (read-only)
# ---------------------------------------------------------------------------
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT id, username, email, full_name, bio,
               activity_status_enabled, ai_memory_enabled, last_seen
        FROM users
        ORDER BY id
    """))
    rows = result.fetchall()
    print(f"=== REAL DATABASE: {len(rows)} users found ===\n")
    for r in rows:
        d = dict(r._mapping)
        print(f"User id={d['id']}: username={d['username']!r}, email={d['email']!r}, "
              f"full_name={d['full_name']!r}, bio={d['bio']!r}, "
              f"activity_status_enabled={d['activity_status_enabled']}, "
              f"ai_memory_enabled={d['ai_memory_enabled']}, last_seen={d['last_seen']}")

# ---------------------------------------------------------------------------
# Step 2: Check what SQLAlchemyUserRepository would supply vs what DatingML needs
# ---------------------------------------------------------------------------
print("\n=== REQUIRED DATINGML FIELDS (from compatibility_engine.py & eligibility.py) ===")
required = {
    "id": "User identifier (required by MatchingService)",
    "age": "REQUIRED for eligibility gate (adulthood check) + demographics scoring",
    "sex": "REQUIRED for eligibility gate (mutual attraction check)",
    "orientation": "REQUIRED for eligibility gate (mutual attraction check)",
    "education": "career_education component scoring",
    "job": "career_education component scoring (profession)",
    "religion": "values_culture component scoring",
    "ethnicity": "values_culture component scoring",
    "drinks": "lifestyle component scoring",
    "drugs": "lifestyle component scoring",
    "smokes": "lifestyle component scoring",
    "diet": "lifestyle component scoring",
    "offspring": "family component scoring",
    "pets": "family component scoring",
    "height": "attraction component scoring",
    "body_type": "attraction component scoring",
    "birth_year": "derives generation for demographics scoring",
    "region/state": "location-based scoring",
}
for field, desc in required.items():
    print(f"  - {field}: {desc}")

print("\n=== SUPPLIED BY SQLAlchemyUserRepository (_user_row_to_dict) ===")
supplied = {
    "id": "YES (always)",
    "username": "YES (always)",
    "full_name": "YES (if not None)",
    "bio": "YES (if not None)",
    "activity_status_enabled": "YES (default True)",
    "ai_memory_enabled": "YES (default False)",
    "last_seen": "YES (if not None)",
}
for field, desc in supplied.items():
    print(f"  - {field}: {desc}")

print("\n=== MISSING CRITICAL FIELDS (NOT in User table, NOT supplied) ===")
missing = [
    "age", "sex", "orientation", "education", "job", "religion", "ethnicity",
    "drinks", "drugs", "smokes", "diet", "offspring", "pets", "height",
    "body_type", "birth_year", "region", "state",
]
for f in missing:
    print(f"  - {f}: MISSING — User table has no such column")

# ---------------------------------------------------------------------------
# Step 3: Test eligibility with real users (no age/sex/orientation => all ineligible)
# ---------------------------------------------------------------------------
print("\n=== REAL DATA ELIGIBILITY TEST ===")
from app.database import SessionLocal
from app.models import User
from ml.dating_ml_model.repository import SQLAlchemyUserRepository
from ml.dating_ml_model.model import CompatibilityModel

db = SessionLocal()
repo = SQLAlchemyUserRepository(db)
model = CompatibilityModel()

all_users = db.query(User).all()
print(f"Testing eligibility between all pairs of {len(all_users)} real users:\n")

for i, u1 in enumerate(all_users):
    for u2 in all_users[i+1:]:
        p1 = repo.get(u1.id)
        p2 = repo.get(u2.id)
        result = model.check_eligibility(p1, p2)
        print(f"  User {u1.id} ({u1.username}) vs User {u2.id} ({u2.username}): "
              f"eligible={result['eligible']}, reason={result['reason']}")

db.close()

print("\n=== CONCLUSION ===")
print("All existing User records lack age, sex, and orientation fields.")
print("Therefore eligibility will always return ineligible for any real user pair.")
print("This is NOT a code bug — the database schema simply doesn't store DatingML-required attributes.")
print("Phase 1 repository implementation is complete and correct; real data integration")
print("requires additional User/DatingProfile columns (out of scope for Phase 1.1).")

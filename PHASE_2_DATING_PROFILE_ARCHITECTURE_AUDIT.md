# PHASE_2_DATING_PROFILE_ARCHITECTURE_AUDIT

**Repository:** `/Users/sandeepsharma/Desktop/bugzyme-new`  
**Status:** Architecture audit — read-only, no code changes  
**Prerequisites completed:** Phase 1 (SQLAlchemyUserRepository), Phase 1.1 (real-data audit)  
**Repository tests:** 6/6 passed  
**Endpoint tests:** 5/5 passed  

---

## 1. Existing Architecture Findings

### 1.1 Application Stack
- **Framework:** FastAPI (single `app/main.py` file, ~2,574 lines)
- **Database:** SQLAlchemy 2.0 with Alembic migrations, PostgreSQL (Neon)
- **Auth:** JWT Bearer token via `OAuth2PasswordBearer`, `SECRET_KEY` from env
- **CORS:** Configured with `ALLOWED_ORIGINS` env variable
- **WebSocket:** `/ws` and `/ws/{chat_id}` with JWT token query param auth

### 1.2 Existing Database Models (`app/models.py`)

| Model | Table | Key Columns | Relationships |
|-------|-------|-------------|---------------|
| `User` | `users` | `id`, `username`, `email`, `hashed_password`, `is_online`, `last_seen`, `full_name`, `bio`, `activity_status_enabled`, `ai_memory_enabled`, `ai_memory_processed_through_message_id` | `chats_as_user1`, `chats_as_user2`, `sent_messages` |
| `Chat` | `chats` | `id`, `user1_id`, `user2_id`, `deleted_by_user1`, `deleted_by_user2`, `notification_muted_by_user1`, `notification_muted_by_user2` | `user1`, `user2` |
| `Message` | `messages` | `id`, `chat_id`, `sender_id`, `content`, `created_at`, `is_delivered`, `is_read`, `is_deleted`, `message_type`, `audio_url`, `audio_duration`, `audio_mime_type`, `attachment_*` fields, `reaction_revision` | `sender`, `reactions` |
| `MessageReaction` | `message_reactions` | `id`, `message_id`, `user_id`, `reaction` (check constraint: 6 emojis), `created_at` | — |
| `Interaction` | `interactions` | `id`, `sender_id`, `receiver_id`, `interaction_type` (LIKE/PASS/SUPER_LIKE), `created_at` | — (unique constraint on sender_id+receiver_id+interaction_type) |
| `AIRecoveryIntervention` | `ai_recovery_interventions` | `id`, `chat_id`, `user_id`, `trigger_message_id`, `recovery_reason`, `strategy`, `status`, `outcome_json` | — |
| `AISuggestionRecord` | `ai_suggestion_records` | `id`, `intervention_id`, `chat_id`, `user_id`, `suggestion_hash`, `strategy`, `prompt_version`, `model_id` | — |

**Missing (confirmed by grep across entire codebase):** `DatingProfile`, `ProfilePhoto`, `Swipe`, `Match`, `VerificationRecord` — none of these exist anywhere.

### 1.3 Existing Schemas (`app/schemas.py`)
- `UserCreate`, `UserUpdate`, `UserPublic`, `UserResponse`, `Token`
- `ChatCreate`, `ChatResponse`, `ChatSummary`
- `MessageCreate`, `MessageResponse`, `MessageReactionResponse`, `MessageDelete`
- No dating-related schemas exist.

### 1.4 Authentication & Authorization
- **JWT:** `create_token(user_id)`, `decode_token(token)` (HS256, 24h TTL)
- **Dependency:** `get_current_user(token, db)` → returns `User` model or raises 401
- **Bearer scheme:** `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")`
- **Routes using auth:** `/login`, `/register`, `/me`, `/users`, `/chats`, `/messages/*`, `/upload-voice`, `/compatibility`, `/eligibility`, `/explanation`, WebSocket endpoints

### 1.5 DatingML V3 Integration (Existing)
- **Routes:** `GET /compatibility`, `GET /eligibility`, `GET /explanation` (lines 2394–2530 in `app/main.py`)
- **Repository:** `SQLAlchemyUserRepository` (Phase 1, already implemented in `ml/dating_ml_model/repository.py`)
- **Adapter:** `app/dating_ml_profile_adapter.py` — `user_to_datingml_profile(user)` converts `User` → DatingML profile dict
- **Service:** `MatchingService` in `ml/dating_ml_model/service.py`
- **Engine:** `CompatibilityEngine` in `ml/dating_ml_model/compatibility_engine.py` (14 components, 6 categories)
- **Eligibility:** `eligibility.py` — requires `age`, `sex`, `orientation` for mutual-attraction gate
- **Config:** `config.json` — model_version "2.1.0", min_age 18, component weights

**Critical finding:** All 29 production users lack `age`, `sex`, `orientation`, and all other DatingML-scored attributes. Every eligibility check returns `eligible=False` with `"Age unknown..."`.

### 1.6 Existing API Routes Summary

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/` | No | Health |
| GET | `/health` | No | Health |
| POST | `/register` | No | User registration |
| POST | `/login` | No | JWT login |
| GET | `/me` | Yes | Current user |
| GET | `/users` | Yes | List users |
| POST | `/chats` | Yes | Create chat |
| DELETE | `/chats/{chat_id}` | Yes | Delete chat |
| PATCH | `/chats/{chat_id}/mute` | Yes | Mute chat |
| GET | `/chats` | Yes | List chats |
| POST | `/messages` | Yes | Send message |
| DELETE | `/messages/{message_id}` | Yes | Delete message |
| GET | `/messages/{chat_id}` | Yes | Get messages |
| POST | `/chats/{chat_id}/attachments` | Yes | Upload attachment |
| POST | `/upload-voice` | Yes | Upload voice message |
| GET | `/attachments/{message_id}/content` | Yes | Get attachment content |
| POST | `/chats/{chat_id}/suggestions` | Yes | AI suggestions |
| GET | `/chats/{chat_id}/coach` | Yes | AI coach |
| GET | `/chats/{chat_id}/insights` | Yes | AI insights |
| POST | `/ai-suggestions/{id}/events` | Yes | AI feedback |
| WS | `/ws` | Yes | Global websocket |
| WS | `/ws/{chat_id}` | Yes | Chat websocket |
| GET | `/compatibility` | Yes | DatingML compatibility |
| GET | `/eligibility` | Yes | DatingML eligibility |
| GET | `/explanation` | Yes | DatingML explanation |
| GET | `/me/ai-memories` | Yes | AI memories |
| PATCH | `/me/ai-memories/{id}` | Yes | Update AI memory |
| DELETE | `/me/ai-memories/{id}` | Yes | Delete AI memory |

### 1.7 File Upload Pattern (`app/storage.py`)
- `save_upload(upload)` → returns `(key, filename, mime_type, size, message_type)`
- Validates extension, MIME type, file signature, max 25 MiB
- Stores with UUID hex key in `ATTACHMENT_STORAGE_DIR` (default: `storage/attachments`)
- `remove_attachment(storage_key)` for cleanup
- Allowed types: jpg, jpeg, png, webp, pdf, txt, doc, docx, xls, xlsx, zip

### 1.8 Alembic Migration History
| Revision | Description | Date | Strategy |
|----------|-------------|------|----------|
| `1d5280e25742` | add indexes on chats.user1/user2, messages.chat_id/sender_id | 2026-09-14 | Additive indexes |
| `6a4f2b8c91de` | add message attachment metadata | 2026-09-30 | Idempotent column add |
| `7c2f4a91d6b3` | add message_reactions table | 2026-10-05 | Idempotent create table + validation |
| `3d9e71b4c2a6` | add reaction_revision column | 2026-10-06 | Idempotent column add |

**Migration pattern:** All migrations are idempotent, use `inspect()` to check existing state, `if_not_exists=True` where supported, `pass` in downgrade for additive tables.

### 1.9 Naming Conventions
- Tables: lowercase plural (`users`, `chats`, `messages`, `interactions`, `message_reactions`)
- Columns: snake_case (`user1_id`, `interaction_type`, `created_at`)
- Models: PascalCase (`User`, `Chat`, `Interaction`)
- Constraints: `uq_<table>_<columns>`, `ck_<table>_<purpose>`, `ix_<table>_<column>`

## 2. Existing Models and Relationships

### 2.1 User Model Relationships
```python
User.chats_as_user1 → Chat (user1_id)
User.chats_as_user2 → Chat (user2_id)
User.sent_messages → Message (sender_id)
```

### 2.2 Interaction Model (Already Exists — Reusable for Swipes)
The `Interaction` table already stores LIKE/PASS/SUPER_LIKE with:
- `sender_id` → `users.id` (CASCADE)
- `receiver_id` → `users.id` (CASCADE)
- `interaction_type` (String(20), nullable=False)
- `created_at`
- Unique constraint: `(sender_id, receiver_id, interaction_type)`
- Indexes on `sender_id`, `receiver_id`, `interaction_type`, `created_at`

This can serve as the **Swipe** storage layer without creating a new table.

### 2.3 Chat Model (Already Exists — Reusable for Matches)
The `Chat` table already stores user pairs with:
- `user1_id`, `user2_id` (both FK to users.id, CASCADE)
- Unique constraint: `(user1_id, user2_id)` via `uq_chat_users`
- `find_chat(db, user1_id, user2_id)` helper exists in `app/main.py`

This can serve as the **Match → chat** link.

## 4. ProfilePhoto Schema
## 5. Swipe and Match Schemas
## 6. Verification Architecture
## 7. DatingML Integration Architecture
## 8. Complete API Contract Proposal
## 9. Profile Completion and Eligibility
## 10. Migration Strategy
## 11. Security and Privacy Considerations
## 12. Final Checklist

### For Phase 2 Approval:

- [ ] `DatingProfile` schema approved (field list, nullability)
- [ ] `ProfilePhoto` storage approach approved (local vs. S3)
- [ ] `Swipe` reuse of `Interaction` table approved
- [ ] Match table design approved (chat_id linkage)
- [ ] Verification model approved (pending/passed/failed/cancelled)
- [ ] API route prefix (`/api/v1/`) approved
- [ ] Migration naming convention approved
- [ ] Repository pattern (separate `SQLAlchemyDatingProfileRepository`) approved

### For Implementation:

- [ ] `app/models.py` — add `DatingProfile`, `ProfilePhoto`, `Match`, `VerificationRecord` + `User.dating_profile` relationship
- [ ] `app/schemas.py` — add all Pydantic schemas
- [ ] `ml/dating_ml_model/repository.py` — add `SQLAlchemyDatingProfileRepository`
- [ ] `app/dating_ml_profile_adapter.py` — add `dating_profile_to_datingml_profile()`
- [ ] `app/main.py` — add `from app.api_v1 import router as api_v1_router` + `app.include_router(api_v1_router)`
- [ ] `app/api_v1.py` — new file with all `/api/v1/*` routes
- [ ] 4 Alembic migration files
- [ ] Test all 6 repository tests pass
- [ ] Test all 5 endpoint tests pass
- [ ] Run `python -c "from app.main import app"` → `APP_IMPORT_OK`

### For Data Privacy:

- [ ] Ownership checks implemented on all profile CRUD routes
- [ ] Photo upload validation per `app/storage.py` patterns
- [ ] Verification status flow: pending → passed/failed/cancelled
- [ ] No sensitive data (DOB, exact location) exposed in public API
- [ ] Duplicate prevention: swipe unique constraint, match unique constraint

### For Code Quality:

- [ ] No circular imports (lazy imports where needed)
- [ ] All new code follows existing code style
- [ ] All new migrations are idempotent
- [ ] Existing routes fully preserved (no breaks)
- [ ] JWT authentication unchanged

### Success Criteria:

After Phase 2 implementation and testing:
1. `python -c "from app.main import app"` → `APP_IMPORT_OK`
2. All 6 repository unit tests pass
3. All 5 endpoint tests pass
4. Real-data audit: 29 users verified; eligibility now depends on actual profile data
5. New `/api/v1/*` routes functional with JWT auth
6. Existing routes (`/login`, `/register`, `/me`, `/chats`, `/messages/*`, `/compatibility`, `/eligibility`, `/explanation`) fully preserved
7. No breaking changes to AI, chat, or messaging functionality

### 11.1 Authentication
- All `/api/v1/*` routes require `get_current_user` (JWT Bearer)
- No unauthenticated access to dating profiles

### 11.2 Ownership Checks
- Profile create/update/delete: only for `current_user`
- Photo upload/delete: only photos owned by `current_user.dating_profile`
- Public profile read: any authenticated user can view another user's public profile
- Private fields (verification review notes, exact location) excluded from public response

### 11.3 Photo Upload Security
- Reuse `app/storage.py` validation (extension, MIME type, file signature, max size)
- Recommended: add image-specific limits (10 MiB max, dimensions validation)
- Store with UUID key, never client-provided filename
- Serve via dedicated endpoint with access control

### 11.4 Sensitive Data Protection
- `DatingProfilePublic` schema excludes: exact address, verification review notes, internal flags
- `is_face_verified`/`is_id_verified` flags are public (boolean only), verification records are private
- `date_of_birth` → age computed server-side, DOB not exposed in public API

### 11.5 Race Conditions
- Mutual-like match creation: use `db.commit()` within transaction; `IntegrityError` on unique constraint handles concurrent matches
- Photo primary flag: update all photos for profile in single transaction (set `is_primary=False` for all, then `True` for selected)

### 11.6 Duplicate Prevention
- Swipes: DB unique constraint on `(sender_id, receiver_id, interaction_type)`
- Matches: DB unique constraint on sorted `(user_a_id, user_b_id)`

### 11.7 Privacy by Default
- New users have `is_profile_public = True` by default (opt-in to visibility)
- Users can toggle `is_profile_public = False` to make profile visible only to matches
- Verification record details never exposed in public API responses

### 10.1 New Migration Files (Do Not Modify Existing)

| Migration | Description | Tables |
|-----------|-------------|--------|
| `xxxx_add_dating_profiles` | Create `dating_profiles` table | `dating_profiles` |
| `yyyy_add_profile_photos` | Create `profile_photos` table | `profile_photos` |
| `zzzz_add_matches_table` | Create `matches` table | `matches` |
| `wwww_add_verification_records` | Create `verification_records` table | `verification_records` |

### 10.2 Migration Pattern (Follow Existing Convention)

Each migration:
1. `upgrade()`: Idempotent — check `inspect(bind).has_table()` before `op.create_table()`
2. `downgrade()`: `pass` (additive only, never drop tables)
3. Use `sa.ForeignKey("users.id", ondelete="CASCADE")`
4. Use `sa.UniqueConstraint(...)` with explicit names
5. Use `sa.Index(...)` explicitly for query performance
6. Validate existing table shape if table already exists (like `7c2f4a91d6b3` does)

### 10.3 Existing Data
- 29 existing `User` records remain unchanged (no `dating_profiles` rows initially)
- No data migration needed
- New users create `DatingProfile` on demand

### 10.4 Rollback Strategy
- Downgrades are `pass` (safe, data-preserving)
- If rollback needed: drop new tables manually (they contain only new data)

### 9.1 Profile Completion (Application-Level Concept)

Completion % calculated from fields filled on `DatingProfile`:
- Required for eligibility: `date_of_birth`, `sex`, `orientation` (weighted heavily)
- Recommended: `city`, `education`, `job`, `height`, `body_type`
- Optional: `bio`, `full_name`, `religion`, `ethnicity`, `drinks`, `drugs`, `smokes`, `diet`, `offspring`, `pets`, `photos`

**Formula:** Weighted sum of non-null fields / total weight × 100.

### 9.2 DatingML Eligibility (Hard Gate)

Per `eligibility.py`:
1. Both users must have `age` ≥ 18 (derived from `date_of_birth`)
2. Mutual attraction: `is_attracted(a, b)` AND `is_attracted(b, a)` must both be `True`
3. `sex` and `orientation` must be known on both profiles

**Key insight:** A user can have 100% profile completion but still be ineligible if their sex/orientation doesn't mutually attract with a candidate. Completion ≠ eligibility.

### 9.3 Compatibility Score Confidence

Per `compatibility_engine.py`:
- `confidence_score` = evidence coverage ratio × 100
- `adjusted_score` = shrinkage toward neutral (50) based on confidence
- Missing attributes → `None` component scores → lower confidence

### 9.3 Compatibility Score Confidence (continued)

The compatibility engine uses **unknown-aware** handling: missing fields return `None` for component scores rather than `0.0`, and the confidence ratio (`evidence` count / total possible weight) determines how much the score shrinks toward the neutral baseline of 50. This means:

- A profile with 3 out of 14 components filled → `confidence_score` ≈ 21% (3/14 × 100)
- A profile with 10 out of 14 components filled → `confidence_score` ≈ 71% (10/14 × 100)
- A profile with all 14 components filled → `confidence_score` ≈ 100%

The `adjusted_score = confidence_ratio × compatibility_score + (1 - confidence_ratio) × 50` ensures that profiles with insufficient evidence don't produce misleading high scores.

### 9.3 Be Completion vs Eligibility

| Profile Completion | Eligibility Status | Reason |
|-------------------|-------------------|--------|
| 100% but missing `sex`/`orientation` | Ineligible | Mutual attraction cannot be verified |
| 80% with all required fields | Eligible (if mutual attraction) | Full eligibility gate satisfied |
| 50% with only `age`+`sex` | Partially eligible | Missing orientation blocks eligibility |

### 9.4 Age Validation

Per `eligibility.py` line 46-48: `clean_age(profile.get("age"))` must return a value ≥ 18. The `compute_age()` function from `date_of_birth` uses `reference_year - birth_year`. The config sets `min_age = 18`.

### 9.5 Sex and Orientation Logic

`_sex()` normalizes: `"m"`, `"male"`, `"man"` → `"m"`; `"f"`, `"female"`, `"woman"` → `"f"`.
`_orientation()` normalizes: `"straight"`, `"heterosexual"` → `"straight"`; `"gay"`, `"lesbian"` → `"gay"`; `"bisexual"` → `"bisexual"`.

`is_attracted(profile, other)` returns `True` only when both `sex` and `orientation` are known and the attraction logic matches:
- `bisexual` → always `True`
- `straight` → `sex != other_sex`
- Other orientations not explicitly handled → `None` (ineligible)

### 9.5 Completion Percentage Calculation

```python
COMPLETION_WEIGHTS = {
    "date_of_birth": 15,   # required for eligibility
    "sex": 15,             # required for eligibility
    "orientation": 15,     # required for eligibility
    "education": 5,
    "job": 5,
    "religion": 3,
    "ethnicity": 3,
    "drinks": 3,
    "drugs": 3,
    "smokes": 3,
    "diet": 3,
    "offspring": 3,
    "pets": 3,
    "height": 5,
    "body_type": 3,
    "city": 2,
    "state": 2,
    "country": 2,
    "match_era_preference": 2,
    "target_gender_preference": 2,
}

def compute_completion(profile_dict) -> int:
    filled = sum(COMPLETION_WEIGHTS.get(k, 0) for k in COMPLETION_WEIGHTS if profile_dict.get(k) is not None)
    return round(filled / sum(COMPLETION_WEIGHTS.values()) * 100)
```

All new routes under `/api/v1/` prefix, JWT Bearer auth required.

### 8.1 Profile Management

| Method | Route | Request Body | Response | Auth | Description |
|--------|-------|--------------|----------|------|-------------|
| POST | `/api/v1/profile` | `DatingProfileInput` | `DatingProfile` | Yes | Create profile (409 if exists) |
| GET | `/api/v1/profile/me` | — | `DatingProfile` | Yes | Get own profile (404 if none) |
| PUT | `/api/v1/profile/me` | `DatingProfileInput` (partial) | `DatingProfile` | Yes | Update own profile |
| GET | `/api/v1/profile/{user_id}` | — | `DatingProfilePublic` | Yes | Get public profile of another user |
| GET | `/api/v1/profile/completion` | — | `ProfileCompletion` | Yes | Get completion % + missing fields |

### 8.2 Profile Photos

| Method | Route | Request | Response | Auth | Description |
|--------|-------|---------|----------|------|-------------|
| POST | `/api/v1/profile/photos` | multipart `file` | `ProfilePhoto` | Yes | Upload photo (400 if no profile) |
| GET | `/api/v1/profile/photos` | — | `list[ProfilePhoto]` | Yes | List own photos |
| DELETE | `/api/v1/profile/photos/{photo_id}` | — | 204 | Yes | Delete own photo |
| PATCH | `/api/v1/profile/photos/{photo_id}/primary` | — | `ProfilePhoto` | Yes | Set as primary |

### 8.3 Swipe (Like/Pass)

| Method | Route | Request Body | Response | Auth | Description |
|--------|-------|--------------|----------|------|-------------|
| POST | `/api/v1/swipe` | `{target_user_id, action}` | `SwipeResponse` | Yes | Like/pass/superlike (409 if mutual → match created) |

### 8.4 Matches

| Method | Route | Response | Auth | Description |
|--------|-------|----------|------|-------------|
| GET | `/api/v1/matches` | `MatchesResponse` | Yes | List own matches |
| GET | `/api/v1/matches/{match_id}` | `MatchItem` | Yes | Get match detail |
| DELETE | `/api/v1/matches/{match_id}` | 204 | Yes | Unmatch (set status='unmatched') |

### 8.5 Verification

| Method | Route | Request | Response | Auth | Description |
|--------|-------|---------|----------|------|-------------|
| GET | `/api/v1/verification/status` | — | `VerificationStatus` | Yes | Get verification records + status |
| POST | `/api/v1/verification/face` | multipart `file` | `VerificationSubmission` | Yes | Submit face verification (pending) |
| POST | `/api/v1/verification/id` | multipart `id_type`, `file` | `VerificationSubmission` | Yes | Submit ID verification (pending) |

### 8.6 Request/Response Schemas (Pydantic)

**DatingProfileInput:**
```python
class DatingProfileInput(BaseModel):
    date_of_birth: str | None       # ISO date
    sex: str                         # male/female/nonbinary/other/prefer_not_to_say
    orientation: str                 # straight/gay/bisexual
    full_name: str | None
    bio: str | None
    education: str | None
    job: str | None
    religion: str | None
    ethnicity: str | None
    drinks: str | None
    drugs: str | None
    smokes: str | None
    diet: str | None
    offspring: str | None
    pets: str | None
    height: float | None             # inches
    body_type: str | None
    city: str | None
    state: str | None
    country: str | None
    match_era_preference: str | None
    target_gender_preference: str | None
    behavioral_personalization_enabled: bool | None
```

**SwipeInput:**
```python
class SwipeInput(BaseModel):
    target_user_id: int
    action: Literal["like", "pass", "superlike"]
```

**ProfilePhoto:**
```python
class ProfilePhoto(BaseModel):
    id: int
    photo_url: str
    is_primary: bool
    display_order: int
```

**VerificationSubmission:**
```python
class VerificationSubmission(BaseModel):
    verification_id: int
    verification_type: str
    status: Literal["pending"]
    submitted_at: datetime
```

### 7.1 Data Flow

```
HTTP Request
    ↓
get_current_user (JWT auth) → User model
    ↓
DatingProfile query (joined with User)
    ↓
dating_profile_to_datingml_profile() adapter
    ↓ (profile dict with id, age, sex, orientation, education, job, etc.)
SQLAlchemyDatingProfileRepository (extends ProfileRepository)
    ↓
MatchingService(model=CompatibilityModel(), repository=repo)
    ↓
CompatibilityEngine.predict_pair() → eligibility + compatibility
    ↓
JSON response
```

### 7.2 Repository Strategy

**Option A: Extend `SQLAlchemyUserRepository`** — Add methods to read from `DatingProfile` table.

**Option B: New `SQLAlchemyDatingProfileRepository`** — Separate repository class implementing `ProfileRepository` (and optionally `RecommendationRepository`).

**Recommendation: Option B** — Clean separation. `SQLAlchemyUserRepository` continues to serve the legacy User-only path. New `SQLAlchemyDatingProfileRepository` reads from `DatingProfile` + `User` join, producing full DatingML profile dicts.

**Implementation:**
```python
class SQLAlchemyDatingProfileRepository(ProfileRepository, RecommendationRepository):
    def __init__(self, db: Session): ...
    def get(self, user_id):  # JOIN User + DatingProfile → profile dict
    def all(self):  # all profiles with dating data
    def get_interactions(self, user_id):  # from Interaction table
    def save_interaction(self, event):  # insert into Interaction table
    def get_blocked_user_ids(self, user_id):  # from Interaction where type='BLOCK'
    ...
```

### 7.3 Adapter: `dating_profile_to_datingml_profile()`

New function in `app/dating_ml_profile_adapter.py`:

```python
def dating_profile_to_datingml_profile(user, dating_profile) -> dict:
    """Convert User + DatingProfile to DatingML V3 profile dict."""
    profile = {
        "id": user.id,
        "username": user.username,
        # From DatingProfile:
        "age": compute_age(dating_profile.date_of_birth),
        "sex": dating_profile.sex,
        "orientation": dating_profile.orientation,
        "education": dating_profile.education,
        "job": dating_profile.job,
        "religion": dating_profile.religion,
        "ethnicity": dating_profile.ethnicity,
        "drinks": dating_profile.drinks,
        "drugs": dating_profile.drugs,
        "smokes": dating_profile.smokes,
        "diet": dating_profile.diet,
        "offspring": dating_profile.offspring,
        "pets": dating_profile.pets,
        "height": dating_profile.height,
        "body_type": dating_profile.body_type,
        "region": dating_profile.city or dating_profile.state,
        # From User (existing):
        "full_name": dating_profile.full_name or user.full_name,
        "bio": dating_profile.bio or user.bio,
        "activity_status_enabled": user.activity_status_enabled,
        "ai_memory_enabled": user.ai_memory_enabled,
    }
    return {k: v for k, v in profile.items() if v is not None}
```

### 7.4 Backward Compatibility
- Existing `/compatibility`, `/eligibility`, `/explanation` routes continue to use `SQLAlchemyUserRepository` + `user_to_datingml_profile()` (User-only path)
- New `/api/v1/*` routes use `SQLAlchemyDatingProfileRepository` + `dating_profile_to_datingml_profile()` (full profile path)
- No changes to DatingML scoring weights or logic

### 6.1 Existing Verification
**None exists.** No verification-related code, models, or routes found in the codebase.

### 6.2 Proposed VerificationRecord Table

| Column | Type | Nullable | Default | Rationale |
|--------|------|----------|---------|-----------|
| `id` | Integer PK | No | — | Primary key |
| `user_id` | Integer FK → users.id | No | — | Owner of verification |
| `verification_type` | String(20) | No | — | "face" or "id" |
| `status` | String(20) | No | 'pending' | pending/passed/failed/cancelled |
| `reviewed_at` | DateTime | Yes | — | When admin/system reviewed |
| `created_at` | DateTime | No | utcnow() | Submission timestamp |

**Constraints:**
- `fk_verification_records_user_id` → `users.id` (CASCADE)

**Important:** Uploading a photo does NOT automatically pass verification. Status starts as "pending" and requires review (manual or automated). `is_face_verified`/`is_id_verified` on `DatingProfile` are flags updated when a `VerificationRecord` reaches "passed" status.

### 5.1 Swipe — Reuse Existing `Interaction` Table

**No new table needed.** The existing `Interaction` model already stores swipes:
- `sender_id` → the user who swiped
- `receiver_id` → the user swiped on
- `interaction_type` (String(20)): "LIKE", "PASS", "SUPER_LIKE"
- `created_at`

**Constraints already present:**
- Unique: `(sender_id, receiver_id, interaction_type)` — prevents duplicate same-type swipes
- Indexes on `sender_id`, `receiver_id`, `interaction_type`, `created_at`

**Application logic needed:**
- "Pass" then "Like" on same user → both rows exist (different interaction_type), allowed
- Mutual like detection: query `Interaction` where `(sender_id=A, receiver_id=B, type='LIKE')` AND `(sender_id=B, receiver_id=A, type IN ('LIKE','SUPER_LIKE'))`

### 5.2 Match Table Definition

| Column | Type | Nullable | Default | Rationale |
|--------|------|----------|---------|-----------|
| `id` | Integer PK | No | — | Primary key |
| `chat_id` | Integer FK → chats.id | Yes | — | Links to existing Chat table |
| `user_a_id` | Integer FK → users.id | No | — | One side of match |
| `user_b_id` | Integer FK → users.id | No | — | Other side of match |
| `matched_at` | DateTime | No | utcnow() | When mutual like occurred |
| `status` | String(20) | No | 'active' | active/unmatched/blocked |
| `compatibility_score` | Integer | Yes | — | Denormalized from DatingML score |
| `compatibility_score_status` | String(30) | Yes | — | e.g. "legacy_placeholder" |

**Constraints:**
- `uq_matches_user_a_user_b` — unique on sorted pair (user_a_id < user_b_id enforced at app level)
- `fk_matches_chat_id` → `chats.id` (SET NULL on delete — match survives chat deletion)
- `fk_matches_user_a_id` → `users.id` (CASCADE)
- `fk_matches_user_b_id` → `users.id` (CASCADE)

**Relationships:**
- `Match.chat` → `Chat`
- `Match.user_a` → `User`
- `Match.user_b` → `User`

### 4.1 Table Definition
| Column | Type | Nullable | Default | Rationale |
|--------|------|----------|---------|-----------|
| `id` | Integer PK | No | — | Primary key |
| `dating_profile_id` | Integer FK → dating_profiles.id | No | — | Owned by dating profile |
| `photo_url` | String | No | — | Storage key or CDN URL (not local path) |
| `is_primary` | Boolean | No | False | Exactly one primary per profile |
| `display_order` | Integer | No | 0 | Ordering for photo carousel |
| `created_at` | DateTime | No | utcnow() | Upload timestamp |

**Constraints:**
- `fk_profile_photos_profile_id` → `dating_profiles.id` (CASCADE on delete)
- Check: only one `is_primary=True` per `dating_profile_id` (enforced at application level)

**Relationships:**
- `DatingProfile.photos` → `ProfilePhoto` (back_populates="profile")
- `ProfilePhoto.profile` → `DatingProfile` (back_populates="photos")

**Photo storage:** Reuse `app/storage.py` `save_upload()` pattern. Store UUID key; serve via `/uploads/profile/{key}` endpoint.
## 3. Proposed DatingProfile Schema

### Design Decision: Separate Table vs. Columns on User

**Recommendation:** Separate `dating_profiles` table with one-to-one relationship to `User`.

**Rationale:**
1. Keeps `User` table focused on authentication (unchanged)
2. Allows optional profile (not all users create dating profiles)
3. DatingProfile can have its own lifecycle (created, updated, completed, hidden)
4. Avoids schema bloat on the core User model
5. Clear separation of concerns: auth vs. dating domain

### 3.1 DatingProfile Table Definition

| Column | Type | Nullable | Default | Rationale |
|--------|------|----------|---------|-----------|
| `id` | Integer PK | No | — | Primary key |
| `user_id` | Integer FK → users.id | No | — | One-to-one, unique |
| `date_of_birth` | String | Yes | — | ISO date string; DatingML `clean_age()` converts to age. Preferred over `age` column because age changes daily; DOB is immutable source of truth. |
| `sex` | String(20) | No | — | Required for DatingML eligibility gate (`_sex()` normalizes "m"/"f"/"male"/"female") |
| `orientation` | String(20) | No | — | Required for DatingML eligibility gate (`_orientation()` normalizes "straight"/"gay"/"bisexual") |
| `full_name` | String(80) | Yes | — | Display name (may differ from `User.full_name`) |
| `bio` | Text | Yes | — | Dating profile bio |
| `education` | String(120) | Yes | — | DatingML `career_education` component (education_rank) |
| `job` | String(120) | Yes | — | DatingML `career_education` component (profession) |
| `religion` | String(80) | Yes | — | DatingML `values_culture` component |
| `ethnicity` | String(80) | Yes | — | DatingML `values_culture` component |
| `drinks` | String(50) | Yes | — | DatingML `lifestyle` component |
| `drugs` | String(50) | Yes | — | DatingML `lifestyle` component |
| `smokes` | String(50) | Yes | — | DatingML `lifestyle` component |
| `diet` | String(50) | Yes | — | DatingML `lifestyle` component |
| `offspring` | String(80) | Yes | — | DatingML `family` component |
| `pets` | String(80) | Yes | — | DatingML `family` component |
| `height` | Float | Yes | — | DatingML `attraction` component (inches, validated 48-96) |
| `body_type` | String(50) | Yes | — | DatingML `attraction` component |
| `city` | String(100) | Yes | — | DatingML location component |
| `state` | String(100) | Yes | — | DatingML location component |
| `country` | String(100) | Yes | — | DatingML location component |
| `match_era_preference` | String(20) | Yes | — | User's preferred generation era for matching |
| `target_gender_preference` | String(20) | Yes | — | User's preferred gender for matching |
| `behavioral_personalization_enabled` | Boolean | No | False | Opt-in for AI personalization |
| `is_face_verified` | Boolean | No | False | Verification flag |
| `is_id_verified` | Boolean | No | False | Verification flag |
| `verification_status` | String(20) | No | 'unverified' | unverified/pending/verified/rejected |
| `profile_completion_pct` | Integer | No | 0 | Computed/stored completion percentage |
| `is_profile_public` | Boolean | No | True | Profile visibility toggle |
| `created_at` | DateTime | No | utcnow() | Creation timestamp |
| `updated_at` | DateTime | Yes | onupdate=utcnow() | Last update timestamp |

**Constraints:**
- `uq_dating_profiles_user_id` — unique on `user_id`
- `fk_dating_profiles_user_id` → `users.id` (CASCADE on delete)

**Relationships:**
- `User.dating_profile` → `DatingProfile` (uselist=False, back_populates="user")
- `DatingProfile.user` → `User` (uselist=False, back_populates="dating_profile")
- `DatingProfile.photos` → `ProfilePhoto` (one-to-many, order by display_order)
- Foreign keys: `ondelete="CASCADE"` for user-related, `ondelete="SET NULL"` where appropriate
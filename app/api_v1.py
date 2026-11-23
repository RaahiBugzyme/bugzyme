# -----------------------------------------------------------------
#  FastAPI router for the /api/v1/ endpoints
# -----------------------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.database import get_db, get_current_user
from app.models import (
    User,
    DatingProfile,
    ProfilePhoto,
    Swipe,
    Match,
    VerificationRecord,
    Interaction,
)
from app.schemas import (
    # --- auth ---
    CurrentUserSchema,
    AuthTokenResult,
    AuthMessageResult,
    GoogleAuthUrlResult,
    # --- profile ---
    DatingProfileInput,
    DatingProfileSchema,
    ProfilePhotoSchema,
    # --- feed / search / swipe ---
    FeedProfileSchema,
    FeedResponseSchema,
    SwipeInput,
    SwipeResponseSchema,
    # --- matches ---
    MatchItemSchema,
    MatchesResponseSchema,
    # --- verification ---
    VerificationRecordSchema,
    VerificationStatusSchema,
    VerificationSubmissionSchema,
)


# -----------------------------------------------------------------
#  Helper – inline chat creation (same logic as POST /chats)
# -----------------------------------------------------------------
def _create_chat(db: Session, initiator_id: int, receiver_id: int) -> int:
    """Return the newly created chat id. Mirrors the existing
    `create_chat` route implementation exactly."""
    from app.main import find_chat  # lazy import – avoids circular import at module load

    # 1️⃣  Verify both users exist
    user_init = db.get(User, initiator_id)
    user_receiver = db.get(User, receiver_id)
    if not user_init or not user_receiver:
        raise HTTPException(status_code=404, detail="User not found")

    # 2️⃣  Look for an existing chat
    existing = find_chat(db, initiator_id, receiver_id)
    if existing:
        return existing.id

    # 3️⃣  Create a new chat row
    new_chat = models.Chat(
        user1_id=initiator_id,
        user2_id=receiver_id,
    )
    db.add(new_chat)
    try:
        db.commit()
    except Exception:
        db.rollback()
        existing = find_chat(db, initiator_id, receiver_id)
        if existing:
            return existing.id
        raise

    db.refresh(new_chat)
# -----------------------------------------------------------------
#  SWIPE
# -----------------------------------------------------------------
@router.post("/swipe", response_model=SwipeResponseSchema, status_code=201)
def do_swipe(
    payload: SwipeInput,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    # Record the swipe in the existing `interactions` table
    swipe = Interaction(
        user_id=current_user.id,
        target_user_id=payload.target_user_id,
        interaction_type=payload.action.upper(),
    )
    db.add(swipe)
    db.commit()
    db.refresh(swipe)

    # Mutual-like check – both directions must be "LIKE" or "SUPER_LIKE"
    opposite = db.execute(
        select(Interaction)
        .filter(
            Interaction.user_id == payload.target_user_id,
            Interaction.target_user_id == current_user.id,
            Interaction.interaction_type.in_(["LIKE", "SUPER_LIKE"]),
        )
    ).scalar_one_or_none()

    is_match = opposite is not None
    if is_match:
        # Create a chat using the exact same logic as POST /chats
        chat_id = _create_chat(db, current_user.id, payload.target_user_id)
        match = Match(
            user_id=current_user.id,
            target_user_id=payload.target_user_id,
            chat_id=chat_id,
        )
        db.add(match)
        db.commit()

    return SwipeResponseSchema(
        id=swipe.id,
        user_id=swipe.user_id,
        target_user_id=swipe.target_user_id,
        action=payload.action,
        created_at=swipe.created_at,
        is_match=is_match,
    )
# -----------------------------------------------------------------
#  MATCHES
# -----------------------------------------------------------------
@router.get("/matches", response_model=MatchesResponseSchema)
def list_matches(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(Match)
        .filter(
            (Match.user_id == current_user.id) | (Match.target_user_id == current_user.id)
        )
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    out = []
    for m in rows:
        other_id = m.target_user_id if m.user_id == current_user.id else m.user_id
        other_user = db.execute(select(User).filter(User.id == other_id)).scalar_one_or_none()

        matched_user_payload = {}
        if other_user:
            matched_user_payload = {
                "id": other_user.id,
                "username": other_user.username,
                "full_name": other_user.full_name,
                "bio": other_user.bio,
                "photo_url": None,
                "photos": [],
            }

        out.append(
            MatchItemSchema(
                id=m.id,
                chat_id=m.chat_id,
                matched_user=matched_user_payload,
                compatibility_score=m.compatibility_score or 0.0,
                compatibility_score_status="legacy_placeholder",
                profile_alignment=None,
                created_at=m.created_at,
                age=None,
                city=None,
                era=None,
                vibe_tag=None,
                profession=None,
                education=None,
                relationship_intentions=None,
                interests=None,
                photos=None,
            )
        )

    return MatchesResponseSchema(
        matches=out,
        total=len(out),
        limit=limit,
        offset=offset,
        has_more=False,
    )


@router.get("/matches/{match_id}", response_model=MatchItemSchema)
def get_match_detail(
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.execute(select(Match).filter(Match.id == match_id)).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")

    other_id = m.target_user_id if m.user_id == current_user.id else m.user_id
    other_user = db.execute(select(User).filter(User.id == other_id)).scalar_one_or_none()

    matched_user_payload = {}
    if other_user:
        matched_user_payload = {
            "id": other_user.id,
            "username": other_user.username,
            "full_name": other_user.full_name,
            "bio": other_user.bio,
            "photo_url": None,
            "photos": [],
        }

    return MatchItemSchema(
        id=m.id,
        chat_id=m.chat_id,
        matched_user=matched_user_payload,
        compatibility_score=m.compatibility_score or 0.0,
        compatibility_score_status="legacy_placeholder",
        profile_alignment=None,
        created_at=m.created_at,
        age=None,
        city=None,
        era=None,
        vibe_tag=None,
        profession=None,
        education=None,
        relationship_intentions=None,
        interests=None,
        photos=None,
    )
# -----------------------------------------------------------------
#  VERIFICATION
# -----------------------------------------------------------------
@router.get("/verification/status", response_model=VerificationStatusSchema)
def verification_status(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    records = db.execute(
        select(VerificationRecord).filter(VerificationRecord.user_id == current_user.id)
    ).scalars().all()

    is_face = any(r.verification_type == "face" for r in records)
    is_id = any(r.verification_type == "id" for r in records)

    current_status: str | None = None
    if records:
        current_status = records[0].status

    return VerificationStatusSchema(
        verifications=[VerificationRecordSchema.from_orm(r) for r in records],
        current_status=current_status,
        is_face_verified=is_face,
        is_id_verified=is_id,
        verification_available=True,
    )


@router.post("/verification/face", status_code=202)
def upload_face_verification(
    file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    rec = VerificationRecord(
        user_id=current_user.id,
        verification_type="face",
        status="pending",
        reviewed_at=None,
        attempt_count=1,
        created_at=func.now(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return VerificationSubmissionSchema(
        verification_id=rec.id,
        verification_type="face",
        status="pending",
        submitted_at=rec.created_at,
    )


@router.post("/verification/id", status_code=202)
def upload_id_verification(
    file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    id_type: str = "id_college",
):
    rec = VerificationRecord(
        user_id=current_user.id,
        verification_type="id",
        status="pending",
        reviewed_at=None,
        attempt_count=1,
        created_at=func.now(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return VerificationSubmissionSchema(
        verification_id=rec.id,
        verification_type="id",
        status="pending",
        submitted_at=rec.created_at,
    )
    return new_chat.id
router = APIRouter(prefix="/api/v1", tags=["v1"])
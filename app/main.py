"""Bugzyme backend: REST + WebSocket chat (Reply + Delete)."""

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    UploadFile,
    File,
    Form,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy import and_, or_, func, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool
from app.ai.graph import run_conversation_workflow
from app.ai.death_zone import analyze_death_zone, is_death_zone
from app.ai.targeting import analyze_participant_effort
from app.ai.recovery_strategy import PROMPT_VERSION
from app.ai.ai_evaluation import CLIENT_EVENTS, VALID_EVENTS, meaningful_response
from . import models, schemas
from . import storage as attachment_storage
from .connection_manager import ConnectionManager
from .database import Base, SessionLocal, engine, get_db

logger = logging.getLogger("bugzyme")

# ============================================================
# CONFIG
# ============================================================

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "Set the SECRET_KEY environment variable (32+ chars)."
    )

ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "24"))

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if o.strip()
]

IDLE_TIMEOUT = 70
ALLOWED_MESSAGE_REACTIONS = frozenset({"❤️", "😂", "👍", "🔥", "😮", "😢"})

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
manager = ConnectionManager()


# ============================================================
# GENERAL HELPERS
# ============================================================

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt):
    if dt is None:
        return None
    return dt.isoformat() + "Z"


# ============================================================
# APP
# ============================================================

def ensure_message_schema_columns(connection):
    """Add missing message metadata columns to an existing PostgreSQL table."""
    logger.info(
        "Checking message schema columns during startup (dialect=%s)",
        connection.dialect.name,
    )

    if connection.dialect.name != "postgresql":
        logger.info(
            "Skipping PostgreSQL message-schema check for dialect=%s",
            connection.dialect.name,
        )
        return

    statements = {
        "attachment_storage_key": (
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
            "attachment_storage_key VARCHAR(64) NULL"
        ),
        "attachment_name": (
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
            "attachment_name VARCHAR(255) NULL"
        ),
        "attachment_mime_type": (
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
            "attachment_mime_type VARCHAR(100) NULL"
        ),
        "attachment_size_bytes": (
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
            "attachment_size_bytes INTEGER NULL"
        ),
        "reaction_revision": (
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
            "reaction_revision INTEGER DEFAULT 0 NOT NULL"
        ),
        "read_at": (
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
            "read_at TIMESTAMP NULL"
        ),
    }

    try:
        existing = {
            column["name"]
            for column in inspect(connection).get_columns("messages")
        }
        missing = [name for name in statements if name not in existing]

        if missing:
            logger.warning(
                "Adding missing message schema columns to messages: %s",
                ", ".join(missing),
            )

            for name in missing:
                connection.exec_driver_sql(statements[name])

            connection.commit()
        else:
            logger.info(
                "All message schema columns already exist on messages"
            )

        remaining = {
            column["name"]
            for column in inspect(connection).get_columns("messages")
        }

        missing_after_check = [
            name for name in statements if name not in remaining
        ]

        if missing_after_check:
            raise RuntimeError(
                "Message schema columns still missing after startup check: "
                + ", ".join(missing_after_check)
            )

    except Exception:
        connection.rollback()
        logger.exception("Message schema startup check failed")
        raise

    logger.info("Message schema startup check passed")


def ensure_user_profile_columns(connection):
    """Add public profile fields to existing PostgreSQL user tables."""
    if connection.dialect.name != "postgresql":
        return
    statements = {
        "full_name": "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(80) NULL",
        "bio": "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT NULL",
        "ai_memory_enabled": "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_memory_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ai_memory_processed_through_message_id": "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_memory_processed_through_message_id INTEGER NULL",
        "activity_status_enabled": "ALTER TABLE users ADD COLUMN IF NOT EXISTS activity_status_enabled BOOLEAN NOT NULL DEFAULT TRUE",
    }
    existing = {column["name"] for column in inspect(connection).get_columns("users")}
    missing = [name for name in statements if name not in existing]
    try:
        for name in missing:
            connection.exec_driver_sql(statements[name])
        if missing:
            connection.commit()
        remaining = {column["name"] for column in inspect(connection).get_columns("users")}
        missing_after_check = [name for name in statements if name not in remaining]
        if missing_after_check:
            raise RuntimeError("User profile columns still missing after startup check: " + ", ".join(missing_after_check))
    except Exception:
        connection.rollback()
        logger.exception("User profile schema startup check failed")
        raise


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)

    with engine.connect() as connection:
        ensure_message_schema_columns(connection)
        ensure_user_profile_columns(connection)

    with SessionLocal() as db:
        db.query(models.User).update(
            {models.User.is_online: False},
            synchronize_session=False
        )
        db.commit()

    yield


app = FastAPI(
    title="Bugzyme",
    lifespan=lifespan
)

# Voice upload folder
os.makedirs("uploads/voice", exist_ok=True)

# Serve uploaded voice files
app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)


@app.middleware("http")
async def catch_unhandled(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled error on %s %s",
            request.method,
            request.url.path
        )
        return JSONResponse(
            {"detail": "Internal server error"},
            status_code=500
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# AUTH
# ============================================================

def create_token(user_id: int):
    expire_time = datetime.now(timezone.utc) + timedelta(
        hours=TOKEN_TTL_HOURS
    )

    return jwt.encode(
        {
            "sub": str(user_id),
            "exp": expire_time
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def decode_token(token: str):
    try:
        return int(
            jwt.decode(
                token,
                SECRET_KEY,
                algorithms=[ALGORITHM]
            )["sub"]
        )
    except (JWTError, KeyError, ValueError, TypeError):
        return None


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user_id = decode_token(token)

    if user_id is None:
        raise HTTPException(
            401,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = db.get(models.User, user_id)

    if not user:
        raise HTTPException(401, "User not found")

    return user


# ============================================================
# CHAT HELPERS
# ============================================================

def other_user(chat: models.Chat, user_id: int):
    if chat.user1_id == user_id:
        return chat.user2_id
    return chat.user1_id


def member_chat(db: Session, chat_id: int, user_id: int):
    chat = db.get(models.Chat, chat_id)

    if chat and user_id in (
        chat.user1_id,
        chat.user2_id
    ):
        return chat

    return None


def find_chat(db: Session, user1_id: int, user2_id: int):
    return db.query(models.Chat).filter(
        or_(
            (models.Chat.user1_id == user1_id) &
            (models.Chat.user2_id == user2_id),

            (models.Chat.user1_id == user2_id) &
            (models.Chat.user2_id == user1_id)
        )
    ).first()

def get_partners(db: Session, user_id: int):
    chats = db.query(models.Chat).filter(
        or_(
            and_(
                models.Chat.user1_id == user_id,
                models.Chat.deleted_by_user1.is_(False)
            ),
            and_(
                models.Chat.user2_id == user_id,
                models.Chat.deleted_by_user2.is_(False)
            )
        )
    ).all()

    return {
        chat.id: other_user(chat, user_id)
        for chat in chats
    }
# ============================================================
# MESSAGE SAVE
# ============================================================

def save_message(
    db: Session,
    sender_id: int,
    chat_id: int,
    content: str,
    reply_to_id: int | None = None
):
    chat = member_chat(db, chat_id, sender_id)

    if not chat:
        return None

    # Validate reply
    if reply_to_id is not None:
        parent = db.get(models.Message, reply_to_id)

        if (
            not parent
            or parent.chat_id != chat_id
            or parent.is_deleted
        ):
            return None

    message = models.Message(
        chat_id=chat_id,
        sender_id=sender_id,
        content=content,
        created_at=utcnow(),
        is_delivered=False,
        is_read=False,
        is_deleted=False,
        reply_to_id=reply_to_id,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return {
        "id": message.id,
        "chat_id": chat_id,
        "sender_id": sender_id,
        "content": message.content,
        "created_at": iso(message.created_at),
        "read_at": iso(message.read_at),
        "is_delivered": False,
        "is_read": False,
        "is_deleted": False,
        "reply_to_id": message.reply_to_id,
        "receiver_id": other_user(chat, sender_id),
    }



def save_voice_message(
    db: Session,
    sender_id: int,
    chat_id: int,
    audio_url: str,
    audio_duration: int | None,
    audio_mime_type: str | None
):
    chat = member_chat(
        db,
        chat_id,
        sender_id
    )

    if not chat:
        return None

    message = models.Message(
        chat_id=chat_id,
        sender_id=sender_id,
        content=None,
        created_at=utcnow(),
        is_delivered=False,
        is_read=False,
        is_deleted=False,
        reply_to_id=None,

        message_type="voice",
        audio_url=audio_url,
        audio_duration=audio_duration,
        audio_mime_type=audio_mime_type,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return {
        "id": message.id,
        "chat_id": chat_id,
        "sender_id": sender_id,
        "content": None,
        "created_at": iso(message.created_at),
        "read_at": iso(message.read_at),
        "is_delivered": False,
        "is_read": False,
        "is_deleted": False,
        "reply_to_id": None,

        "message_type": "voice",
        "audio_url": message.audio_url,
        "audio_duration": message.audio_duration,
        "audio_mime_type": message.audio_mime_type,

        "receiver_id": other_user(
            chat,
            sender_id
        ),
    }


def save_attachment_message(
    db: Session,
    sender_id: int,
    chat_id: int,
    content: str | None,
    reply_to_id: int | None,
    storage_key: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    message_type: str,
):
    chat = member_chat(db, chat_id, sender_id)
    if not chat:
        return None

    if content is not None:
        content = content.strip()
        if len(content) > schemas.MAX_MESSAGE_LEN:
            return None
        content = content or None

    if reply_to_id is not None:
        parent = db.get(models.Message, reply_to_id)
        if not parent or parent.chat_id != chat_id or parent.is_deleted:
            return None

    message = models.Message(
        chat_id=chat_id,
        sender_id=sender_id,
        content=content,
        created_at=utcnow(),
        is_delivered=False,
        is_read=False,
        is_deleted=False,
        reply_to_id=reply_to_id,
        message_type=message_type,
        attachment_storage_key=storage_key,
        attachment_name=filename,
        attachment_mime_type=mime_type,
        attachment_size_bytes=size_bytes,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return {
        "id": message.id,
        "chat_id": chat_id,
        "sender_id": sender_id,
        "content": message.content,
        "created_at": iso(message.created_at),
        "read_at": iso(message.read_at),
        "is_delivered": message.is_delivered,
        "is_read": message.is_read,
        "is_deleted": message.is_deleted,
        "reply_to_id": message.reply_to_id,
        "message_type": message.message_type,
        "attachment_name": message.attachment_name,
        "attachment_mime_type": message.attachment_mime_type,
        "attachment_size_bytes": message.attachment_size_bytes,
        "receiver_id": other_user(chat, sender_id),
    }


# ============================================================
# MESSAGE DELETE
# ============================================================

def soft_delete_message(
    db: Session,
    user_id: int,
    message_id: int,
    for_everyone: bool = True
):
    message = db.get(models.Message, message_id)

    if not message or message.is_deleted:
        return None

    chat = member_chat(
        db,
        message.chat_id,
        user_id
    )

    if not chat:
        return None

    # Only sender can delete for everyone
    if for_everyone and message.sender_id != user_id:
        return None

    # Messages are soft-deleted, so explicitly remove their reactions.
    db.query(models.MessageReaction).filter(
        models.MessageReaction.message_id == message.id
    ).delete(synchronize_session=False)

    message.is_deleted = True
    message.deleted_at = utcnow()
    message.content = None

    db.commit()

    return {
        "message_id": message.id,
        "chat_id": message.chat_id,
        "sender_id": message.sender_id,
        "for_everyone": for_everyone,
        "receiver_id": other_user(chat, user_id),
        "attachment_storage_key": message.attachment_storage_key,
    }


def toggle_message_reaction(
    db: Session,
    user_id: int,
    chat_id: int,
    message_id: int,
    reaction: str,
):
    if reaction not in ALLOWED_MESSAGE_REACTIONS:
        return None

    chat = member_chat(db, chat_id, user_id)
    if not chat:
        return None

    # Lock the owning message before reading or changing a user's reaction.
    # This serializes all reaction mutations for this message in PostgreSQL.
    for attempt in range(2):
        message = (
            db.query(models.Message)
            .filter(
                models.Message.id == message_id,
                models.Message.chat_id == chat_id,
                models.Message.is_deleted.is_(False),
            )
            .with_for_update()
            .first()
        )
        if not message:
            return None

        current = db.query(models.MessageReaction).filter_by(
            message_id=message_id,
            user_id=user_id,
        ).first()

        if current and current.reaction == reaction:
            db.delete(current)
        elif current:
            current.reaction = reaction
            current.created_at = utcnow()
        else:
            db.add(models.MessageReaction(
                message_id=message_id,
                user_id=user_id,
                reaction=reaction,
                created_at=utcnow(),
            ))

        message.reaction_revision = (message.reaction_revision or 0) + 1
        try:
            db.commit()
            break
        except IntegrityError:
            # The message row lock serializes normal callers. Retrying once
            # also handles a concurrent insert from a legacy/unlocked caller;
            # the unique constraint remains the final guard.
            db.rollback()
            if attempt:
                raise

    # Generate the canonical snapshot only after the mutation is committed.
    # Re-locking the message keeps the revision and reaction rows stable while
    # they are read. A later update can still broadcast first; clients order
    # these committed snapshots by revision.
    snapshot_message = (
        db.query(models.Message)
        .filter(
            models.Message.id == message_id,
            models.Message.chat_id == chat_id,
            models.Message.is_deleted.is_(False),
        )
        .with_for_update()
        .first()
    )
    if not snapshot_message:
        return None

    reactions = db.query(models.MessageReaction).filter_by(
        message_id=message_id
    ).order_by(models.MessageReaction.user_id).all()
    revision = snapshot_message.reaction_revision or 0
    db.commit()

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "revision": revision,
        "receiver_id": other_user(chat, user_id),
        "reactions": [
            {"user_id": row.user_id, "reaction": row.reaction}
            for row in reactions
        ],
    }


# ============================================================
# CHAT DELETE
# ============================================================
def delete_chat_from_database(
    db: Session,
    chat_id: int,
    user_id: int
):
    chat = db.get(models.Chat, chat_id)

    if not chat:
        return None

    if user_id not in (
        chat.user1_id,
        chat.user2_id
    ):
        return None

    # Mark conversation as deleted only
    # for the current user's side.
    if chat.user1_id == user_id:
        chat.deleted_by_user1 = True
    else:
        chat.deleted_by_user2 = True

    # IMPORTANT:
    # Do NOT delete messages.
    # Do NOT delete the chat.
    db.commit()

    return {
        "chat_id": chat_id,
        "user_id": user_id,
        "other_user_id": other_user(chat, user_id)
    }
# ============================================================
# DELIVERY / READ
# ============================================================

def mark_delivered(db: Session, ids: list[int]):
    if not ids:
        return

    db.query(models.Message).filter(
        models.Message.id.in_(ids)
    ).update(
        {models.Message.is_delivered: True},
        synchronize_session=False
    )

    db.commit()


def mark_read(
    db: Session,
    user_id: int,
    chat_id: int,
    message_id: int | None
):
    chat = member_chat(
        db,
        chat_id,
        user_id
    )

    if not chat:
        return None

    query = db.query(models.Message).filter(
        models.Message.chat_id == chat_id,
        models.Message.sender_id == other_user(chat, user_id),
        models.Message.is_read.is_not(True),
        models.Message.is_deleted.is_not(True),
    )

    if message_id is not None:
        query = query.filter(
            models.Message.id == message_id
        )

    messages = query.all()

    for message in messages:
        message.is_read = True
        message.is_delivered = True
        message.read_at = utcnow()

    db.commit()

    return {
        "sender": other_user(chat, user_id),
        "ids": [message.id for message in messages],
        "read_at": {message.id: iso(message.read_at) for message in messages},
    }


# ============================================================
# ONLINE / OFFLINE
# ============================================================

def set_online(
    db: Session,
    user_id: int,
    online: bool
):
    user = db.get(models.User, user_id)

    if not user:
        return None

    online = bool(online and user.activity_status_enabled)
    was_online = bool(user.is_online)
    user.is_online = online

    if not online and was_online:
        user.last_seen = utcnow()

    db.commit()

    return {
        "is_online": online,
        "activity_status_enabled": bool(user.activity_status_enabled),
        "last_seen": iso(user.last_seen),
    }


def visible_online_ids(db: Session):
    connected_ids = manager.online_ids()
    if not connected_ids:
        return []
    return [row[0] for row in db.query(models.User.id).filter(
        models.User.id.in_(connected_ids),
        models.User.activity_status_enabled.is_(True),
    ).all()]


def load_context(
    db: Session,
    user_id: int,
    bound_chat_id: int | None
):
    user = db.get(models.User, user_id)

    if not user:
        return None

    partners = get_partners(db, user_id)

    if (
        bound_chat_id is not None
        and bound_chat_id not in partners
    ):
        return None

    # A user with no chats has no pending messages to load. Avoid using a
    # fabricated chat ID as an empty-result sentinel in the SQL query.
    if not partners:
        return {
            "username": user.username,
            "partners": partners,
            "delivered": [],
            "activity_status_enabled": user.activity_status_enabled,
        }

    query = db.query(models.Message).filter(
        models.Message.chat_id.in_(list(partners)),
        models.Message.sender_id != user_id,
        models.Message.is_delivered.is_not(True),
        models.Message.is_deleted.is_not(True),
    )

    if bound_chat_id is not None:
        query = query.filter(
            models.Message.chat_id == bound_chat_id
        )

    pending = query.all()

    for message in pending:
        message.is_delivered = True

    db.commit()

    return {
        "username": user.username,
        "partners": partners,
        "activity_status_enabled": user.activity_status_enabled,
        "delivered": [
            (
                message.sender_id,
                message.chat_id,
                message.id
            )
            for message in pending
        ]
    }


# ============================================================
# DATABASE ASYNC HELPER
# ============================================================

async def db_call(function, *args):
    def run():
        with SessionLocal() as db:
            return function(db, *args)

    return await run_in_threadpool(run)


# ============================================================
# WEBSOCKET HELPERS
# ============================================================

async def safe_send(
    websocket: WebSocket,
    payload: dict
):
    with contextlib.suppress(Exception):
        await websocket.send_json(payload)


async def broadcast_presence(
    user_id: int,
    status: str,
    last_seen=None,
    activity_status_enabled=None,
):
    payload = {
        "type": "presence",
        "user_id": user_id,
        "status": status,
        "last_seen": last_seen
    }
    if activity_status_enabled is not None:
        payload["activity_status_enabled"] = bool(activity_status_enabled)

    # Presence belongs to the user, not a chat. Send it to every connected
    # account so soft-deleted chats and chat-bound sockets cannot miss it.
    for recipient_id in manager.online_ids():
        await manager.send_to_user(
            recipient_id,
            payload
        )


# ============================================================
# BACKGROUND TASKS
# ============================================================

_bg_tasks = set()


def spawn(coro):
    task = asyncio.create_task(coro)

    _bg_tasks.add(task)

    task.add_done_callback(
        _bg_tasks.discard
    )


async def go_offline(user_id: int):
    try:
        if manager.is_online(user_id):
            return

        presence = await db_call(
            set_online,
            user_id,
            False
        )

        if manager.is_online(user_id):
            presence = await db_call(
                set_online,
                user_id,
                True
            )
            if presence["is_online"]:
                return

        await broadcast_presence(
            user_id,
            "offline",
            presence["last_seen"],
            presence["activity_status_enabled"],
        )

    except Exception:
        logger.exception(
            "go_offline failed for user %s",
            user_id
        )


# ============================================================
# PROCESS MESSAGE
# ============================================================

async def process_message(
    sender_id,
    sender_name,
    chat_id,
    content,
    client_id=None,
    origin=None,
    reply_to_id=None
):
    try:
        message = await db_call(
            save_message,
            sender_id,
            chat_id,
            content,
            reply_to_id
        )
    except Exception:
        logger.exception("Message persistence failed for chat_id=%s", chat_id)
        if origin is not None:
            await safe_send(origin, {
                "type": "message_failed",
                "chat_id": chat_id,
                "client_id": client_id,
                "detail": "Message could not be saved. Please try again.",
            })
        return {"failed": True}

    if message is None:
        return None

    # Tell sender actual message ID
    if origin is not None:
        await safe_send(
            origin,
            {
                "type": "message_sent",
                "chat_id": chat_id,
                "message_id": message["id"],
                "client_id": client_id,
                "created_at": message["created_at"],
                "reply_to_id": message["reply_to_id"],
            }
        )

    # Message event
    payload = {
        "type": "message",
        "chat_id": chat_id,
        "message_id": message["id"],
        "sender_id": sender_id,
        "sender_name": sender_name,
        "content": message["content"],
        "created_at": message["created_at"],
        "is_delivered": False,
        "is_read": False,
        "read_at": None,
        "reply_to_id": message["reply_to_id"],
    }

    delivered = await manager.send_to_user(
        message["receiver_id"],
        payload,
        chat_id
    )

    if delivered:
        await db_call(
            mark_delivered,
            [message["id"]]
        )

        message["is_delivered"] = True

        delivered_event = {
            "type": "message_delivered",
            "chat_id": chat_id,
            "message_id": message["id"],
        }

        if origin is not None:
            await safe_send(
                origin,
                delivered_event
            )
        else:
            await manager.send_to_user(
                sender_id,
                delivered_event,
                chat_id
            )

    # Detection and suggestion preparation run after persistence/delivery so
    # the normal send acknowledgement is never held up by the AI provider.
    spawn(evaluate_ai_response(chat_id, sender_id, message["id"]))
    spawn(prepare_death_zone_notification(chat_id, message["id"]))

    return message


def _chat_ai_context(db: Session, chat_id: int):
    rows = (
        db.query(models.Message)
        .filter(
            models.Message.chat_id == chat_id,
            models.Message.is_deleted.is_(False),
            models.Message.message_type == "text",
        )
        .order_by(models.Message.id.desc())
        .limit(60)
        .all()
    )
    rows.reverse()
    sender_ids = {row.sender_id for row in rows}
    users = db.query(models.User).filter(models.User.id.in_(sender_ids)).all() if sender_ids else []
    usernames = {user.id: user.username for user in users}
    messages = [
        {
            "sender_name": usernames.get(row.sender_id, "Unknown"),
            "sender_id": row.sender_id,
            "message_id": row.id,
            "content": row.content or "",
            "created_at": row.created_at,
        }
        for row in rows if row.content and row.content.strip()
    ]
    return rows, messages, {user.id: user for user in users}


def _notification_payload(notification: models.DeathZoneNotification) -> dict:
    return {
        "id": notification.id,
        "chat_id": notification.chat_id,
        "user_id": notification.user_id,
        "event_key": notification.event_key,
        "status": notification.status,
        "suggestions": json.loads(notification.suggestions_json or "[]"),
        "death_zone": json.loads(notification.death_zone_json or "{}"),
        "created_at": iso(notification.created_at),
        "viewed_at": iso(notification.viewed_at),
        "expires_at": iso(notification.expires_at),
        "active": notification.status == "ready" and (
            notification.viewed_at is None or
            (notification.expires_at is not None and notification.expires_at > utcnow())
        ),
    }


def _persist_ai_suggestions(db: Session, chat_id: int, user_id: int,
                            trigger_message_id: int | None, suggestions: list,
                            recovery: dict | None = None) -> list:
    """Best-effort lifecycle metadata; never persist suggestion text here."""
    from app.ai.extraction import MODEL_NAME
    recovery = recovery or {"strategy": "natural_continuation", "reason": "conversation_context"}
    try:
        intervention = db.query(models.AIRecoveryIntervention).filter_by(
            chat_id=chat_id, user_id=user_id, trigger_message_id=trigger_message_id,
        ).first()
        if intervention is None:
            intervention = models.AIRecoveryIntervention(
                chat_id=chat_id, user_id=user_id, trigger_message_id=trigger_message_id,
                recovery_reason=str(recovery.get("reason", "conversation_context"))[:80],
                strategy=str(recovery.get("strategy", "natural_continuation"))[:60],
                prompt_version=PROMPT_VERSION,
            )
            db.add(intervention)
            db.flush()
        result = []
        for item in suggestions:
            text = str(item.get("message", ""))
            strategy = str(item.get("strategy") or (recovery.get("strategy") if item.get("style") == "natural" else item.get("style")))[:60]
            record = models.AISuggestionRecord(
                intervention_id=intervention.id, chat_id=chat_id, user_id=user_id,
                suggestion_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                strategy=strategy, prompt_version=PROMPT_VERSION,
                model_id=MODEL_NAME, validation_passed=True,
            )
            db.add(record)
            db.flush()
            db.add(models.AISuggestionEvent(
                suggestion_id=record.id, chat_id=chat_id, user_id=user_id,
                event_key=f"generated-{record.id}", event_type="generated",
            ))
            result.append({**item, "suggestion_id": record.id, "strategy": strategy,
                           "prompt_version": PROMPT_VERSION})
        db.commit()
        return result
    except Exception:
        db.rollback()
        logger.exception("Could not persist AI suggestion lifecycle metadata for chat_id=%s", chat_id)
        return suggestions


def _record_suggestion_event(db: Session, suggestion_id: int, user_id: int,
                             event_type: str, event_key: str, details: dict | None = None):
    record = db.query(models.AISuggestionRecord).filter_by(
        id=suggestion_id, user_id=user_id
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="AI suggestion not found")
    if event_type not in VALID_EVENTS:
        raise HTTPException(status_code=422, detail="Unsupported suggestion event")
    # Unique event key makes retries idempotent while permitting repeated
    # views/selections when the caller supplies a fresh event key.
    event = models.AISuggestionEvent(
        suggestion_id=record.id, chat_id=record.chat_id, user_id=user_id,
        event_key=event_key[:100], event_type=event_type,
        details_json=json.dumps(details or {}, ensure_ascii=False),
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    if event_type == "user_feedback":
        intervention = db.get(models.AIRecoveryIntervention, record.intervention_id) if record.intervention_id else None
        if intervention:
            rating = (details or {}).get("rating")
            intervention.status = "unsuccessful" if rating == "not_helpful" else "user_endorsed" if rating == "helpful" else intervention.status
            intervention.evaluated_at = utcnow()
            intervention.outcome_json = json.dumps({"user_feedback": rating})
            db.commit()
            if rating == "not_helpful":
                state = db.get(models.DeathZoneConversationState, record.chat_id)
                if state:
                    state.active = False
                    state.target_user_id = None
                    db.commit()
    return {"ok": True}


def _evaluate_ai_response(db: Session, chat_id: int, sender_id: int, message_id: int):
    """Record observable outcomes only after the non-target participant replies."""
    from app.ai.ai_evaluation import meaningful_response
    intervention = db.query(models.AIRecoveryIntervention).filter(
        models.AIRecoveryIntervention.chat_id == chat_id,
        models.AIRecoveryIntervention.user_id != sender_id,
        models.AIRecoveryIntervention.status == "generated",
    ).order_by(models.AIRecoveryIntervention.created_at.desc()).first()
    if intervention is None:
        return
    suggestion_rows = db.query(models.AISuggestionRecord).filter_by(
        intervention_id=intervention.id,
    ).all()
    sent_ids = {
        event.suggestion_id for event in db.query(models.AISuggestionEvent).filter(
            models.AISuggestionEvent.event_type == "sent",
            models.AISuggestionEvent.suggestion_id.in_([row.id for row in suggestion_rows] or [-1]),
        ).all()
    }
    if not sent_ids:
        return
    message = db.get(models.Message, message_id)
    if message is None or message.sender_id == intervention.user_id:
        return
    key = f"reply-{message_id}"
    response_ok = meaningful_response(message.content)
    rows = db.query(models.Message).filter(
        models.Message.chat_id == chat_id,
        models.Message.is_deleted.is_(False),
        models.Message.message_type == "text",
        models.Message.id <= message_id,
    ).order_by(models.Message.id.desc()).limit(24).all()
    rows.reverse()
    baseline_rows = [row for row in rows if row.id <= (intervention.trigger_message_id or 0)][-24:]
    from app.ai.user_engagement import analyze_engagement
    before_score = analyze_engagement(baseline_rows)["scores"].get(str(intervention.user_id))
    after_score = analyze_engagement(rows)["scores"].get(str(intervention.user_id))
    improved = before_score is not None and after_score is not None and after_score >= before_score + 5
    for row in suggestion_rows:
        if row.id not in sent_ids:
            continue
        event_types = ["continued"]
        if response_ok:
            event_types.append("meaningful_response")
        if improved:
            event_types.append("engagement_improved")
        for event_type in event_types:
            event_key = f"{event_type}-{key}"
            already_recorded = db.query(models.AISuggestionEvent).filter_by(
                suggestion_id=row.id, event_key=event_key,
            ).first()
            if already_recorded:
                continue
            db.add(models.AISuggestionEvent(
                suggestion_id=row.id, chat_id=chat_id, user_id=intervention.user_id,
                event_key=event_key, event_type=event_type,
                details_json=json.dumps({"reply_message_id": message_id,
                                         "meaningful": response_ok,
                                         "engagement_delta": round(after_score - before_score, 1) if improved else None}),
            ))
    intervention.status = "observed_improvement" if improved else "responded" if response_ok else "awaiting_more_context"
    intervention.outcome_json = json.dumps({"reply_message_id": message_id, "meaningful_response": response_ok,
                                             "engagement_before": before_score, "engagement_after": after_score,
                                             "engagement_improved": improved})
    intervention.evaluated_at = utcnow()
    db.commit()


async def evaluate_ai_response(chat_id: int, sender_id: int, message_id: int):
    try:
        await db_call(_evaluate_ai_response, chat_id, sender_id, message_id)
    except Exception:
        logger.exception("AI suggestion outcome evaluation failed for chat_id=%s", chat_id)


def _prepare_death_zone_notification(db: Session, chat_id: int, trigger_message_id: int):
    chat = db.get(models.Chat, chat_id)
    if chat is None:
        return None
    state = db.get(models.DeathZoneConversationState, chat_id)
    if state is None:
        state = models.DeathZoneConversationState(chat_id=chat_id)
        db.add(state)
        db.flush()
    rows, messages, users = _chat_ai_context(db, chat_id)
    if not messages or not rows or rows[-1].id != trigger_message_id:
        return None

    analysis = analyze_death_zone(messages)
    effort = analyze_participant_effort(messages)
    target_id = effort.get("target_user_id")
    qualifies = (
        is_death_zone(analysis)
        and effort.get("eligible") is True
        and target_id in (chat.user1_id, chat.user2_id)
    )
    if not qualifies:
        state.active = False
        state.target_user_id = None
        state.last_message_id = trigger_message_id
        db.commit()
        return None

    if state.active and state.target_user_id == target_id:
        state.last_message_id = trigger_message_id
        db.commit()
        return None

    event_key = f"message-{trigger_message_id}"
    existing = db.query(models.DeathZoneNotification).filter_by(
        chat_id=chat_id, user_id=target_id, event_key=event_key
    ).first()
    if existing:
        return None

    # Claim this unique event before calling the model. A concurrent task will
    # see the claim and skip, preventing duplicate suggestion generation.
    notification = models.DeathZoneNotification(
        chat_id=chat_id,
        user_id=target_id,
        event_key=event_key,
        trigger_message_id=trigger_message_id,
        status="generating",
        death_zone_json=json.dumps({**analysis, "participant_effort": effort}, ensure_ascii=False),
    )
    db.add(notification)
    state.active = True
    state.target_user_id = target_id
    state.last_message_id = trigger_message_id
    try:
        db.commit()
        db.refresh(notification)
    except IntegrityError:
        db.rollback()
        return None

    target = users.get(target_id)
    if target is None:
        notification.status = "failed"
        db.commit()
        return None

    try:
        if target.ai_memory_enabled:
            try:
                from app.ai.memory import extract_and_save_opt_in_memories
                extract_and_save_opt_in_memories(db, target, messages)
            except Exception:
                db.rollback()
                logger.exception("Opt-in AI memory extraction failed for user_id=%s", target_id)
        result = run_conversation_workflow(
            db=db,
            requesting_user_id=target_id,
            requesting_user=target.username,
            messages=messages,
            chat_id=chat_id,
        )
        suggestions = (result.get("suggestion_result") or {}).get("suggestions", [])
        if result.get("should_generate") is not True or len(suggestions) != 3:
            notification.status = "failed"
            state.active = False
            state.target_user_id = None
            db.commit()
            return None
        suggestions = _persist_ai_suggestions(
            db, chat_id, target_id, trigger_message_id, suggestions,
            result.get("recovery"),
        )
        notification.suggestions_json = json.dumps(suggestions, ensure_ascii=False)
        notification.status = "ready"
        db.commit()
        db.refresh(notification)
        return _notification_payload(notification)
    except Exception:
        db.rollback()
        logger.exception("Automatic AI notification failed for chat_id=%s", chat_id)
        failed = db.get(models.DeathZoneNotification, notification.id)
        if failed:
            failed.status = "failed"
            failed_state = db.get(models.DeathZoneConversationState, chat_id)
            if failed_state:
                failed_state.active = False
                failed_state.target_user_id = None
            db.commit()
        return None


async def prepare_death_zone_notification(chat_id: int, trigger_message_id: int):
    try:
        payload = await db_call(_prepare_death_zone_notification, chat_id, trigger_message_id)
        if payload and payload.get("active"):
            await manager.send_to_user(
                payload["user_id"],
                {"type": "death_zone_notification", "notification": payload},
                chat_id,
            )
    except Exception:
        logger.exception("Death-zone notification preparation failed for chat_id=%s", chat_id)


# ============================================================
# BASIC ROUTES
# ============================================================

@app.get("/")
def home():
    return {
        "message": "Bugzyme Backend is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }




# ============================================================
# REGISTER
# ============================================================

@app.post(
    "/register",
    response_model=schemas.UserResponse,
    status_code=201
)
def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    email = user.email.strip().lower()
    username = user.username.strip()

    if db.query(models.User).filter(
        func.lower(models.User.email) == email
    ).first():
        raise HTTPException(
            409,
            "Email already registered"
        )

    if db.query(models.User).filter(
        func.lower(models.User.username)
        == username.lower()
    ).first():
        raise HTTPException(
            409,
            "Username already taken"
        )

    new_user = models.User(
        username=username,
        email=email,
        hashed_password=password_hash.hash(
            user.password
        ),
        is_online=False,
    )

    db.add(new_user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Email or username already registered"
        )

    db.refresh(new_user)

    return new_user
@app.post("/upload-voice")
async def upload_voice(
    file: UploadFile = File(...),
    chat_id: int = Query(...),
    duration: int | None = Query(default=None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # -----------------------------------------
    # 1. Check chat membership
    # -----------------------------------------

    chat = member_chat(
        db,
        chat_id,
        current_user.id
    )

    if not chat:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this chat"
        )

    # -----------------------------------------
    # 2. Save audio file
    # -----------------------------------------

    upload_dir = "uploads/voice"

    os.makedirs(
        upload_dir,
        exist_ok=True
    )

    extension = os.path.splitext(
        file.filename or ""
    )[1]

    if not extension:
        extension = ".webm"

    filename = f"{uuid.uuid4()}{extension}"

    file_path = os.path.join(
        upload_dir,
        filename
    )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Empty audio file"
        )

    with open(file_path, "wb") as f:
        f.write(content)

    audio_url = f"/uploads/voice/{filename}"

    # -----------------------------------------
    # 3. Create voice message in DB
    # -----------------------------------------

    message = await db_call(
        save_voice_message,
        current_user.id,
        chat_id,
        audio_url,
        duration,
        file.content_type
    )

    if message is None:
        # Remove uploaded file if DB message failed
        try:
            os.remove(file_path)
        except OSError:
            pass

        raise HTTPException(
            status_code=400,
            detail="Could not create voice message"
        )

    # -----------------------------------------
    # 4. Send voice message to receiver
    # -----------------------------------------

    payload = {
        "type": "voice_message",
        "chat_id": chat_id,
        "message_id": message["id"],
        "sender_id": current_user.id,
        "sender_name": current_user.username,
        "content": None,
        "created_at": message["created_at"],
        "is_delivered": False,
        "is_read": False,
        "read_at": None,
        "reply_to_id": None,
        "message_type": "voice",
        "audio_url": message["audio_url"],
        "audio_duration": message["audio_duration"],
        "audio_mime_type": message["audio_mime_type"],
    }

    delivered = await manager.send_to_user(
        message["receiver_id"],
        payload,
        chat_id
    )

    # -----------------------------------------
    # 5. Mark delivered if receiver is online
    # -----------------------------------------

    if delivered:
        await db_call(
            mark_delivered,
            [message["id"]]
        )

        message["is_delivered"] = True

    # -----------------------------------------
    # 6. Return message to sender
    # -----------------------------------------

    return {
        "success": True,
        "message": message,
        "delivered": delivered,
    }


@app.post(
    "/chats/{chat_id}/attachments",
    response_model=schemas.MessageResponse,
    status_code=201,
)
async def upload_chat_attachment(
    chat_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    reply_to_id: int | None = Form(default=None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not member_chat(db, chat_id, current_user.id):
        raise HTTPException(403, "You are not a member of this chat")

    if caption is not None and len(caption) > schemas.MAX_MESSAGE_LEN:
        raise HTTPException(400, "Caption exceeds the 2000 character limit")

    try:
        storage_key, filename, mime_type, size_bytes, message_type = (
            await attachment_storage.save_upload(file)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()

    try:
        message = await db_call(
            save_attachment_message,
            current_user.id,
            chat_id,
            caption,
            reply_to_id,
            storage_key,
            filename,
            mime_type,
            size_bytes,
            message_type,
        )
    except Exception:
        await run_in_threadpool(attachment_storage.remove_attachment, storage_key)
        raise

    if message is None:
        await run_in_threadpool(attachment_storage.remove_attachment, storage_key)
        raise HTTPException(400, "Could not create attachment message or invalid reply")

    payload = {
        "type": "message",
        "chat_id": chat_id,
        "message_id": message["id"],
        "sender_id": current_user.id,
        "sender_name": current_user.username,
        "content": message["content"],
        "created_at": message["created_at"],
        "is_delivered": False,
        "is_read": False,
        "read_at": None,
        "reply_to_id": message["reply_to_id"],
        "message_type": message_type,
        "attachment_name": filename,
        "attachment_mime_type": mime_type,
        "attachment_size_bytes": size_bytes,
    }
    delivered = await manager.send_to_user(
        message["receiver_id"], payload, chat_id
    )

    if delivered:
        await db_call(mark_delivered, [message["id"]])
        message["is_delivered"] = True
        await manager.send_to_user(
            current_user.id,
            {
                "type": "message_delivered",
                "chat_id": chat_id,
                "message_id": message["id"],
            },
            chat_id,
        )

    return message


@app.get("/attachments/{message_id}/content")
def get_attachment_content(
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = db.get(models.Message, message_id)
    if (
        not message
        or message.is_deleted
        or not message.attachment_storage_key
        or message.message_type not in {"image", "file"}
    ):
        raise HTTPException(404, "Attachment not found")

    chat = member_chat(db, message.chat_id, current_user.id)
    if not chat:
        raise HTTPException(404, "Attachment not found")

    try:
        path = attachment_storage.attachment_path(message.attachment_storage_key)
    except ValueError as exc:
        logger.error("Invalid attachment key on message %s", message_id)
        raise HTTPException(404, "Attachment not found") from exc
    if not path.is_file():
        raise HTTPException(404, "Attachment content not found")

    mime_type = message.attachment_mime_type
    if mime_type not in {value[0] for value in attachment_storage.ALLOWED_TYPES.values()}:
        mime_type = "application/octet-stream"

    filename = Path(message.attachment_name or "attachment").name.replace("\r", "").replace("\n", "")
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "'")
    disposition = "inline" if message.message_type == "image" else "attachment"

    def stream_file():
        with path.open("rb") as source:
            while chunk := source.read(64 * 1024):
                yield chunk

    headers = {
        "Content-Disposition": (
            f'{disposition}; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(filename, safe='')}"
        ),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    return StreamingResponse(stream_file(), media_type=mime_type, headers=headers)
# ============================================================
# LOGIN
# ============================================================

@app.post(
    "/login",
    response_model=schemas.Token
)
def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    email = form_data.username.strip().lower()

    user = db.query(models.User).filter(
        func.lower(models.User.email) == email
    ).first()

    if (
        not user
        or not password_hash.verify(
            form_data.password,
            user.hashed_password
        )
    ):
        raise HTTPException(
            401,
            "Invalid email or password"
        )

    return {
        "access_token": create_token(user.id),
        "token_type": "bearer"
    }


# ============================================================
# CURRENT USER
# ============================================================

@app.get(
    "/me",
    response_model=schemas.UserResponse
)
def me(
    current_user: models.User = Depends(
        get_current_user
    )
):
    return current_user


@app.patch("/me", response_model=schemas.UserResponse)
def update_me_profile(
    changes: schemas.UserProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    values = changes.model_dump(exclude_unset=True)
    for field in ("full_name", "bio", "ai_memory_enabled"):
        if field not in values:
            continue
        value = values[field]
        if field == "ai_memory_enabled":
            setattr(current_user, field, bool(value))
        else:
            value = value.strip() if isinstance(value, str) else None
            setattr(current_user, field, value or None)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@app.patch("/me/presence", response_model=schemas.PresencePreferenceResponse)
async def update_presence_preference(
    changes: schemas.PresencePreferenceUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enabled = bool(changes.activity_status_enabled)
    changed = current_user.activity_status_enabled != enabled
    was_online = bool(current_user.is_online)
    visible_online = enabled and manager.is_online(current_user.id)
    current_user.activity_status_enabled = enabled
    current_user.is_online = visible_online
    if was_online and not visible_online:
        current_user.last_seen = utcnow()
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    last_seen = iso(current_user.last_seen)
    if changed or was_online != visible_online:
        await broadcast_presence(
            current_user.id,
            "online" if visible_online else "offline",
            last_seen,
            enabled,
        )
    return {
        "activity_status_enabled": enabled,
        "is_online": visible_online,
        "last_seen": current_user.last_seen,
    }


@app.get("/me/ai-memories", response_model=list[schemas.UserMemoryResponse])
def list_my_ai_memories(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.UserMemory)
        .filter(models.UserMemory.user_id == current_user.id)
        .order_by(models.UserMemory.created_at.desc(), models.UserMemory.id.desc())
        .limit(100)
        .all()
    )


@app.patch("/me/ai-memories/{memory_id}", response_model=schemas.UserMemoryResponse)
def update_my_ai_memory(
    memory_id: int,
    changes: schemas.UserMemoryUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = db.query(models.UserMemory).filter(
        models.UserMemory.id == memory_id,
        models.UserMemory.user_id == current_user.id,
    ).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    value = changes.memory_text.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Memory cannot be blank")
    from app.ai.memory import generate_embedding
    memory.memory_text = value
    memory.embedding = generate_embedding(value)
    db.commit()
    db.refresh(memory)
    return memory


@app.delete("/me/ai-memories/{memory_id}")
def delete_my_ai_memory(
    memory_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = db.query(models.UserMemory).filter(
        models.UserMemory.id == memory_id,
        models.UserMemory.user_id == current_user.id,
    ).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(memory)
    db.commit()
    return {"deleted": True}


@app.delete("/me/ai-memories")
def clear_my_ai_memories(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(models.UserMemory).filter(
        models.UserMemory.user_id == current_user.id
    ).delete(synchronize_session=False)
    # Do not immediately recreate cleared memories from old history.
    current_user.ai_memory_processed_through_message_id = (
        db.query(func.max(models.Message.id))
        .filter(models.Message.sender_id == current_user.id)
        .scalar()
    )
    db.commit()
    return {"deleted": True}


# ============================================================
# USERS
# ============================================================

@app.get(
    "/users",
    response_model=list[schemas.UserPublic]
)
def get_users(
    current_user: models.User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db)
):
    users = db.query(
        models.User
    ).order_by(
        models.User.username
    ).all()

    return [
        schemas.UserPublic(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            bio=user.bio,
            is_online=manager.is_online(user.id) and user.activity_status_enabled,
            last_seen=user.last_seen,
        )
        for user in users
    ]


# ============================================================
# CREATE CHAT
# ============================================================

@app.post(
    "/chats",
    response_model=schemas.ChatResponse
)
def create_chat(
    chat: schemas.ChatCreate,
    current_user: models.User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db)
):
    if current_user.id == chat.user2_id:
        raise HTTPException(
            400,
            "You cannot chat with yourself"
        )

    if not db.get(
        models.User,
        chat.user2_id
    ):
        raise HTTPException(
            404,
            "User not found"
        )

    existing = find_chat(
        db,
        current_user.id,
        chat.user2_id
    )

    if existing:
        return existing

    new_chat = models.Chat(
        user1_id=current_user.id,
        user2_id=chat.user2_id
    )

    db.add(new_chat)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        existing = find_chat(
            db,
            current_user.id,
            chat.user2_id
        )

        if existing:
            return existing

        raise

    db.refresh(new_chat)

    return new_chat


# ============================================================
# DELETE CHAT
# ============================================================

@app.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: int,
    current_user: models.User = Depends(
        get_current_user
    )
):
    result = await db_call(
        delete_chat_from_database,
        chat_id,
        current_user.id
    )

    if result is None:
        raise HTTPException(
            404,
            "Chat not found or you are not a member"
        )

    event = {
        "type": "chat_deleted",
        "chat_id": result["chat_id"]
    }

    # Tell current user
    await manager.send_to_user(
        current_user.id,
        event,
        chat_id
    )

    # Tell other user
    await manager.send_to_user(
        result["other_user_id"],
        event,
        chat_id
    )

    return {
        "ok": True,
        "message": "Chat deleted successfully"
    }


# ============================================================
# GET CHATS
# ============================================================

@app.get("/chats", response_model=list[schemas.ChatSummary])
def list_chats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    my_id = current_user.id

    chats = db.query(models.Chat).filter(
        or_(
            models.Chat.user1_id == my_id,
            models.Chat.user2_id == my_id
        )
    ).all()

    if not chats:
        return []

    chat_ids = [chat.id for chat in chats]

    latest_ids = dict(
        db.query(
            models.Message.chat_id,
            func.max(models.Message.id)
        )
        .filter(
            models.Message.chat_id.in_(chat_ids),
            models.Message.is_deleted.is_not(True)
        )
        .group_by(models.Message.chat_id)
        .all()
    )

    latest_messages = {}

    if latest_ids:
        latest_messages = {
            message.chat_id: message
            for message in db.query(models.Message)
            .filter(
                models.Message.id.in_(list(latest_ids.values()))
            )
            .all()
        }

    unread = dict(
        db.query(
            models.Message.chat_id,
            func.count(models.Message.id)
        )
        .filter(
            models.Message.chat_id.in_(chat_ids),
            models.Message.sender_id != my_id,
            models.Message.is_read.is_not(True),
            models.Message.is_deleted.is_not(True)
        )
        .group_by(models.Message.chat_id)
        .all()
    )

    partner_ids = {
        other_user(chat, my_id)
        for chat in chats
    }

    users = {
        user.id: user
        for user in db.query(models.User)
        .filter(models.User.id.in_(partner_ids))
        .all()
    }

    result = []

    for chat in chats:
        partner = users.get(
            other_user(chat, my_id)
        )

        if not partner:
            continue

        last_message = latest_messages.get(chat.id)

        result.append(
            schemas.ChatSummary(
                chat_id=chat.id,
                user=schemas.UserPublic(
                    id=partner.id,
                    username=partner.username,
                    full_name=partner.full_name,
                    bio=partner.bio,
                    is_online=manager.is_online(partner.id) and partner.activity_status_enabled,
                    last_seen=partner.last_seen
                ),
                last_message=(
                    schemas.MessageResponse.model_validate(last_message)
                    if last_message
                    else None
                ),
                unread_count=unread.get(chat.id, 0)
            )
        )

    result.sort(
        key=lambda chat: chat.last_message.id if chat.last_message else 0,
        reverse=True
    )

    return result

# ============================================================
# SEND MESSAGE
# ============================================================

@app.post(
    "/messages",
    response_model=schemas.MessageResponse,
    status_code=201
)
async def send_message(
    message: schemas.MessageCreate,
    current_user: models.User = Depends(
        get_current_user
    )
):
    result = await process_message(
        current_user.id,
        current_user.username,
        message.chat_id,
        message.content,
        reply_to_id=message.reply_to_id
    )

    if result is None:
        raise HTTPException(
            403,
            "You are not a member of this chat or invalid reply"
        )

    return result


# ============================================================
# DELETE MESSAGE
# ============================================================

@app.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    for_everyone: bool = True,
    current_user: models.User = Depends(
        get_current_user
    )
):
    result = await db_call(
        soft_delete_message,
        current_user.id,
        message_id,
        for_everyone
    )

    if result is None:
        raise HTTPException(
            403,
            "Cannot delete this message"
        )

    event = {
        "type": "message_deleted",
        "chat_id": result["chat_id"],
        "message_id": result["message_id"],
        "for_everyone": result["for_everyone"],
    }

    # Sender
    await manager.send_to_user(
        current_user.id,
        event,
        result["chat_id"]
    )

    # Receiver
    await manager.send_to_user(
        result["receiver_id"],
        event,
        result["chat_id"]
    )

    await run_in_threadpool(
        attachment_storage.remove_attachment,
        result.get("attachment_storage_key"),
    )

    return {
        "ok": True,
        "message_id": message_id
    }


# ============================================================
# GET MESSAGES
# ============================================================

@app.get(
    "/messages/{chat_id}",
    response_model=list[schemas.MessageResponse]
)
def get_messages(
    chat_id: int,
    limit: int = Query(
        200,
        ge=1,
        le=500
    ),
    before_id: int | None = None,
    current_user: models.User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db)
):
    chat = db.get(
        models.Chat,
        chat_id
    )

    if not chat:
        raise HTTPException(
            404,
            "Chat not found"
        )

    if current_user.id not in (
        chat.user1_id,
        chat.user2_id
    ):
        raise HTTPException(
            403,
            "You are not a member of this chat"
        )

    query = db.query(
        models.Message
    ).options(
        selectinload(models.Message.reactions)
    ).filter(
        models.Message.chat_id == chat_id
    )

    if before_id is not None:
        query = query.filter(
            models.Message.id < before_id
        )

    messages = query.order_by(
        models.Message.id.desc()
    ).limit(
        limit
    ).all()

    messages.reverse()

    return messages


# ============================================================
# AI CONVERSATION SUGGESTIONS
# ============================================================

@app.get("/ai-notifications")
def list_ai_notifications(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(models.DeathZoneNotification).filter(
        models.DeathZoneNotification.user_id == current_user.id,
        models.DeathZoneNotification.status == "ready",
        or_(
            models.DeathZoneNotification.viewed_at.is_(None),
            models.DeathZoneNotification.expires_at > utcnow(),
        ),
    ).order_by(models.DeathZoneNotification.created_at.desc()).limit(100).all()
    return {"notifications": [_notification_payload(row) for row in rows]}


@app.post("/ai-notifications/{notification_id}/view")
def view_ai_notification(
    notification_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(models.DeathZoneNotification).filter(
        models.DeathZoneNotification.id == notification_id,
        models.DeathZoneNotification.user_id == current_user.id,
        models.DeathZoneNotification.status == "ready",
    ).first()
    if notification is None:
        raise HTTPException(status_code=404, detail="AI notification not found")
    now = utcnow()
    if notification.viewed_at is None:
        notification.viewed_at = now
        notification.expires_at = now + timedelta(seconds=30)
        db.commit()
        db.refresh(notification)
        for suggestion in json.loads(notification.suggestions_json or "[]"):
            suggestion_id = suggestion.get("suggestion_id") if isinstance(suggestion, dict) else None
            if suggestion_id:
                try:
                    _record_suggestion_event(
                        db, suggestion_id, current_user.id, "viewed",
                        f"notification-{notification.id}-view",
                    )
                except HTTPException:
                    logger.info("Suggestion lifecycle row missing for notification=%s", notification.id)
    payload = _notification_payload(notification)
    return payload


@app.post("/ai-suggestions/{suggestion_id}/events")
def track_ai_suggestion_event(
    suggestion_id: int,
    payload: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event_type = payload.get("event_type")
    event_key = payload.get("event_key")
    if not isinstance(event_key, str) or not event_key.strip():
        raise HTTPException(status_code=422, detail="event_key is required")
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    if event_type not in CLIENT_EVENTS:
        raise HTTPException(status_code=422, detail="Unsupported suggestion event")
    if event_type == "user_feedback" and details.get("rating") not in {"helpful", "not_helpful"}:
        raise HTTPException(status_code=422, detail="Feedback rating is invalid")
    if event_type == "sent":
        message_id = details.get("message_id")
        record = db.query(models.AISuggestionRecord).filter_by(id=suggestion_id, user_id=current_user.id).first()
        message = db.get(models.Message, message_id) if isinstance(message_id, int) else None
        if record is None or message is None or message.chat_id != record.chat_id or message.sender_id != current_user.id:
            raise HTTPException(status_code=422, detail="Sent event must reference your persisted chat message")
        selected = db.query(models.AISuggestionEvent).filter_by(suggestion_id=suggestion_id, user_id=current_user.id, event_type="selected").first()
        edited = db.query(models.AISuggestionEvent).filter_by(suggestion_id=suggestion_id, user_id=current_user.id, event_type="edited").first()
        digest = hashlib.sha256((message.content or "").encode("utf-8")).hexdigest()
        if selected is None or (digest != record.suggestion_hash and edited is None):
            raise HTTPException(status_code=422, detail="Suggestion must be selected before it can be recorded as sent")
    if event_type == "user_feedback":
        details = {"rating": details["rating"]}
    elif event_type == "viewed":
        details = {}
    elif event_type == "edited":
        details = {"changed": bool(details.get("changed", True))}
    elif event_type == "sent":
        details = {"message_id": int(details["message_id"]), "edited": bool(details.get("edited", False))}
    else:
        details = {}
    response = _record_suggestion_event(db, suggestion_id, current_user.id, event_type, event_key, details)
    if event_type == "sent":
        next_reply = db.query(models.Message).filter(
            models.Message.chat_id == record.chat_id,
            models.Message.id > message_id,
            models.Message.sender_id != current_user.id,
            models.Message.is_deleted.is_(False),
        ).order_by(models.Message.id.asc()).first()
        if next_reply:
            _evaluate_ai_response(db, record.chat_id, next_reply.sender_id, next_reply.id)
    return response


@app.get("/chats/{chat_id}/coach")
def get_private_conversation_coach(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = db.get(models.Chat, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if current_user.id not in (chat.user1_id, chat.user2_id):
        raise HTTPException(status_code=403, detail="You are not a member of this chat")
    _, messages, _ = _chat_ai_context(db, chat_id)
    from app.ai.conversation_intelligence import build_conversation_intelligence
    from app.ai.conversation_coach import CoachServiceError, generate_private_coaching
    from app.ai.conversation_insights import build_conversation_insights
    if not messages:
        return {"chat_id": chat_id, "user_id": current_user.id,
                "available": False, "reason": "no_context", "insights": []}
    intelligence = build_conversation_intelligence(messages)
    own = intelligence.get("participant_views", {}).get(str(current_user.id), {})
    if not own:
        return {"chat_id": chat_id, "user_id": current_user.id,
                "available": False, "reason": "missing_profile", "insights": []}
    shared = build_conversation_insights(messages)
    try:
        coaching = generate_private_coaching(messages, current_user.id, own, {
            "mood": (shared.get("mood") or {}).get("state", "uncertain"),
            "shared_topics": shared.get("shared_topics", []),
            "engagement_trend": (shared.get("engagement_trend") or {}).get("state", "unknown"),
        })
    except CoachServiceError as exc:
        logger.exception("Private coach generation failed for chat_id=%s user_id=%s code=%s",
                         chat_id, current_user.id, exc.code)
        if exc.code == "provider_not_configured":
            raise HTTPException(status_code=503, detail={"code": exc.code, "message": "The AI coach is not configured on the server."}) from exc
        if exc.code == "invalid_provider_response":
            raise HTTPException(status_code=502, detail={"code": exc.code, "message": "The AI coach returned an invalid response. Please retry."}) from exc
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": "The AI coach service is temporarily unavailable. Please retry."}) from exc
    except Exception as exc:
        logger.exception("Unexpected private coach error for chat_id=%s user_id=%s", chat_id, current_user.id)
        raise HTTPException(status_code=500, detail={"code": "coach_internal_error", "message": "Private coaching could not be prepared. Please retry."}) from exc
    return {"chat_id": chat_id, "user_id": current_user.id, **coaching}


@app.get("/chats/{chat_id}/insights")
def get_private_conversation_insights(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = db.get(models.Chat, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if current_user.id not in (chat.user1_id, chat.user2_id):
        raise HTTPException(status_code=403, detail="You are not a member of this chat")
    _, messages, _ = _chat_ai_context(db, chat_id)
    from app.ai.conversation_insights import build_conversation_insights
    try:
        report = build_conversation_insights(messages)
    except Exception as exc:
        logger.exception("Conversation insights failed for chat_id=%s user_id=%s", chat_id, current_user.id)
        raise HTTPException(status_code=500, detail={"code": "insights_internal_error", "message": "Conversation insights could not be prepared. Please retry."}) from exc
    return {"chat_id": chat_id, "user_id": current_user.id, **report}

@app.post("/chats/{chat_id}/suggestions")
def get_chat_suggestions(
    chat_id: int,
    payload: dict = Body(default={}),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Verify chat exists
    chat = db.get(models.Chat, chat_id)

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    # 2. Verify current user belongs to this chat
    if current_user.id not in (chat.user1_id, chat.user2_id):
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this chat",
        )

    # 3. Fetch recent, non-deleted text messages
    db_messages = (
        db.query(models.Message)
        .filter(
            models.Message.chat_id == chat_id,
            models.Message.is_deleted.is_(False),
            models.Message.message_type == "text",
        )
        .order_by(models.Message.id.desc())
        .limit(60)
        .all()
    )

    # AI needs chronological order
    db_messages.reverse()

    if not db_messages:
        raise HTTPException(
            status_code=400,
            detail="No text messages available for AI analysis",
        )

    # 4. Fetch sender usernames
    sender_ids = {message.sender_id for message in db_messages}

    users = (
        db.query(models.User)
        .filter(models.User.id.in_(sender_ids))
        .all()
    )
    usernames = {user.id: user.username for user in users}

    # 5. Prepare the message format expected by the AI
    messages = [
        {
            "sender_name": usernames.get(message.sender_id, "Unknown"),
            "sender_id": message.sender_id,
            "message_id": message.id,
            "content": message.content or "",
            "created_at": message.created_at,
        }
        for message in db_messages
        if message.content and message.content.strip()
    ]

    if not messages:
        raise HTTPException(
            status_code=400,
            detail="No usable text messages available for AI analysis",
        )

    avoid_suggestions = payload.get("avoid_suggestions", []) if isinstance(payload, dict) else []
    if not isinstance(avoid_suggestions, list):
        avoid_suggestions = []
    avoid_suggestions = [item[:300] for item in avoid_suggestions if isinstance(item, str) and item.strip()][:3]

    effort = analyze_participant_effort(messages)
    death_zone = analyze_death_zone(messages)
    # Manual suggestions are available to either chat participant.
    # Automatic death-zone targeting remains unchanged.

    if current_user.ai_memory_enabled:
        try:
            from app.ai.memory import extract_and_save_opt_in_memories
            extract_and_save_opt_in_memories(db, current_user, messages)
        except Exception:
            db.rollback()
            logger.exception("Opt-in AI memory extraction failed for user_id=%s", current_user.id)

    # 6. Run the LangGraph workflow
    try:
        result = run_conversation_workflow(
            db=db,
            requesting_user_id=current_user.id,
            requesting_user=current_user.username,
            messages=messages,
            chat_id=chat_id,
            avoid_suggestions=avoid_suggestions,
            manual_request=True,
        )
    except Exception:
        logger.exception(
            "AI suggestion workflow failed for chat_id=%s",
            chat_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not generate AI conversation suggestions",
        )

    # 7. Return death-zone analysis and suggestions
    death_zone = result.get("death_zone", {})
    suggestion_result = result.get("suggestion_result")
    suggestions = (suggestion_result or {}).get("suggestions", [])
    if suggestions:
        suggestions = _persist_ai_suggestions(
            db, chat_id, current_user.id, db_messages[-1].id,
            suggestions, result.get("recovery"),
        )

    return {
        "chat_id": chat_id,
        "death_zone": death_zone,
        "should_generate": result.get("should_generate", False),
        "target_user_id": current_user.id if result.get("should_generate") else result.get("participant_effort", {}).get("target_user_id"),
        "eligible": result.get("should_generate", False),
        "recovery": result.get("recovery", {}),
        "suggestions": suggestions,
        "analysis": (
            suggestion_result.get("analysis")
            if suggestion_result
            else None
        ),
        "memories_used": (
            suggestion_result.get("memories_used", [])
            if suggestion_result
            else []
        ),
    }





# ============================================================
# WEBSOCKET
# ============================================================

async def handle_socket(
    websocket: WebSocket,
    token: str,
    bound_chat_id: int | None
):
    await websocket.accept()

    user_id = decode_token(token)

    if user_id is None:
        await websocket.close(
            code=1008,
            reason="Invalid or expired token"
        )
        return

    context = await db_call(
        load_context,
        user_id,
        bound_chat_id
    )

    if context is None:
        await websocket.close(
            code=1008,
            reason="Not allowed"
        )
        return

    partners = context["partners"]
    username = context["username"]

    first = manager.connect(
        user_id,
        websocket,
        bound_chat_id
    )

    try:
        if first:
            presence = await db_call(set_online, user_id, True)
            await broadcast_presence(
                user_id,
                "online" if presence["is_online"] else "offline",
                presence["last_seen"],
                presence["activity_status_enabled"],
            )

        await safe_send(
            websocket,
            {
                "type": "ready",
                "user_id": user_id,
                "online_user_ids": [
                    online_id for online_id in await db_call(visible_online_ids)
                    if online_id != user_id
                ],
            }
        )

        for (
            sender_id,
            chat_id,
            message_id
        ) in context["delivered"]:

            await manager.send_to_user(
                sender_id,
                {
                    "type": "message_delivered",
                    "chat_id": chat_id,
                    "message_id": message_id
                },
                chat_id
            )

        timeout = (
            IDLE_TIMEOUT
            if bound_chat_id is None
            else None
        )

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout
                )

            except asyncio.TimeoutError:
                await websocket.close(
                    code=1001,
                    reason="Idle timeout"
                )
                break

            except ValueError:
                await safe_send(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Invalid JSON"
                    }
                )
                continue

            if not isinstance(data, dict):
                continue

            event_type = data.get("type")

            chat_id = (
                bound_chat_id
                if bound_chat_id is not None
                else data.get("chat_id")
            )

            if (
                isinstance(chat_id, bool)
                or (
                    chat_id is not None
                    and not isinstance(
                        chat_id,
                        int
                    )
                )
            ):
                chat_id = None

            # =================================================
            # PING
            # =================================================

            if event_type == "ping":

                await safe_send(
                    websocket,
                    {
                        "type": "pong"
                    }
                )

            # =================================================
            # MESSAGE
            # =================================================

            elif event_type == "message":

                content = data.get("content")
                reply_to_id = data.get(
                    "reply_to_id"
                )

                if (
                    not isinstance(
                        content,
                        str
                    )
                    or chat_id is None
                ):
                    continue

                content = content.strip()

                if not content:
                    continue

                if len(content) > schemas.MAX_MESSAGE_LEN:

                    await safe_send(
                        websocket,
                        {
                            "type": "message_failed",
                            "chat_id": chat_id,
                            "client_id": data.get("client_id"),
                            "detail": "Message too long"
                        }
                    )

                    continue

                result = await process_message(
                    user_id,
                    username,
                    chat_id,
                    content,
                    data.get("client_id"),
                    websocket,
                    reply_to_id
                )

                if result is None:

                    await safe_send(
                        websocket,
                        {
                            "type": "message_failed",
                            "chat_id": chat_id,
                            "client_id": data.get("client_id"),
                            "detail":
                            "Not a member of this chat or invalid reply"
                        }
                    )

            # =================================================
            # MESSAGE REACTION
            # =================================================

            elif event_type == "message_reaction":

                message_id = data.get("message_id")
                reaction = data.get("reaction")
                request_id = data.get("request_id")

                if (
                    chat_id is None
                    or isinstance(message_id, bool)
                    or not isinstance(message_id, int)
                    or not isinstance(reaction, str)
                    or reaction not in ALLOWED_MESSAGE_REACTIONS
                ):
                    await safe_send(
                        websocket,
                        {
                            "type": "message_reaction_error",
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "request_id": request_id,
                            "detail": "Invalid message reaction",
                        },
                    )
                    continue

                result = await db_call(
                    toggle_message_reaction,
                    user_id,
                    chat_id,
                    message_id,
                    reaction,
                )
                if result is None:
                    await safe_send(
                        websocket,
                        {
                            "type": "message_reaction_error",
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "request_id": request_id,
                            "detail": "Message not found or you are not a chat participant",
                        },
                    )
                    continue

                reaction_event = {
                    "type": "message_reaction",
                    "chat_id": result["chat_id"],
                    "message_id": result["message_id"],
                    "revision": result["revision"],
                    "request_id": request_id,
                    "reactions": result["reactions"],
                }
                await manager.send_to_user(
                    user_id,
                    reaction_event,
                    result["chat_id"],
                )
                await manager.send_to_user(
                    result["receiver_id"],
                    reaction_event,
                    result["chat_id"],
                )

            # =================================================
            # DELETE MESSAGE
            # =================================================

            elif event_type == "delete_message":

                message_id = data.get(
                    "message_id"
                )

                for_everyone = data.get(
                    "for_everyone",
                    True
                )

                if not isinstance(
                    message_id,
                    int
                ):
                    continue

                result = await db_call(
                    soft_delete_message,
                    user_id,
                    message_id,
                    for_everyone
                )

                if result:

                    delete_event = {
                        "type": "message_deleted",
                        "chat_id": result["chat_id"],
                        "message_id": result["message_id"],
                        "for_everyone":
                            result["for_everyone"]
                    }

                    # Send to sender
                    await manager.send_to_user(
                        user_id,
                        delete_event,
                        result["chat_id"]
                    )

                    # Send to receiver
                    await manager.send_to_user(
                        result["receiver_id"],
                        delete_event,
                        result["chat_id"]
                    )

                    await run_in_threadpool(
                        attachment_storage.remove_attachment,
                        result.get("attachment_storage_key"),
                    )

            # =================================================
            # DELETE CHAT
            # =================================================

            elif event_type == "delete_chat":

                if chat_id is None:
                    continue

                result = await db_call(
                    delete_chat_from_database,
                    chat_id,
                    user_id
                )

                if result is None:

                    await safe_send(
                        websocket,
                        {
                            "type": "error",
                            "detail":
                            "Chat not found or you are not a member"
                        }
                    )

                    continue

                delete_chat_event = {
                    "type": "chat_deleted",
                    "chat_id": result["chat_id"]
                }

                # Send to current user
                await manager.send_to_user(
                    user_id,
                    delete_chat_event,
                    chat_id
                )

                # Send to other user
                await manager.send_to_user(
                    result["other_user_id"],
                    delete_chat_event,
                    chat_id
                )

            # =================================================
            # TYPING
            # =================================================

            elif event_type == "typing":

                if chat_id is None:
                    continue

                if chat_id not in partners:

                    partners.clear()

                    partners.update(
                        await db_call(
                            get_partners,
                            user_id
                        )
                    )

                if chat_id in partners:

                    await manager.send_to_user(
                        partners[chat_id],
                        {
                            "type": "typing",
                            "chat_id": chat_id,
                            "user_id": user_id
                        },
                        chat_id
                    )

            # =================================================
            # READ
            # =================================================

            elif event_type in (
                "read",
                "read_chat"
            ):

                if chat_id is None:
                    continue

                if event_type == "read":

                    message_id = data.get(
                        "message_id"
                    )

                else:

                    message_id = None

                if (
                    message_id is not None
                    and (
                        isinstance(
                            message_id,
                            bool
                        )
                        or not isinstance(
                            message_id,
                            int
                        )
                    )
                ):
                    continue

                result = await db_call(
                    mark_read,
                    user_id,
                    chat_id,
                    message_id
                )

                if result:

                    for read_id in result["ids"]:

                        await manager.send_to_user(
                            result["sender"],
                            {
                                "type": "message_read",
                                "chat_id": chat_id,
                                "message_id": read_id,
                                "reader_id": user_id,
                                "read_at": result["read_at"].get(read_id),
                            },
                            chat_id
                        )

    except WebSocketDisconnect:
        pass

    except Exception:
        logger.exception(
            "WebSocket error for user %s",
            user_id
        )

    finally:

        if manager.disconnect(
            user_id,
            websocket
        ):

            spawn(
                go_offline(
                    user_id
                )
            )


# ============================================================
# WEBSOCKET ROUTES
# ============================================================

@app.websocket("/ws")
async def ws_global(
    websocket: WebSocket,
    token: str = Query(default="")
):
    await handle_socket(
        websocket,
        token,
        None
    )


@app.websocket("/ws/{chat_id}")
async def ws_chat(
    websocket: WebSocket,
    chat_id: int,
    token: str = Query(default="")
):
    await handle_socket(
        websocket,
        token,
        chat_id
    )

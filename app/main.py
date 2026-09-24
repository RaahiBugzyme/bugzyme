"""Bugzyme backend: REST + WebSocket chat (with Reply + Delete)."""
import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import (
    Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import models, schemas
from .connection_manager import ConnectionManager
from .database import Base, SessionLocal, engine, get_db

logger = logging.getLogger("bugzyme")

# ---------------------------------------------------------------- config
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "Set the SECRET_KEY environment variable (32+ chars). Generate one with: "
        "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "24"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
IDLE_TIMEOUT = 70  # seconds; clients must send {"type":"ping"} more often than this

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
manager = ConnectionManager()


def utcnow() -> datetime:
    """Naive UTC (the DB columns are naive)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat() + "Z"


# ---------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Creates only missing tables (safe next to alembic). Remove once
    # "alembic upgrade head" runs in your deploy command.
    Base.metadata.create_all(bind=engine)
    # After a restart nobody is connected, so nobody is online.
    with SessionLocal() as db:
        db.query(models.User).update({models.User.is_online: False}, synchronize_session=False)
        db.commit()
    yield


app = FastAPI(title="Bugzyme", lifespan=lifespan)


@app.middleware("http")
async def catch_unhandled(request: Request, call_next):
    """Turn crashes into a JSON 500 that still carries CORS headers
    (added BEFORE CORSMiddleware so CORS wraps it)."""
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # we use Bearer tokens, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- auth
def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        return None


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user_id = decode_token(token)
    if user_id is None:
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    return user


# ---------------------------------------------------------------- shared DB helpers (sync)
def other_user(chat: models.Chat, user_id: int) -> int:
    return chat.user2_id if chat.user1_id == user_id else chat.user1_id


def member_chat(db: Session, chat_id: int, user_id: int):
    chat = db.get(models.Chat, chat_id)
    if chat and user_id in (chat.user1_id, chat.user2_id):
        return chat
    return None


def find_chat(db: Session, a: int, b: int):
    return db.query(models.Chat).filter(
        or_(
            (models.Chat.user1_id == a) & (models.Chat.user2_id == b),
            (models.Chat.user1_id == b) & (models.Chat.user2_id == a),
        )
    ).first()


def get_partners(db: Session, user_id: int) -> dict[int, int]:
    """{chat_id: other_user_id} for all chats of the user."""
    chats = db.query(models.Chat).filter(
        or_(models.Chat.user1_id == user_id, models.Chat.user2_id == user_id)
    ).all()
    return {c.id: other_user(c, user_id) for c in chats}


def save_message(db: Session, sender_id: int, chat_id: int, content: str, reply_to_id: int | None = None):
    chat = member_chat(db, chat_id, sender_id)
    if not chat:
        return None

    if reply_to_id is not None:
        parent = db.get(models.Message, reply_to_id)
        if not parent or parent.chat_id != chat_id or parent.is_deleted:
            return None

    msg = models.Message(
        chat_id=chat_id,
        sender_id=sender_id,
        content=content,
        created_at=utcnow(),
        is_delivered=False,
        is_read=False,
        is_deleted=False,
        reply_to_id=reply_to_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return {
        "id": msg.id,
        "chat_id": chat_id,
        "sender_id": sender_id,
        "content": msg.content,
        "created_at": iso(msg.created_at),
        "is_delivered": False,
        "is_read": False,
        "is_deleted": False,
        "reply_to_id": msg.reply_to_id,
        "receiver_id": other_user(chat, sender_id),
    }


def soft_delete_message(db: Session, user_id: int, message_id: int, for_everyone: bool = True):
    msg = db.get(models.Message, message_id)
    if not msg or msg.is_deleted:
        return None

    chat = member_chat(db, msg.chat_id, user_id)
    if not chat:
        return None

    # Only the sender can delete for everyone
    if for_everyone and msg.sender_id != user_id:
        return None

    msg.is_deleted = True
    msg.deleted_at = utcnow()
    msg.content = None
    db.commit()

    return {
        "message_id": msg.id,
        "chat_id": msg.chat_id,
        "sender_id": msg.sender_id,
        "for_everyone": for_everyone,
        "receiver_id": other_user(chat, user_id),
    }


def mark_delivered(db: Session, ids: list[int]) -> None:
    if ids:
        db.query(models.Message).filter(models.Message.id.in_(ids)).update(
            {models.Message.is_delivered: True}, synchronize_session=False)
        db.commit()


def mark_read(db: Session, user_id: int, chat_id: int, message_id: int | None):
    """Mark the partner's messages as read. Returns {'sender': id, 'ids': [...]}."""
    chat = member_chat(db, chat_id, user_id)
    if not chat:
        return None
    q = db.query(models.Message).filter(
        models.Message.chat_id == chat_id,
        models.Message.sender_id != user_id,
        models.Message.is_read.is_not(True),
        models.Message.is_deleted.is_not(True),
    )
    if message_id is not None:
        q = q.filter(models.Message.id == message_id)
    rows = q.all()
    print("MARK READ ROWS:", [
    {
        "id": m.id,
        "sender_id": m.sender_id,
        "is_read": m.is_read,
        "is_delivered": m.is_delivered,
    }
    for m in rows
])
    for m in rows:
        m.is_read = True
        m.is_delivered = True
    db.commit()
    return {"sender": other_user(chat, user_id), "ids": [m.id for m in rows]}


def set_online(db: Session, user_id: int, online: bool):
    user = db.get(models.User, user_id)
    if not user:
        return None
    user.is_online = online
    if not online:
        user.last_seen = utcnow()
    db.commit()
    return iso(user.last_seen)


def load_context(db: Session, user_id: int, bound_chat_id: int | None):
    user = db.get(models.User, user_id)
    if not user:
        return None
    partners = get_partners(db, user_id)
    if bound_chat_id is not None and bound_chat_id not in partners:
        return None
    # messages sent to me while I was away are now delivered
    q = db.query(models.Message).filter(
        models.Message.chat_id.in_(list(partners) or [0]),
        models.Message.sender_id != user_id,
        models.Message.is_delivered.is_not(True),
        models.Message.is_deleted.is_not(True),
    )
    if bound_chat_id is not None:
        q = q.filter(models.Message.chat_id == bound_chat_id)
    pending = q.all()
    for m in pending:
        m.is_delivered = True
    db.commit()
    return {
        "username": user.username, "partners": partners,
        "delivered": [(m.sender_id, m.chat_id, m.id) for m in pending],
    }


async def db_call(fn, *args):
    """Run a sync DB function in a worker thread with its own short-lived session."""
    def run():
        with SessionLocal() as db:
            return fn(db, *args)
    return await run_in_threadpool(run)


async def safe_send(ws: WebSocket, payload: dict) -> None:
    with contextlib.suppress(Exception):
        await ws.send_json(payload)


async def broadcast_presence(user_id: int, partners: dict[int, int], status: str, last_seen=None):
    payload = {"type": "presence", "user_id": user_id, "status": status, "last_seen": last_seen}
    for chat_id, partner_id in partners.items():
        await manager.send_to_user(partner_id, payload, chat_id)


_bg_tasks: set = set()


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def go_offline(user_id: int) -> None:
    """Runs after a user's LAST socket closed: save last_seen, tell their chat partners."""
    try:
        if manager.is_online(user_id):  # reconnected already
            return
        last_seen = await db_call(set_online, user_id, False)
        if manager.is_online(user_id):  # reconnected while we were saving
            await db_call(set_online, user_id, True)
            return
        partners = await db_call(get_partners, user_id)
        await broadcast_presence(user_id, partners, "offline", last_seen)
    except Exception:
        logger.exception("go_offline failed for user %s", user_id)


async def process_message(
    sender_id,
    sender_name,
    chat_id,
    content,
    client_id=None,
    origin=None,
    reply_to_id=None,
):
    """Save + deliver one message. Used by both REST and WebSocket."""
    msg = await db_call(save_message, sender_id, chat_id, content, reply_to_id)
    if msg is None:
        return None

    if origin is not None:  # tell the sender the real message id right away
        await safe_send(origin, {
            "type": "message_sent",
            "chat_id": chat_id,
            "message_id": msg["id"],
            "client_id": client_id,
            "created_at": msg["created_at"],
            "reply_to_id": msg["reply_to_id"],
        })

    payload = {
        "type": "message",
        "chat_id": chat_id,
        "message_id": msg["id"],
        "sender_id": sender_id,
        "sender_name": sender_name,
        "content": msg["content"],
        "created_at": msg["created_at"],
        "reply_to_id": msg["reply_to_id"],
    }
    delivered = await manager.send_to_user(msg["receiver_id"], payload, chat_id)

    if delivered:
        await db_call(mark_delivered, [msg["id"]])
        msg["is_delivered"] = True
        event = {
            "type": "message_delivered",
            "chat_id": chat_id,
            "message_id": msg["id"],
        }
        if origin is not None:
            await safe_send(origin, event)
        else:
            await manager.send_to_user(sender_id, event, chat_id)

    return msg


# ---------------------------------------------------------------- REST
@app.get("/")
def home():
    return {"message": "Bugzyme Backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/register", response_model=schemas.UserResponse, status_code=201)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    email = user.email.strip().lower()
    username = user.username.strip()
    if db.query(models.User).filter(func.lower(models.User.email) == email).first():
        raise HTTPException(409, "Email already registered")
    if db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first():
        raise HTTPException(409, "Username already taken")
    new_user = models.User(
        username=username, email=email,
        hashed_password=password_hash.hash(user.password), is_online=False,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email or username already registered")
    db.refresh(new_user)
    return new_user


@app.post("/login", response_model=schemas.Token)
def login_user(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form_data.username.strip().lower()
    user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if not user or not password_hash.verify(form_data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_token(user.id), "token_type": "bearer"}


@app.get("/me", response_model=schemas.UserResponse)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@app.get("/users", response_model=list[schemas.UserPublic])
def get_users(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.username).all()
    return [
        schemas.UserPublic(
            id=u.id, username=u.username,
            is_online=manager.is_online(u.id),  # live truth, not the DB flag
            last_seen=u.last_seen,
        )
        for u in users
    ]


@app.post("/chats", response_model=schemas.ChatResponse)
def create_chat(chat: schemas.ChatCreate, current_user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if current_user.id == chat.user2_id:
        raise HTTPException(400, "You cannot chat with yourself")
    if not db.get(models.User, chat.user2_id):
        raise HTTPException(404, "User not found")
    existing = find_chat(db, current_user.id, chat.user2_id)
    if existing:
        return existing
    new_chat = models.Chat(user1_id=current_user.id, user2_id=chat.user2_id)
    db.add(new_chat)
    try:
        db.commit()
    except IntegrityError:  # two requests raced; the unique index caught it
        db.rollback()
        existing = find_chat(db, current_user.id, chat.user2_id)
        if existing:
            return existing
        raise
    db.refresh(new_chat)
    return new_chat


@app.get("/chats", response_model=list[schemas.ChatSummary])
def list_chats(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    me_id = current_user.id
    chats = db.query(models.Chat).filter(
        or_(models.Chat.user1_id == me_id, models.Chat.user2_id == me_id)).all()
    if not chats:
        return []
    ids = [c.id for c in chats]
    last_ids = dict(db.query(models.Message.chat_id, func.max(models.Message.id))
                    .filter(models.Message.chat_id.in_(ids),
                            models.Message.is_deleted.is_not(True))
                    .group_by(models.Message.chat_id).all())
    last_msgs = {}
    if last_ids:
        last_msgs = {m.chat_id: m for m in db.query(models.Message)
                     .filter(models.Message.id.in_(list(last_ids.values()))).all()}
    unread = dict(db.query(models.Message.chat_id, func.count(models.Message.id))
                  .filter(models.Message.chat_id.in_(ids),
                          models.Message.sender_id != me_id,
                          models.Message.is_read.is_not(True),
                          models.Message.is_deleted.is_not(True))
                  .group_by(models.Message.chat_id).all())
    partner_ids = {other_user(c, me_id) for c in chats}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(partner_ids)).all()}
    out = []
    for c in chats:
        u = users.get(other_user(c, me_id))
        if not u:
            continue
        last = last_msgs.get(c.id)
        out.append(schemas.ChatSummary(
            chat_id=c.id,
            user=schemas.UserPublic(id=u.id, username=u.username,
                                    is_online=manager.is_online(u.id), last_seen=u.last_seen),
            last_message=schemas.MessageResponse.model_validate(last) if last else None,
            unread_count=unread.get(c.id, 0),
        ))
    out.sort(key=lambda s: s.last_message.id if s.last_message else 0, reverse=True)
    return out


@app.post("/messages", response_model=schemas.MessageResponse, status_code=201)
async def send_message(
    message: schemas.MessageCreate,
    current_user: models.User = Depends(get_current_user),
):
    msg = await process_message(
        current_user.id,
        current_user.username,
        message.chat_id,
        message.content,
        reply_to_id=message.reply_to_id,
    )
    if msg is None:
        raise HTTPException(403, "You are not a member of this chat or invalid reply")
    return msg


@app.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    for_everyone: bool = True,
    current_user: models.User = Depends(get_current_user),
):
    result = await db_call(soft_delete_message, current_user.id, message_id, for_everyone)
    if result is None:
        raise HTTPException(403, "Cannot delete this message")

    event = {
        "type": "message_deleted",
        "chat_id": result["chat_id"],
        "message_id": result["message_id"],
        "for_everyone": result["for_everyone"],
    }
    await manager.send_to_user(current_user.id, event, result["chat_id"])
    await manager.send_to_user(result["receiver_id"], event, result["chat_id"])

    return {"ok": True, "message_id": message_id}


@app.get("/messages/{chat_id}", response_model=list[schemas.MessageResponse])
def get_messages(
    chat_id: int,
    limit: int = Query(200, ge=1, le=500),
    before_id: int | None = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = db.get(models.Chat, chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if current_user.id not in (chat.user1_id, chat.user2_id):
        raise HTTPException(403, "You are not a member of this chat")
    q = db.query(models.Message).filter(models.Message.chat_id == chat_id)
    if before_id is not None:
        q = q.filter(models.Message.id < before_id)
    rows = q.order_by(models.Message.id.desc()).limit(limit).all()
    rows.reverse()  # oldest first
    return rows


# ---------------------------------------------------------------- WebSocket
# /ws               -> one global socket per user (presence + every chat)   [used by raahi]
# /ws/{chat_id}     -> legacy per-chat socket (old test.html); same protocol
async def handle_socket(websocket: WebSocket, token: str, bound_chat_id: int | None):
    await websocket.accept()
    user_id = decode_token(token)
    if user_id is None:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return
    ctx = await db_call(load_context, user_id, bound_chat_id)
    if ctx is None:
        await websocket.close(code=1008, reason="Not allowed")
        return
    partners, username = ctx["partners"], ctx["username"]

    first = manager.connect(user_id, websocket, bound_chat_id)
    try:
        if first:
            await db_call(set_online, user_id, True)
            await broadcast_presence(user_id, partners, "online")
        await safe_send(websocket, {
            "type": "ready", "user_id": user_id,
            "online_user_ids": [p for p in set(partners.values()) if manager.is_online(p)],
        })
        for sender_id, chat_id, mid in ctx["delivered"]:
            await manager.send_to_user(
                sender_id, {"type": "message_delivered", "chat_id": chat_id, "message_id": mid}, chat_id)

        timeout = IDLE_TIMEOUT if bound_chat_id is None else None
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout)
            except asyncio.TimeoutError:
                await websocket.close(code=1001, reason="Idle timeout")
                break
            except ValueError:
                await safe_send(websocket, {"type": "error", "detail": "Invalid JSON"})
                continue
            if not isinstance(data, dict):
                continue
            kind = data.get("type")
            chat_id = bound_chat_id if bound_chat_id is not None else data.get("chat_id")
            if isinstance(chat_id, bool) or (chat_id is not None and not isinstance(chat_id, int)):
                chat_id = None

            if kind == "ping":
                await safe_send(websocket, {"type": "pong"})

            elif kind == "message":
                content = data.get("content")
                reply_to_id = data.get("reply_to_id")
                if not isinstance(content, str) or chat_id is None:
                    continue
                content = content.strip()
                if not content:
                    continue
                if len(content) > schemas.MAX_MESSAGE_LEN:
                    await safe_send(websocket, {"type": "error", "detail": "Message too long"})
                    continue
                msg = await process_message(
                    user_id, username, chat_id, content,
                    data.get("client_id"), websocket, reply_to_id,
                )
                if msg is None:
                    await safe_send(websocket, {"type": "error", "detail": "Not a member of this chat or invalid reply"})

            elif kind == "delete_message":
                mid = data.get("message_id")
                for_everyone = data.get("for_everyone", True)
                if not isinstance(mid, int):
                    continue
                result = await db_call(soft_delete_message, user_id, mid, for_everyone)
                if result:
                    event = {
                        "type": "message_deleted",
                        "chat_id": result["chat_id"],
                        "message_id": result["message_id"],
                        "for_everyone": result["for_everyone"],
                    }
                    await manager.send_to_user(user_id, event, result["chat_id"])
                    await manager.send_to_user(result["receiver_id"], event, result["chat_id"])

            elif kind == "typing":
                if chat_id is None:
                    continue
                if chat_id not in partners:  # chat may have been created after we connected
                    partners.clear()
                    partners.update(await db_call(get_partners, user_id))
                if chat_id in partners:
                    await manager.send_to_user(
                        partners[chat_id],
                        {"type": "typing", "chat_id": chat_id, "user_id": user_id}, chat_id)

            elif kind in ("read", "read_chat"):
                if chat_id is None:
                    continue
                mid = data.get("message_id") if kind == "read" else None
                if mid is not None and (isinstance(mid, bool) or not isinstance(mid, int)):
                    continue

                print("READ EVENT RECEIVED:", {
                    "kind": kind,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "message_id": mid
                })
                res = await db_call(mark_read, user_id, chat_id, mid)
                print("READ RESULT:", res)

                if res:
                    for read_id in res["ids"]:
                        await manager.send_to_user(
                            res["sender"],
                            {"type": "message_read", "chat_id": chat_id, "message_id": read_id},
                            chat_id
                        )
                   
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for user %s", user_id)
    finally:
        if manager.disconnect(user_id, websocket):
            # detached task: cleanup must finish even if this handler gets cancelled
            spawn(go_offline(user_id))


@app.websocket("/ws")
async def ws_global(websocket: WebSocket, token: str = Query(default="")):
    await handle_socket(websocket, token, None)


@app.websocket("/ws/{chat_id}")
async def ws_chat(websocket: WebSocket, chat_id: int, token: str = Query(default="")):
    await handle_socket(websocket, token, chat_id)
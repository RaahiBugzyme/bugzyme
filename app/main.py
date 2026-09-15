
from datetime import datetime

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketException,
    WebSocketDisconnect,
    status
)

from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm
)
from sqlalchemy import or_, and_, text
from sqlalchemy.orm import Session
from sqlalchemy.orm import Session
from pwdlib import PasswordHash
from jose import jwt
from sqlalchemy.orm import Session
from .connection_manager import ConnectionManager
from .database import engine, Base, get_db
from . import models, schemas
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
manager = ConnectionManager()


# Security
password_hash = PasswordHash.recommended()

SECRET_KEY = "my-super-secret-key"
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# Create database tables
Base.metadata.create_all(bind=engine)


# Get current user from JWT
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

        user = db.query(models.User).filter(
            models.User.id == int(user_id)
        ).first()

        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )

        return user

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )


# Home
@app.get("/")
def home():
    return {
        "message": "Bugzyme Backend is running"
    }


# Register user
@app.post("/register", response_model=schemas.UserResponse)
def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    hashed_password = password_hash.hash(user.password)

    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# Get all users
@app.get("/users", response_model=list[schemas.UserResponse])
def get_users(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.User).all()


# Login
@app.post("/login")
def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.User).filter(
        models.User.email == form_data.username
    ).first()

    if not existing_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    password_is_correct = password_hash.verify(
        form_data.password,
        existing_user.hashed_password
    )

    if not password_is_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    token_data = {
        "sub": str(existing_user.id)
    }

    access_token = jwt.encode(
        token_data,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

# Create chat
@app.post("/chats")
def create_chat(
    chat: schemas.ChatCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Prevent self chat
    if current_user.id == chat.user2_id:
        raise HTTPException(
            status_code=400,
            detail="You cannot chat with yourself"
        )

    # Validate target user
    target_user = db.query(models.User).filter(
        models.User.id == chat.user2_id
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # Check duplicate chat
    existing_chat = db.query(models.Chat).filter(
        or_(
            and_(
                models.Chat.user1_id == current_user.id,
                models.Chat.user2_id == chat.user2_id
            ),
            and_(
                models.Chat.user1_id == chat.user2_id,
                models.Chat.user2_id == current_user.id
            )
        )
    ).first()

    if existing_chat:
        return existing_chat

    # Create new chat
    new_chat = models.Chat(
        user1_id=current_user.id,
        user2_id=chat.user2_id
    )

    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)

    return new_chat


# Send message
@app.post("/messages")
def send_message(
    message: schemas.MessageCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_message = models.Message(
        chat_id=message.chat_id,
        sender_id=current_user.id,
        content=message.content
    )

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return new_message


# Get chat messages
@app.get("/messages/{chat_id}")
def get_messages(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(models.Chat).filter(
        models.Chat.id == chat_id
    ).first()

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found"
        )

    if current_user.id not in [chat.user1_id, chat.user2_id]:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this chat"
        )

    messages = db.query(models.Message).filter(
        models.Message.chat_id == chat_id
    ).all()

    return messages

# Create chat

@app.websocket("/ws/{chat_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    chat_id: int,
    token: str,
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if not user_id:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION
            )

        user_id = int(user_id)

    except WebSocketException:
        raise

    except Exception:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION
        )

    # Check chat exists
    chat = db.query(models.Chat).filter(
        models.Chat.id == chat_id
    ).first()

    if not chat:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION
        )

    # Check user belongs to this chat
    if user_id not in [chat.user1_id, chat.user2_id]:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION
        )

    # Find receiver
    if user_id == chat.user1_id:
        receiver_id = chat.user2_id
    else:
        receiver_id = chat.user1_id

    # Connect user
    await manager.connect(
        user_id,
        websocket
    )

    # Update online status
    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    user.is_online = True
    db.commit()

    # Notify receiver
    await manager.notify_presence(
        user_id,
        "online",
        receiver_id
    )

    try:
        while True:

            data = await websocket.receive_json()

            # Debug: show exact data received from client
            print("RAW DATA:", repr(data))

            # -------------------------
            # NORMAL MESSAGE
            # -------------------------
            if data.get("type") == "message":

                message = data.get("content", "")

                print("Normal message received")
                print("Sender:", user_id)
                print("Receiver:", receiver_id)
                print("Message:", repr(message))

                # Don't save empty messages
                if not message.strip():
                    print("EMPTY MESSAGE - NOT SAVING")
                    continue

                # Save message in database
                new_message = models.Message(
                    chat_id=chat_id,
                    sender_id=user_id,
                    content=message
                )

                db.add(new_message)
                db.commit()
                db.refresh(new_message)

                print(
                    "Saved message:",
                    new_message.id,
                    repr(new_message.content)
                )

                # Check if receiver is connected
                receiver_websocket = manager.active_connections.get(
                    receiver_id
                )

                if receiver_websocket:

                    # Send message to receiver
                    await manager.send_personal_message(
                        {
                            "type": "message",
                            "message_id": new_message.id,
                            "sender_id": user_id,
                            "sender_name": user.username,
                            "content": new_message.content,
                            "created_at": new_message.created_at.isoformat()
                        },
                        receiver_id
                    )

                    # Mark message as delivered
                    new_message.is_delivered = True
                    db.commit()

                    # Send delivery confirmation to sender
                    await manager.send_personal_message(
                        {
                            "type": "message_delivered",
                            "message_id": new_message.id
                        },
                        user_id
                    )

            # -------------------------
            # TYPING INDICATOR
            # -------------------------
            elif data.get("type") == "typing":

                print("User is typing")

                await manager.send_personal_message(
                    {
                        "type": "typing"
                    },
                    receiver_id
                )

            # -------------------------
            # READ STATUS
            # -------------------------
            elif data.get("type") == "read":

                message_id = data.get("message_id")

                message = db.query(models.Message).filter(
                    models.Message.id == message_id,
                    models.Message.chat_id == chat_id
                ).first()

                if message:

                    message.is_read = True
                    db.commit()

                    # Notify sender that message was read
                    await manager.send_personal_message(
                        {
                            "type": "message_read",
                            "message_id": message_id
                        },
                        message.sender_id
                    )

    except WebSocketDisconnect:

        # Remove connection
        manager.disconnect(user_id)

        # Update offline status
        user = db.query(models.User).filter(
            models.User.id == user_id
        ).first()

        user.is_online = False
        user.last_seen = datetime.utcnow()

        db.commit()

        # Notify receiver
        await manager.notify_presence(
            user_id,
            "offline",
            receiver_id
        )

@app.post("/reset-database")
def reset_database(secret: str, db: Session = Depends(get_db)):

    if secret != "TEMP_RESET_2026":
        raise HTTPException(
            status_code=403,
            detail="Forbidden"
        )

    db.query(models.Message).delete(
        synchronize_session=False
    )

    db.query(models.Chat).delete(
        synchronize_session=False
    )

    db.query(models.User).delete(
        synchronize_session=False
    )

    db.execute(
        text("ALTER SEQUENCE users_id_seq RESTART WITH 1")
    )

    db.commit()

    return {
        "message": "Database reset successfully"
    }
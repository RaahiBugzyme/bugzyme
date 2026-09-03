from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.message import MessageCreate
from app.schemas.user import UserCreate, UserUpdate, UserLogin
from app.schemas.conversation import ConversationCreate
from app.database.database import get_db

from app.database.models import (
    User,
    Conversation,
    ConversationParticipant,
    Message
)

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)



# Create FastAPI Application

app = FastAPI()



# Home / Health Check

@app.get("/")
def home():
    # Simple endpoint to check whether the backend is running
    return {"message": "Bugzyme Backend is Running"}



# User APIs

@app.post("/users")
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    # Convert the plain-text password into a secure bcrypt hash
    hashed_password = hash_password(user.password)

    # Create a new User database object
    new_user = User(
        username=user.username,
        password_hash=hashed_password
    )

    # Add the user to the database session
    db.add(new_user)

    # Save the user permanently in the database
    db.commit()

    # Refresh the object to get the generated user ID
    db.refresh(new_user)

    return new_user



# Login / Authentication

@app.post("/login")
def login(
    user_data: UserLogin,
    db: Session = Depends(get_db)
):
    # Find the user using the username provided during login
    user = db.query(User).filter(
        User.username == user_data.username
    ).first()

    # If the username does not exist, reject the login
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Compare the plain-text password with the bcrypt hash
    # stored in the database
    if not verify_password(
        user_data.password,
        user.password_hash
    ):
        # Reject the login if the password is incorrect
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Create a JWT access token after successful authentication
    #
    # "sub" stores the user's ID.
    # The token will later be used to identify the logged-in user.
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username
        }
    )

    # Send the JWT token back to the client
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }



# Get All Users

@app.get("/users")
def get_users(
    db: Session = Depends(get_db)
):
    # Fetch all users from the database
    users = db.query(User).all()

    return users



# Get User By ID

@app.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    # Find a user by their ID
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    return user



# Update User

@app.put("/users/{user_id}")
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db)
):
    # Find the user that needs to be updated
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    # Return an error if the user does not exist
    if user is None:
        return {"message": "User not found"}

    # Update the username
    user.username = user_data.username

    # Save the updated data
    db.commit()

    # Refresh the object with the latest database values
    db.refresh(user)

    return user



# Delete User

@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    # Find the user that needs to be deleted
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    # Return an error if the user does not exist
    if user is None:
        return {"message": "User not found"}

    # Delete the user from the database
    db.delete(user)

    # Save the changes
    db.commit()

    return {"message": "User deleted successfully"}



# Conversation APIs

@app.post("/conversations")
def create_conversation(
    conversation_data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check that the target user exists
    target_user = db.query(User).filter(
        User.id == conversation_data.user_id
    ).first()

    if target_user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # Create a new conversation
    conversation = Conversation()

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    # Add current user as a participant
    participant1 = ConversationParticipant(
        conversation_id=conversation.id,
        user_id=current_user.id
    )

    # Add target user as a participant
    participant2 = ConversationParticipant(
        conversation_id=conversation.id,
        user_id=target_user.id
    )

    db.add(participant1)
    db.add(participant2)

    db.commit()

    return conversation


# Add User To Conversation

@app.post("/conversations/{conversation_id}/participants")
def add_participant(
    conversation_id: int,
    user_id: int,
    db: Session = Depends(get_db)
):
    # Create a relationship between a user and a conversation
    participant = ConversationParticipant(
        conversation_id=conversation_id,
        user_id=user_id
    )

    # Add the relationship to the database session
    db.add(participant)

    # Save the relationship
    db.commit()

    # Refresh to get the generated participant ID
    db.refresh(participant)

    return participant



# Message APIs

@app.post("/messages")
def create_message(
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    participant = db.query(
        ConversationParticipant
    ).filter(
        ConversationParticipant.conversation_id == message.conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if participant is None:
        raise HTTPException(
            status_code=403,
            detail="User is not a participant of this conversation"
        )

    new_message = Message(
        conversation_id=message.conversation_id,
        sender_id=current_user.id,
        content=message.content
    )

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return new_message


# Get Conversation Messages

@app.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    participant = db.query(
        ConversationParticipant
    ).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    ).first()

    if participant is None:
        raise HTTPException(
            status_code=403,
            detail="User is not a participant of this conversation"
        )

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).all()

    return messages


@app.get("/conversations")
def get_my_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversations = db.query(
        ConversationParticipant
    ).filter(
        ConversationParticipant.user_id == current_user.id
    ).all()

    return conversations
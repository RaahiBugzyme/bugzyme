
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base

# Base is the common foundation for all our database models.
# Every model (User, Conversation, Message, etc.) inherits from Base.
Base = declarative_base()



# User Table

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Username must be unique for every user.
    username = Column(String, unique=True, index=True)

    # We store the hashed password, NOT the original password.
    password_hash = Column(String)



# Conversation Table

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)



# Conversation Participants Table

class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id = Column(Integer, primary_key=True, index=True)

    # Which conversation does this participant belong to?
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id")
    )

    # Which user is participating?
    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )



# Message Table

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    # Conversation in which the message was sent.
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id")
    )

    # User who sent the message.
    sender_id = Column(
        Integer,
        ForeignKey("users.id")
    )

    # Actual message text.
    content = Column(String)

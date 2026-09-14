from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)

    chats_as_user1 = relationship(
        "Chat",
        foreign_keys="Chat.user1_id",
        back_populates="user1"
    )

    chats_as_user2 = relationship(
        "Chat",
        foreign_keys="Chat.user2_id",
        back_populates="user2"
    )

    sent_messages = relationship(
        "Message",
        foreign_keys="Message.sender_id",
        back_populates="sender"
    )


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)

    user1_id = Column(
        Integer,
        ForeignKey("users.id"),
        index=True
    )

    user2_id = Column(
        Integer,
        ForeignKey("users.id"),
        index=True
    )

    user1 = relationship(
        "User",
        foreign_keys=[user1_id],
        back_populates="chats_as_user1"
    )

    user2 = relationship(
        "User",
        foreign_keys=[user2_id],
        back_populates="chats_as_user2"
    )

    messages = relationship(
        "Message",
        back_populates="chat"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    chat_id = Column(
        Integer,
        ForeignKey("chats.id"),
        index=True
    )

    sender_id = Column(
        Integer,
        ForeignKey("users.id"),
        index=True
    )

    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_delivered = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)

    chat = relationship(
        "Chat",
        back_populates="messages"
    )

    sender = relationship(
        "User",
        foreign_keys=[sender_id],
        back_populates="sent_messages"
    )




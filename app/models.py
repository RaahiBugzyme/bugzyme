from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(30), unique=True, index=True, nullable=False)
    email = Column(String(254), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_online = Column(Boolean, default=False, nullable=False)
    last_seen = Column(DateTime, nullable=True)

    chats_as_user1 = relationship(
        "Chat",
        foreign_keys="Chat.user1_id",
        back_populates="user1",
    )
    chats_as_user2 = relationship(
        "Chat",
        foreign_keys="Chat.user2_id",
        back_populates="user2",
    )
    sent_messages = relationship(
        "Message",
        foreign_keys="Message.sender_id",
        back_populates="sender",
    )


class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        UniqueConstraint("user1_id", "user2_id", name="uq_chat_users"),
        Index("ix_chats_user1", "user1_id"),
        Index("ix_chats_user2", "user2_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user1 = relationship(
        "User",
        foreign_keys=[user1_id],
        back_populates="chats_as_user1",
    )
    user2 = relationship(
        "User",
        foreign_keys=[user2_id],
        back_populates="chats_as_user2",
    )
    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_id_id", "chat_id", "id"),
        Index("ix_messages_unread", "chat_id", "sender_id", "is_read"),
        Index("ix_messages_undelivered", "chat_id", "sender_id", "is_delivered"),
    )

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(String(2000), nullable=True)  # deleted messages → None
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_delivered = Column(Boolean, default=False, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)

    # Delete + Reply support
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)

    chat = relationship("Chat", back_populates="messages")
    sender = relationship(
        "User",
        foreign_keys=[sender_id],
        back_populates="sent_messages",
    )
    reply_to = relationship(
        "Message",
        remote_side=[id],
        foreign_keys=[reply_to_id],
        backref="replies",
    )
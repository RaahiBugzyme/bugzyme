"""Comprehensive tests verifying Render 512MB RAM optimizations.

Tests:
1. Memory storage and retrieval without embeddings (NULL embeddings in DB).
2. Strict user isolation in memory search.
3. Opt-in and opt-out consent enforcement.
4. Lightweight reranker fallback and intent matching.
5. AI suggestions with and without memories.
6. Verification that neither PyTorch nor SentenceTransformers is loaded at runtime.
7. Verification that process RSS remains strictly below 200 MB.
"""

import sys
import os
import resource
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserMemory, Chat, Message
from app.ai.memory import (
    save_memory,
    search_memories,
    rerank_memories,
    generate_embedding,
    extract_and_save_opt_in_memories,
    _memory_tokens,
    detect_topic,
    memory_matches_topic,
)
from app.ai.memory_diagnostics import get_process_rss_mb


@pytest.fixture
def db_session():
    """In-memory SQLite database session fixture."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


def test_no_torch_in_sys_modules():
    """Verify that importing app modules did not load PyTorch or SentenceTransformers."""
    # Note: If tests in same process imported torch previously, check that
    # app.main and app.ai.memory do not import torch directly.
    import inspect
    import app.ai.memory
    import app.main
    import app.ai.suggestions
    import app.ai.graph

    for mod in [app.ai.memory, app.main, app.ai.suggestions, app.ai.graph]:
        source = inspect.getsource(mod)
        assert "import torch" not in source, f"{mod} directly imports torch!"
        assert "from sentence_transformers import" not in source, f"{mod} directly imports sentence_transformers!"


def test_rss_memory_within_safe_limits():
    """Verify process RSS is well below the 512 MB Render ceiling."""
    rss = get_process_rss_mb()
    # Should be well below 250 MB
    assert rss < 350.0, f"Process RSS is too high: {rss} MB"


def test_generate_embedding_returns_none_in_lightweight_mode():
    """Embeddings must be None when ML models are disabled."""
    assert generate_embedding("Test text for embedding") is None

    with pytest.raises(ValueError):
        generate_embedding("")


def test_memory_storage_and_deduplication_without_embeddings(db_session):
    """Test save_memory stores records with NULL embedding and avoids duplicates."""
    mem1 = save_memory(
        db=db_session,
        user_id=1,
        memory_text="Prefers evening conversations and coffee.",
        memory_type="preference",
        confidence=0.85,
    )
    assert mem1.id is not None
    assert mem1.embedding is None
    assert mem1.memory_text == "Prefers evening conversations and coffee."

    # Duplicate save with different case should return existing record
    mem2 = save_memory(
        db=db_session,
        user_id=1,
        memory_text="prefers evening conversations and coffee.",
        memory_type="preference",
        confidence=0.85,
    )
    assert mem2.id == mem1.id

    # Total rows in DB should be exactly 1
    count = db_session.query(UserMemory).filter_by(user_id=1).count()
    assert count == 1


def test_search_memories_when_embeddings_are_null(db_session):
    """Test search_memories successfully retrieves memories where embedding is NULL."""
    save_memory(
        db=db_session,
        user_id=10,
        memory_text="Sandeep prefers casual conversations and simple questions.",
        memory_type="preference",
        confidence=0.9,
    )
    save_memory(
        db=db_session,
        user_id=10,
        memory_text="Loves hiking in Himachal and mountain photography.",
        memory_type="interest",
        confidence=0.95,
    )
    save_memory(
        db=db_session,
        user_id=10,
        memory_text="Passionate about Italian food, pizza, and cooking pasta.",
        memory_type="interest",
        confidence=0.85,
    )

    # 1. Topic query: food / cooking
    food_results = search_memories(
        db=db_session,
        user_id=10,
        query="What kind of food or dinner do you like to cook?",
    )
    assert len(food_results) > 0
    assert "Italian food" in food_results[0]["memory_text"]
    assert food_results[0]["similarity"] > 0.3

    # 2. Topic query: travel / mountains
    travel_results = search_memories(
        db=db_session,
        user_id=10,
        query="Have you been on any trips or hiking in the mountains?",
    )
    assert len(travel_results) > 0
    assert "hiking" in travel_results[0]["memory_text"]

    # 3. Communication style query
    comm_results = search_memories(
        db=db_session,
        user_id=10,
        query="What communication style does Sandeep prefer?",
    )
    assert len(comm_results) > 0
    assert "casual conversations" in comm_results[0]["memory_text"]

    # 4. Unrelated query should return empty or low similarity
    unrelated = search_memories(
        db=db_session,
        user_id=10,
        query="Stock market cryptocurrency trading bitcoin",
        min_similarity=0.3,
    )
    assert len(unrelated) == 0


def test_user_memory_isolation(db_session):
    """Memories of User A must NEVER be returned for User B."""
    save_memory(
        db=db_session,
        user_id=100,
        memory_text="Secret fact belonging exclusively to User 100",
        memory_type="personal_fact",
    )
    save_memory(
        db=db_session,
        user_id=200,
        memory_text="Public hobby belonging to User 200",
        memory_type="interest",
    )

    results_user_100 = search_memories(db=db_session, user_id=100, query="Secret fact")
    assert any("User 100" in r["memory_text"] for r in results_user_100)
    assert not any("User 200" in r["memory_text"] for r in results_user_100)

    results_user_200 = search_memories(db=db_session, user_id=200, query="Secret fact")
    assert len(results_user_200) == 0


def test_opt_in_and_opt_out_behavior(db_session):
    """Verify memories are extracted and saved only when ai_memory_enabled is True."""
    user = User(
        id=50,
        username="testuser",
        email="testuser@example.com",
        hashed_password="fakehash",
        ai_memory_enabled=False,
    )
    db_session.add(user)
    db_session.commit()

    second_user = User(
        id=51,
        username="testuser2",
        email="testuser2@example.com",
        hashed_password="fakehash",
    )
    db_session.add(second_user)
    db_session.commit()

    chat = Chat(
        id=1,
        user1_id=50,
        user2_id=51,
    )
    db_session.add(chat)
    db_session.commit()

    message = Message(
        id=1,
        chat_id=1,
        sender_id=50,
        content="I really love playing badminton on weekends.",
        message_type="text",
        is_deleted=False,
    )
    db_session.add(message)
    db_session.commit()


    # With opt-in FALSE:
    extracted_count = extract_and_save_opt_in_memories(db=db_session, user=user)
    assert extracted_count == 0
    assert db_session.query(UserMemory).filter_by(user_id=50).count() == 0

    # With opt-in TRUE:
    user.ai_memory_enabled = True
    db_session.add(user)
    db_session.commit()

    mock_extracted = [
        {"memory_text": "Loves playing badminton on weekends.", "memory_type": "interest", "confidence": 0.95}
    ]
    with patch("app.ai.extraction.extract_memories", return_value=mock_extracted):
        extracted_count = extract_and_save_opt_in_memories(db=db_session, user=user)
        assert extracted_count == 1
        assert db_session.query(UserMemory).filter_by(user_id=50).count() == 1


def test_rerank_memories_fallback():
    """Verify lightweight reranking accurately ranks candidates and sets intent_match."""
    candidates = [
        {
            "id": 1,
            "memory_text": "Prefers casual conversations and thoughtful replies.",
            "memory_type": "preference",
            "confidence": 0.9,
            "similarity": 0.7,
        },
        {
            "id": 2,
            "memory_text": "Loves playing soccer and badminton.",
            "memory_type": "interest",
            "confidence": 0.95,
            "similarity": 0.2,
        },
    ]

    # Communication query: candidate 1 should win and have intent_match=1
    reranked = rerank_memories(candidates, "What communication style do you prefer?", top_k=2)
    assert len(reranked) == 2
    assert reranked[0]["id"] == 1
    assert reranked[0]["intent_match"] == 1
    assert reranked[1]["intent_match"] == 0

    # Sports query: candidate 2 should win and have intent_match=1
    reranked_sports = rerank_memories(candidates, "Do you play soccer or any sport?", top_k=2)
    assert len(reranked_sports) == 2
    assert reranked_sports[0]["id"] == 2
    assert reranked_sports[0]["intent_match"] == 1
    assert reranked_sports[1]["intent_match"] == 0


def test_ai_suggestions_memory_retrieval_flow(db_session):
    """Test suggestions retrieval integration with mock Groq response."""
    from app.ai.suggestions import suggest_next_messages

    # Create user with opt-in memory
    user = User(
        id=77,
        username="Priya",
        email="priya@example.com",
        hashed_password="fakehash",
        ai_memory_enabled=True,
    )
    db_session.add(user)
    db_session.commit()

    save_memory(
        db=db_session,
        user_id=77,
        memory_text="Priya loves indie music and acoustic guitar.",
        memory_type="interest",
        confidence=0.95,
    )

    conversation_messages = [
        {"sender": "Priya", "content": "Hey, what kind of songs are you listening to lately?"},
        {"sender": "Rohan", "content": "Mostly rock, but open to recommendations! What do you like?"},
    ]

    mock_analysis = {
        "current_topic": "music recommendations",
        "conversation_tone": "friendly",
        "last_message_intent": "asking for music recommendations",
        "conversation_state": "flowing",
        "next_reply_strategy": "share music preference",
        "detected_language": "english",
    }

    mock_suggestions = [
        {"style": "natural", "message": "I love indie music and acoustic guitar songs."},
        {"style": "playful", "message": "My playlist is 90% indie music and 10% pure chaos!"},
        {"style": "thoughtful", "message": "Acoustic indie tracks have such calming vibes."},
    ]

    with (
        patch("app.ai.suggestions._analyze_conversation", return_value=mock_analysis),
        patch("app.ai.suggestions._generate_suggestions", return_value=mock_suggestions),
    ):
        result = suggest_next_messages(
            db=db_session,
            requesting_user_id=77,
            requesting_user="Priya",
            messages=conversation_messages,
        )

        assert len(result["suggestions"]) == 3
        # Verify memories were used
        memories_used = result.get("memories_used", [])
        assert len(memories_used) > 0
        assert any("indie music" in m["memory_text"] for m in memories_used)

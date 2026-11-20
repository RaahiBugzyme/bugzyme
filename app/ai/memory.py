import logging
import os
import re
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models import UserMemory, Message

logger = logging.getLogger("bugzyme.memory")

EMBEDDING_MODEL_NAME = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Similarity threshold for filtering weak memory matches
DEFAULT_MIN_SIMILARITY = 0.15


# ---------------------------------------------------------
# OPTIONAL LAZY ML LOADER (DISABLED BY DEFAULT FOR LOW MEMORY)
# ---------------------------------------------------------

_EMBEDDING_MODEL = None
_RERANKER_MODEL = None


def _is_heavy_ml_enabled() -> bool:
    """Return True only if heavyweight ML models are explicitly enabled via env."""
    return os.getenv("ENABLE_HEAVY_AI", "false").lower() in ("true", "1", "yes")


def get_embedding_model():
    """Lazily load SentenceTransformer only if explicitly enabled."""
    global _EMBEDDING_MODEL
    if not _is_heavy_ml_enabled():
        return None
    if _EMBEDDING_MODEL is None:
        try:
            import importlib
            st_module = importlib.import_module("sentence_transformers")
            _EMBEDDING_MODEL = st_module.SentenceTransformer(EMBEDDING_MODEL_NAME)
        except Exception as exc:
            logger.warning("Could not load SentenceTransformer: %s", exc)
            return None
    return _EMBEDDING_MODEL


def get_reranker_model():
    """Lazily load CrossEncoder only if explicitly enabled."""
    global _RERANKER_MODEL
    if not _is_heavy_ml_enabled():
        return None
    if _RERANKER_MODEL is None:
        try:
            import importlib
            st_module = importlib.import_module("sentence_transformers")
            _RERANKER_MODEL = st_module.CrossEncoder(RERANKER_MODEL_NAME)
        except Exception as exc:
            logger.warning("Could not load CrossEncoder: %s", exc)
            return None
    return _RERANKER_MODEL


# ---------------------------------------------------------
# EMBEDDINGS
# ---------------------------------------------------------

def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate vector embedding if ML is enabled; otherwise return None.

    This keeps memory consumption negligible in Render (512 MB limit)
    while preserving the full memory storage and retrieval functionality.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text cannot be empty.")

    model = get_embedding_model()
    if model is None:
        return None

    try:
        embedding = model.encode(text.strip(), normalize_embeddings=True)
        return embedding.tolist()
    except Exception as exc:
        logger.warning("Embedding generation failed, falling back to None: %s", exc)
        return None


# ---------------------------------------------------------
# MEMORY STORAGE
# ---------------------------------------------------------

def save_memory(
    db: Session,
    user_id: int,
    memory_text: str,
    memory_type: str = "general",
    confidence: float = 0.8,
    source_message_id: Optional[int] = None,
) -> UserMemory:
    """Save a memory for one user, avoiding exact duplicates."""

    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    if not isinstance(memory_text, str) or not memory_text.strip():
        raise ValueError("Memory text cannot be empty.")

    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1.")

    if not isinstance(memory_type, str) or not memory_type.strip():
        raise ValueError("memory_type cannot be empty.")

    normalized_text = memory_text.strip()

    existing_memory = (
        db.query(UserMemory)
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.memory_text.ilike(normalized_text),
        )
        .first()
    )

    if existing_memory:
        if source_message_id is not None and existing_memory.source_message_id is None:
            existing_memory.source_message_id = source_message_id
            db.commit()
        return existing_memory

    embedding = generate_embedding(normalized_text)

    memory = UserMemory(
        user_id=user_id,
        memory_text=normalized_text,
        memory_type=memory_type.strip().lower(),
        confidence=confidence,
        source_message_id=source_message_id,
        embedding=embedding,
    )

    try:
        db.add(memory)
        db.commit()
        db.refresh(memory)
        return memory
    except Exception:
        db.rollback()
        raise


def extract_and_save_opt_in_memories(db: Session, user, messages=None) -> int:
    """Extract opted-in user's own unprocessed messages across all chats."""

    if not getattr(user, "ai_memory_enabled", False):
        return 0

    cursor = user.ai_memory_processed_through_message_id

    query = db.query(Message).filter(
        Message.sender_id == user.id,
        Message.is_deleted.is_(False),
        Message.message_type == "text",
        Message.content.isnot(None),
        Message.content != "",
    )

    if cursor is not None:
        query = query.filter(Message.id > cursor)

    batch = (
        query
        .order_by(Message.id.asc())
        .limit(30)
        .all()
    )

    if not batch:
        return 0

    eligible_types = {
        "preference",
        "interest",
        "communication_style",
        "goal",
        "project",
    }

    from app.ai.extraction import extract_memories

    transcript = "\n".join(
        f"{user.username}: {item.content.strip()}"
        for item in batch
    )

    extracted = extract_memories(transcript)

    source_message_id = batch[-1].id
    saved = 0

    for item in extracted:
        if not isinstance(item, dict):
            continue

        memory_type = item.get("memory_type")
        confidence = item.get("confidence", 0)
        memory_text = item.get("memory_text", "")

        if memory_type not in eligible_types:
            continue

        if not isinstance(confidence, (int, float)) or confidence < 0.7:
            continue

        if not isinstance(memory_text, str) or not memory_text.strip():
            continue

        save_memory(
            db=db,
            user_id=user.id,
            memory_text=memory_text,
            memory_type=memory_type,
            confidence=confidence,
            source_message_id=source_message_id,
        )
        saved += 1

    user.ai_memory_processed_through_message_id = source_message_id
    db.add(user)
    db.commit()

    return saved


# ---------------------------------------------------------
# TOPIC DETECTION & KEYWORDS
# ---------------------------------------------------------

TOPIC_KEYWORDS = {
    "sports": [
        "sport", "sports", "football", "soccer", "cricket",
        "badminton", "basketball", "tennis", "volleyball",
        "hockey", "swimming", "athletics", "chess",
        "table tennis", "running", "cycling",
    ],
    "music": [
        "music", "song", "songs", "singing", "singer",
        "indie music", "pop music", "rock music",
        "classical music", "playlist", "playlists",
    ],
    "travel": [
        "travel", "travelling", "traveling", "trip", "trips",
        "holiday", "holidays", "vacation", "vacations",
        "exploring places",
    ],
    "food": [
        "food", "cooking", "cuisine", "restaurant",
        "restaurants", "foodie", "baking", "coffee",
        "cafe", "cafes", "café", "cafés",
    ],
    "movies": [
        "movie", "movies", "film", "films", "cinema",
        "sitcom", "sitcoms", "tv show", "tv shows",
        "web series",
    ],
    "reading": [
        "reading", "read books", "books", "novels",
        "fiction", "nonfiction",
    ],
    "technology": [
        "technology", "tech", "programming", "coding",
        "artificial intelligence", "machine learning",
        "software development",
    ],
    "career": [
        "career", "job", "jobs", "profession",
        "career goals", "professional goals",
    ],
}

INTEREST_WORDS = [
    "interest", "interests", "hobby", "hobbies",
    "like", "likes", "enjoy", "enjoys",
    "favorite", "favourite", "prefer", "preferences",
]

COMMUNICATION_KEYWORDS = [
    "communication", "communication style", "style", "tone",
    "casual", "direct", "playful", "thoughtful", "conversational",
    "reply", "response", "talk", "speak",
]

PREFERENCE_KEYWORDS = [
    "prefer", "preference", "preferences", "preferred",
    "priority", "favorite", "favourite",
]


def contains_keyword(text: str, keywords: List[str]) -> bool:
    """Match complete words or phrases, ignoring case."""
    text = text.casefold()
    for keyword in keywords:
        pattern = (
            r"(?<!\w)"
            + re.escape(keyword.casefold())
            + r"(?!\w)"
        )
        if re.search(pattern, text):
            return True
    return False


def detect_topic(query: str) -> Optional[str]:
    """Identify a specific topic mentioned in the query."""
    for topic, keywords in TOPIC_KEYWORDS.items():
        if contains_keyword(query, keywords):
            return topic
    return None


def memory_matches_topic(memory_text: str, topic: Optional[str]) -> bool:
    """Check whether the actual memory text mentions the topic."""
    if not topic:
        return False
    keywords = TOPIC_KEYWORDS.get(topic, [])
    return contains_keyword(memory_text, keywords)


# ---------------------------------------------------------
# LIGHTWEIGHT TOKENIZATION & MATCHING
# ---------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "does", "do",
    "for", "from", "how", "i", "in", "is", "it", "me", "my",
    "of", "on", "or", "that", "the", "their", "them", "they",
    "this", "to", "u", "was", "what", "when", "where", "which",
    "who", "why", "with", "you", "your", "he", "she", "his", "her",
    "we", "our", "us", "so", "but", "by", "if", "than", "then",
}

_SYNONYM_EXPANSIONS = {
    "communication": {
        "conversation", "conversational", "talk", "speak",
        "reply", "response", "casual", "direct", "playful",
        "thoughtful",
    },
    "style": {
        "tone", "casual", "direct", "playful",
        "thoughtful", "conversational",
    },
    "interest": {"hobby", "like", "enjoy", "favorite"},
    "prefer": {"preference", "favorite", "like", "enjoy"},
    "preference": {"prefer", "favorite", "like", "enjoy"},
    "career": {"job", "profession", "work", "office"},
    "trip": {"travel", "vacation", "holiday"},
    "cooking": {"food", "baking", "recipe", "cuisine"},
}


def _memory_tokens(text: str) -> Set[str]:
    """Extract, normalize, stem and synonym-expand meaningful words."""
    words = re.findall(r"[a-z0-9]+", text.casefold())
    normalized: Set[str] = set()

    for word in words:
        if len(word) <= 2 or word in _STOP_WORDS:
            continue
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("ing") and len(word) > 5:
            word = word[:-3]
        elif word.endswith("es") and len(word) > 4:
            word = word[:-2]
        elif word.endswith("s") and len(word) > 3:
            word = word[:-1]
        elif word.endswith("ed") and len(word) > 4:
            word = word[:-2]
        normalized.add(word)

    expanded = set(normalized)
    for word in normalized:
        expanded.update(_SYNONYM_EXPANSIONS.get(word, set()))

    return expanded


# ---------------------------------------------------------
# MEMORY SEARCH
# ---------------------------------------------------------

def search_memories(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 10,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> List[Dict[str, Any]]:
    """Retrieve memories for one user using lightweight relevance matching.

    Maintains strict user isolation: only memories belonging to user_id are returned.
    Functions reliably whether vector embeddings are populated or NULL.
    """
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    if not 0.0 <= min_similarity <= 1.0:
        raise ValueError("min_similarity must be between 0 and 1.")

    query_stripped = query.strip()
    query_tokens = _memory_tokens(query_stripped)
    target_topic = detect_topic(query_stripped)
    asks_about_interests = contains_keyword(query_stripped, INTEREST_WORDS)
    query_is_comm = contains_keyword(query_stripped, COMMUNICATION_KEYWORDS)
    query_is_pref = contains_keyword(query_stripped, PREFERENCE_KEYWORDS)

    # Fetch candidate memories for this user (user isolation guaranteed)
    rows = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user_id)
        .order_by(UserMemory.created_at.desc(), UserMemory.id.desc())
        .limit(300)
        .all()
    )

    if not rows:
        return []

    results: List[Dict[str, Any]] = []

    for memory in rows:
        mem_text = memory.memory_text or ""
        mem_tokens = _memory_tokens(mem_text)

        overlap = query_tokens.intersection(mem_tokens) if query_tokens else set()
        topic_match = memory_matches_topic(mem_text, target_topic) if target_topic else False
        comm_match = query_is_comm and (
            memory.memory_type in ("communication_style", "preference")
            or contains_keyword(mem_text, COMMUNICATION_KEYWORDS)
        )
        pref_match = query_is_pref and memory.memory_type in ("preference", "communication_style")
        interest_match = asks_about_interests and memory.memory_type == "interest"

        # If no tokens overlap and no topic/intent category aligns, skip
        if not overlap and not (topic_match or comm_match or pref_match or interest_match):
            continue

        precision = len(overlap) / max(1, len(mem_tokens)) if mem_tokens else 0.0
        coverage = len(overlap) / max(1, len(query_tokens)) if query_tokens else 0.0

        similarity = (
            0.45 * precision
            + 0.15 * coverage
            + (0.30 if topic_match else 0.0)
            + (0.20 if (comm_match or pref_match) else (0.10 if interest_match else 0.0))
        )
        similarity = min(1.0, round(similarity, 4))

        if similarity < min_similarity:
            continue

        results.append({
            "id": memory.id,
            "memory_text": memory.memory_text,
            "memory_type": memory.memory_type,
            "confidence": memory.confidence,
            "similarity": similarity,
            "created_at": memory.created_at,
        })

    results.sort(
        key=lambda item: (
            item["similarity"],
            float(item.get("confidence") or 0.0),
            item["created_at"],
        ),
        reverse=True,
    )

    return results[:limit]


# ---------------------------------------------------------
# MEMORY RERANKING
# ---------------------------------------------------------

def rerank_memories(
    memories: List[Dict[str, Any]],
    query: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Rerank candidate memories without loading heavyweight ML models.

    Preserves existing intent_match gating and final_score sorting behavior:
    final_score = (int(intent_match), rerank_score, similarity).
    """
    if not memories or not isinstance(query, str) or not query.strip():
        return []

    if top_k < 1:
        return []

    query = query.strip()
    target_topic = detect_topic(query)
    asks_about_interests = contains_keyword(query, INTEREST_WORDS)
    query_is_comm = contains_keyword(query, COMMUNICATION_KEYWORDS)
    query_is_pref = contains_keyword(query, PREFERENCE_KEYWORDS)
    query_tokens = _memory_tokens(query)

    # Deduplicate candidate memories by normalized text
    unique_memories: List[Dict[str, Any]] = []
    seen_texts: Set[str] = set()

    for memory in memories:
        if not isinstance(memory, dict):
            continue

        memory_text = memory.get("memory_text")
        if not isinstance(memory_text, str) or not memory_text.strip():
            continue

        normalized = memory_text.strip().casefold()
        if normalized in seen_texts:
            continue

        seen_texts.add(normalized)
        unique_memories.append(memory)

    if not unique_memories:
        return []

    # For a specific topic query that also asks about interests, discard candidates
    # that do not mention that topic
    if target_topic is not None and asks_about_interests:
        filtered = [
            m for m in unique_memories
            if memory_matches_topic(m.get("memory_text", ""), target_topic)
        ]
        if filtered:
            unique_memories = filtered

    reranked: List[Dict[str, Any]] = []

    for memory in unique_memories:
        item = memory.copy()
        mem_text = item.get("memory_text", "")
        mem_type = str(item.get("memory_type", "")).lower()
        mem_tokens = _memory_tokens(mem_text)

        overlap = query_tokens.intersection(mem_tokens) if query_tokens else set()
        topic_match = memory_matches_topic(mem_text, target_topic) if target_topic else False

        # Intent matching aligned with query categories
        if target_topic is not None:
            intent_match = topic_match
        elif query_is_comm:
            intent_match = (
                mem_type in ("communication_style", "preference")
                or contains_keyword(mem_text, COMMUNICATION_KEYWORDS)
            )
        elif query_is_pref:
            intent_match = mem_type in ("preference", "communication_style")
        elif asks_about_interests:
            intent_match = mem_type == "interest"
        else:
            # For general conversation, an intent match is confirmed if candidate
            # exhibits strong token overlap (>= 2 terms or >= 25% precision)
            precision = len(overlap) / max(1, len(mem_tokens)) if mem_tokens else 0.0
            intent_match = bool(len(overlap) >= 2 or precision >= 0.25)

        base_similarity = float(item.get("similarity", 0.0))
        precision = len(overlap) / max(1, len(mem_tokens)) if mem_tokens else 0.0
        confidence = float(item.get("confidence") or 0.8)

        rerank_score = min(
            1.0,
            round(
                0.5 * base_similarity
                + 0.3 * precision
                + (0.1 if topic_match else 0.0)
                + 0.1 * confidence,
                4,
            ),
        )

        item["rerank_score"] = rerank_score
        item["intent_match"] = int(intent_match)
        item["final_score"] = (
            int(intent_match),
            rerank_score,
            base_similarity,
        )

        reranked.append(item)

    reranked.sort(
        key=lambda item: item["final_score"],
        reverse=True,
    )

    return reranked[:top_k]

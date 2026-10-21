
from functools import lru_cache
import re

from sentence_transformers import CrossEncoder, SentenceTransformer
from sqlalchemy.orm import Session

from app.models import UserMemory


EMBEDDING_MODEL_NAME = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Similarity values are model-dependent. Tune this threshold using
# your own retrieval tests rather than treating it as universal.
DEFAULT_MIN_SIMILARITY = 0.30


# ---------------------------------------------------------
# MODELS
# ---------------------------------------------------------

@lru_cache(maxsize=1)
def get_embedding_model():
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


@lru_cache(maxsize=1)
def get_reranker_model():
    return CrossEncoder(RERANKER_MODEL_NAME)


# ---------------------------------------------------------
# EMBEDDINGS
# ---------------------------------------------------------

def generate_embedding(text: str) -> list[float]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text cannot be empty.")

    embedding = get_embedding_model().encode(
        text.strip(),
        normalize_embeddings=True,
    )

    return embedding.tolist()


# ---------------------------------------------------------
# MEMORY STORAGE
# ---------------------------------------------------------

def save_memory(
    db: Session,
    user_id: int,
    memory_text: str,
    memory_type: str = "general",
    confidence: float = 0.8,
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
        return existing_memory

    embedding = generate_embedding(normalized_text)

    memory = UserMemory(
        user_id=user_id,
        memory_text=normalized_text,
        memory_type=memory_type.strip().lower(),
        confidence=confidence,
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


# ---------------------------------------------------------
# TOPIC DETECTION
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

# Words indicating that the user is asking about personal interests.
INTEREST_WORDS = [
    "interest", "interests", "hobby", "hobbies",
    "like", "likes", "enjoy", "enjoys",
    "favorite", "favourite", "prefer", "preferences",
]


def contains_keyword(text: str, keywords: list[str]) -> bool:
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


def detect_topic(query: str) -> str | None:
    """Identify a specific topic mentioned in the query."""

    for topic, keywords in TOPIC_KEYWORDS.items():
        if contains_keyword(query, keywords):
            return topic

    return None


def memory_matches_topic(memory_text: str, topic: str) -> bool:
    """Check whether the actual memory text mentions the topic."""

    keywords = TOPIC_KEYWORDS.get(topic, [])
    return contains_keyword(memory_text, keywords)


# ---------------------------------------------------------
# SEMANTIC MEMORY SEARCH
# ---------------------------------------------------------

def search_memories(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 10,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> list[dict]:
    """
    Retrieve semantically similar memories for one user.

    The threshold removes weak matches. Topic-specific filtering
    is performed later by rerank_memories().
    """

    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    if not -1.0 <= min_similarity <= 1.0:
        raise ValueError("min_similarity must be between -1 and 1.")

    query_embedding = generate_embedding(query.strip())

    distance = UserMemory.embedding.cosine_distance(query_embedding)

    matches = (
        db.query(
            UserMemory,
            distance.label("distance"),
        )
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(limit)
        .all()
    )

    results = []

    for memory, distance_value in matches:
        if distance_value is None:
            continue

        similarity = 1.0 - float(distance_value)

        if similarity < min_similarity:
            continue

        results.append(
            {
                "id": memory.id,
                "memory_text": memory.memory_text,
                "memory_type": memory.memory_type,
                "confidence": memory.confidence,
                "similarity": round(similarity, 4),
                "created_at": memory.created_at,
            }
        )

    return results


# ---------------------------------------------------------
# MEMORY RERANKING
# ---------------------------------------------------------

def rerank_memories(
    memories: list[dict],
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Rerank candidate memories.

    When a query identifies a specific topic, only memories whose
    text matches that topic can receive intent_match=1.

    For general queries, semantic relevance is used without
    automatically claiming a specific topic match.
    """

    if not memories or not isinstance(query, str) or not query.strip():
        return []

    if top_k < 1:
        return []

    query = query.strip()
    target_topic = detect_topic(query)
    asks_about_interests = contains_keyword(query, INTEREST_WORDS)

    # Deduplicate candidate memories.
    unique_memories = []
    seen_texts = set()

    for memory in memories:
        if not isinstance(memory, dict):
            continue

        text = memory.get("memory_text")

        if not isinstance(text, str) or not text.strip():
            continue

        normalized_text = text.strip().casefold()

        if normalized_text in seen_texts:
            continue

        seen_texts.add(normalized_text)
        unique_memories.append(memory)

    if not unique_memories:
        return []

    # For a specific topic query, discard candidates that do not
    # mention that topic before running the more expensive reranker.
    if target_topic is not None and asks_about_interests:
        unique_memories = [
            memory
            for memory in unique_memories
            if memory_matches_topic(
                memory["memory_text"],
                target_topic,
            )
        ]

    if not unique_memories:
        return []

    model = get_reranker_model()

    pairs = [
        [query, memory["memory_text"].strip()]
        for memory in unique_memories
    ]

    scores = model.predict(pairs)

    reranked = []

    for memory, score in zip(unique_memories, scores):
        item = memory.copy()
        item["rerank_score"] = float(score)

        if target_topic is not None:
            topic_match = memory_matches_topic(
                item["memory_text"],
                target_topic,
            )
            intent_match = topic_match
        elif asks_about_interests:
            intent_match = (
                item.get("memory_type") == "interest"
            )
        else:
            # No specific topic was detected. Keep the candidate
            # available, but do not falsely mark its intent as matched.
            intent_match = False

        item["intent_match"] = int(intent_match)

        item["final_score"] = (
            int(intent_match),
            float(score),
            float(item.get("similarity", 0.0)),
        )

        reranked.append(item)

    reranked.sort(
        key=lambda item: item["final_score"],
        reverse=True,
    )

    return reranked[:top_k]

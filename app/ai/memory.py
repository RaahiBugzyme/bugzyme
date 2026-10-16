from functools import lru_cache
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from app.models import UserMemory
from app.models import UserMemory
from functools import lru_cache
from sentence_transformers import CrossEncoder

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def get_embedding_model():
    model = SentenceTransformer(MODEL_NAME)
    return model


def generate_embedding(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Text cannot be empty.")

    model = get_embedding_model()

    embedding = model.encode(
        text.strip(),
        normalize_embeddings=True
    )

    return embedding.tolist()



def save_memory(
    db: Session,
    user_id: int,
    memory_text: str,
    memory_type: str = "general",
    confidence: float = 0.8,
) -> UserMemory:
    """Save a memory, avoiding exact duplicates for the same user."""

    if not memory_text or not memory_text.strip():
        raise ValueError("Memory text cannot be empty.")

    normalized_text = memory_text.strip()

    # 1. Check whether this exact memory already exists
    existing_memory = (
        db.query(UserMemory)
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.memory_text.ilike(normalized_text),
        )
        .first()
    )

    # 2. Return the existing record instead of inserting a duplicate
    if existing_memory:
        return existing_memory

    # 3. Generate embedding only for a new memory
    embedding = generate_embedding(normalized_text)

    memory = UserMemory(
        user_id=user_id,
        memory_text=normalized_text,
        memory_type=memory_type,
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



def search_memories(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 5,
) -> list[dict]:

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    query_embedding = generate_embedding(query)

    distance = UserMemory.embedding.cosine_distance(query_embedding)

    matches = (
        db.query(UserMemory, distance.label("distance"))
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
        .all()
    )

    results = []

    for memory, distance_value in matches:
        results.append({
            "id": memory.id,
            "memory_text": memory.memory_text,
            "memory_type": memory.memory_type,
            "confidence": memory.confidence,
            "similarity": round(
                1.0 - float(distance_value), 4
            ),
            "created_at": memory.created_at,
        })

    return results




RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def get_reranker_model():
    """Load the cross-encoder model once and reuse it."""
    return CrossEncoder(RERANKER_MODEL_NAME)


def rerank_memories(
    memories: list[dict],
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Rerank memories using query intent and CrossEncoder relevance."""

    if not memories or not query or not query.strip() or top_k < 1:
        return []

    # 1. Remove duplicate memories.
    unique_memories = []
    seen_texts = set()

    for memory in memories:
        text = memory.get("memory_text", "").strip()

        if not text:
            continue

        normalized_text = text.casefold()

        if normalized_text in seen_texts:
            continue

        seen_texts.add(normalized_text)
        unique_memories.append(memory)

    if not unique_memories:
        return []

    # 2. Detect query intent.
    query_lower = query.casefold()

    intent_keywords = {
        "interest": [
            "sport", "football", "cricket", "basketball",
            "tennis", "hobby", "hobbies", "interest",
        ],
        "preference": [
            "communicate", "communication", "conversation",
            "conversations", "speaking", "talking",
            "simple english", "explain", "explanation",
            "how should the ai", "what style",
        ],
        "goal": [
            "career", "job", "aspiration", "profession",
            "goal", "become an engineer",
        ],
        "project": [
            "project", "building", "application",
            "app", "system", "what is sandeep building",
        ],
    }

    target_type = None

    # Check more specific phrase matches first.
    for memory_type, keywords in intent_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            target_type = memory_type
            break

    # 3. Get CrossEncoder relevance scores.
    model = get_reranker_model()

    pairs = [
        [query.strip(), memory["memory_text"]]
        for memory in unique_memories
    ]

    scores = model.predict(pairs)

    # 4. Combine semantic relevance with intent matching.
    reranked = []

    for memory, score in zip(unique_memories, scores):
        item = memory.copy()
        item["rerank_score"] = float(score)

        intent_match = (
            target_type is not None
            and item.get("memory_type") == target_type
        )

        item["intent_match"] = int(intent_match)

        # Intent is the primary signal for recognized query types.
        # CrossEncoder score breaks ties within the same group.
        item["final_score"] = (
            1 if intent_match else 0,
            float(score),
        )

        reranked.append(item)

    reranked.sort(
        key=lambda item: item["final_score"],
        reverse=True,
    )

    return reranked[:top_k]


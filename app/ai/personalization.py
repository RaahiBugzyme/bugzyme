
from sqlalchemy.orm import Session

from app.ai.memory import search_memories, rerank_memories
from app.ai.extraction import get_groq_client, MODEL_NAME


def build_personalized_context(
    db: Session,
    user_id: int,
    message: str,
    limit: int = 5,
) -> str:
    """Retrieve and select memories relevant to the user's message."""

    candidates = search_memories(
        db=db,
        user_id=user_id,
        query=message,
        limit=max(limit * 2, 10),
    )

    memories = rerank_memories(
        memories=candidates,
        query=message,
        top_k=limit,
    )

    if not memories:
        return "No relevant user memories found."

    relevant_memories = [
        memory
        for memory in memories
        if memory.get("intent_match") == 1
    ]

    if not relevant_memories:
        relevant_memories = memories[:3]

    lines = ["Relevant information about this user:"]

    for memory in relevant_memories:
        lines.append(f"- {memory['memory_text']}")

    return "\n".join(lines)


def generate_personalized_reply(
    context: str,
    message: str,
) -> str:
    """Generate a natural reply using relevant user memories."""

    if not message or not message.strip():
        raise ValueError("Message cannot be empty.")

    client = get_groq_client()

    system_prompt = f"""
You are a friendly AI assistant in a chat application.

Your job is to respond naturally and conversationally.

Rules:
- Use the supplied memories only when relevant to the user's message.
- Treat memories as supporting context, not guaranteed truth.
- Never invent personal facts or claim memories that are not provided.
- Do not force personal interests into unrelated replies.
- If the user asks about their preferences or interests, use relevant memories.
- If the answer is not available in the memories, say so honestly.
- Keep replies concise, clear, and natural.
- Respect the user's communication preferences when relevant.

User memories:
{context}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message.strip()},
        ],
        temperature=0.5,
        max_completion_tokens=300,
    )

    reply = response.choices[0].message.content

    return reply.strip() if reply else (
        "Sorry, I couldn't generate a reply right now."
    )


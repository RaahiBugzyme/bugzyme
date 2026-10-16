
import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL_NAME = "openai/gpt-oss-120b"


def get_groq_client():
    """Create and return a Groq API client."""

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise ValueError(
            "GROQ_API_KEY missing. Check your .env file."
        )

    return Groq(api_key=api_key)


def extract_memories(conversation: str) -> list[dict]:
    """Extract useful long-term memories from a conversation."""

    if not conversation or not conversation.strip():
        return []

    client = get_groq_client()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": """
You extract useful long-term information from conversations.

Identify information that can help personalize future conversations.

Extract these categories:

1. preference:
   Explicit preferences, such as preferred language or answer format.

2. goal:
   Long-term or ongoing goals, such as preparing for interviews.

3. interest:
   Topics the user is interested in, such as AI, cricket, or music.

4. personal_fact:
   Relevant personal facts explicitly shared by the user.

5. project:
   Projects the user is building or working on.

6. communication_style:
   Supported communication preferences, such as preferring
   short replies, casual language, or detailed explanations.

7. behaviour:
   Repeated, observable conversation patterns that may help
   personalize future replies. Only include patterns supported
   by the conversation. Do not make psychological diagnoses
   or unsupported personality judgments.

8. general:
   Other useful long-term information that does not fit above.

Rules:
- Extract only information explicitly stated or strongly supported.
- Do not invent facts or infer sensitive personal attributes.
- Ignore temporary small talk and one-time reactions.
- Prefer concise, reusable memory statements.
- Avoid duplicate memories that express the same information.
- Do not confuse a temporary conversation topic with a lasting interest.
- If the conversation has multiple speakers, preserve the speaker's
  identity in memory_text when it is clear from the input.
- If the speaker is unclear, do not guess their identity.
- Confidence must be a number between 0 and 1.
- Return valid JSON only, in this format:

{
  "memories": [
    {
      "memory_text": "The user prefers short, casual replies.",
      "memory_type": "communication_style",
      "confidence": 0.95
    }
  ]
}

If no useful long-term information exists, return:
{"memories": []}
"""
            },
            {
                "role": "user",
                "content": conversation,
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_completion_tokens=1000,
    )

    content = response.choices[0].message.content

    if not content:
        return []

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return []

    memories = data.get("memories", [])

    if not isinstance(memories, list):
        return []

    allowed_types = {
        "preference",
        "goal",
        "interest",
        "personal_fact",
        "project",
        "communication_style",
        "behaviour",
        "general",
    }

    valid_memories = []

    for item in memories:
        if not isinstance(item, dict):
            continue

        memory_text = item.get("memory_text")

        if not isinstance(memory_text, str) or not memory_text.strip():
            continue

        memory_type = item.get("memory_type", "general")

        if not isinstance(memory_type, str):
            memory_type = "general"
        elif memory_type not in allowed_types:
            memory_type = "general"

        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        confidence = max(0.0, min(1.0, confidence))

        valid_memories.append({
            "memory_text": memory_text.strip(),
            "memory_type": memory_type,
            "confidence": confidence,
        })

    return valid_memories

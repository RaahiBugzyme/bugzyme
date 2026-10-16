
import json

from app.ai.extraction import get_groq_client, MODEL_NAME


def extract_interests(conversation: str) -> dict:
    """Extract each user's interests from a chat conversation."""

    if not conversation or not conversation.strip():
        return {
            "user_1_interests": [],
            "user_2_interests": [],
        }

    client = get_groq_client()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": """
You are an interest extraction assistant for a chat application.

Analyze the conversation and extract the interests of each user separately.

Rules:
1. Extract hobbies, sports, music, movies, food, travel,
   fitness, technology, and other genuine interests.
2. Use only information explicitly stated or strongly supported
   by the conversation.
3. Do not assume an interest just because a user asks one question.
4. Do not mix the two users' interests.
5. Avoid duplicate interests.
6. If a user's interests are unclear, return an empty list.
7. Return valid JSON only, using this exact structure:

{
  "user_1_interests": ["interest 1"],
  "user_2_interests": ["interest 2"]
}
"""
            },
            {
                "role": "user",
                "content": conversation,
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_completion_tokens=500,
    )

    content = response.choices[0].message.content

    if not content:
        return {
            "user_1_interests": [],
            "user_2_interests": [],
        }

    data = json.loads(content)

    result = {}

    for key in ("user_1_interests", "user_2_interests"):
        interests = data.get(key, [])

        if not isinstance(interests, list):
            interests = []

        result[key] = [
            item.strip()
            for item in interests
            if isinstance(item, str) and item.strip()
        ]

    return result
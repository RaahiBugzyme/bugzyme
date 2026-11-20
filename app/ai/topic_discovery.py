"""Evidence-based topic overlap, unanswered questions, and topic recency."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.ai.memory import TOPIC_KEYWORDS, contains_keyword

def _get(item: Any, key: str, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

def discover_topics(messages: list[Any]) -> dict:
    per_user: dict[str, set[str]] = defaultdict(set)
    topic_last_index = {}
    lines = []
    for index, item in enumerate(messages or []):
        sender = _get(item, "sender_id", _get(item, "sender"))
        text = _get(item, "content", _get(item, "message", _get(item, "text", "")))
        if not isinstance(text, str) or not text.strip(): continue
        lines.append((str(sender) if sender is not None else "", text.strip()))
        for topic, keywords in TOPIC_KEYWORDS.items():
            if contains_keyword(text, keywords):
                if sender is not None: per_user[str(sender)].add(topic)
                topic_last_index[topic] = index
    participants = list(per_user)
    overlap = sorted(set.intersection(*(per_user[p] for p in participants))) if len(participants) >= 2 else []
    asked = []
    for i, (sender, text) in enumerate(lines[-12:]):
        if "?" not in text: continue
        # Only call it unresolved if no subsequent message from a different speaker clearly follows it.
        later = lines[-12:][i + 1:]
        if not any(other != sender and reply for other, reply in later):
            asked.append(text)
    return {"topics_by_participant": {k: sorted(v) for k, v in per_user.items()},
            "supported_shared_topics": overlap,
            "recent_topics": [topic for topic, _ in sorted(topic_last_index.items(), key=lambda kv: kv[1], reverse=True)[:5]],
            "unanswered_latest_questions": asked[-3:]}

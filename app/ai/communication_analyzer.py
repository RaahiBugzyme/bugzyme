"""Observable, per-speaker communication patterns (not personality diagnoses)."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def _get(item: Any, key: str, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def analyze_communication(messages: list[Any], usernames: dict[str, str] | None = None) -> dict[str, dict]:
    """Summarize each speaker independently; suppress labels below 6 samples."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in messages or []:
        sender = _get(item, "sender_id", _get(item, "sender_name", _get(item, "speaker")))
        content = _get(item, "content", _get(item, "message", _get(item, "text", "")))
        if sender is not None and isinstance(content, str) and content.strip():
            grouped[str(sender)].append(content.strip())
    result = {}
    for sender, texts in grouped.items():
        sample = texts[-30:]
        lengths = [len(re.findall(r"\S+", text)) for text in sample]
        avg = sum(lengths) / len(lengths)
        emoji = sum(bool(re.search(r"[^\w\s,.'!?-]", text, re.UNICODE)) for text in sample) / len(sample)
        questions = sum("?" in text for text in sample) / len(sample)
        playful_markers = sum(bool(re.search(r"\b(lol|haha|hehe|lmao|😂|😄|😅)\b", text, re.I)) for text in sample) / len(sample)
        if len(sample) < 6:
            style = "insufficient_data"
        elif avg <= 7:
            style = "usually_concise"
        elif avg >= 22:
            style = "usually_detailed"
        elif playful_markers >= .20:
            style = "often_playful"
        elif emoji >= .30:
            style = "often_expressive"
        else:
            style = "conversational_mix"
        result[sender] = {
            "sample_messages": len(sample), "average_words": round(avg, 1),
            "question_rate": round(questions, 2), "emoji_message_rate": round(emoji, 2),
            "playful_marker_rate": round(playful_markers, 2), "observable_style": style,
            "confidence": "low" if len(sample) < 6 else ("medium" if len(sample) < 15 else "high"),
        }
    return result

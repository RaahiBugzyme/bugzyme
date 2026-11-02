"""Conservative probabilistic tone cues in English and common Roman Hindi."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

POSITIVE = {"excited": ("excited", "amazing", "can't wait", "so happy", "omg", "yay", "mazedaar", "bohot acha", "bahut acha", "mast"),
            "playful": ("haha", "hehe", "lol", "lmao", "😂", "😄", "😜", "kidding", "mazaak"),
            "curious": ("?", "wonder", "curious", "tell me", "kaise", "kyun", "kya", "batao"),
            "comfortable": ("thanks for sharing", "with you", "comfortable", "sukoon", "acha laga")}
NEGATIVE = {"frustrated": ("annoyed", "frustrated", "upset", "angry", "irritated", "pareshan", "gussa", "tang aa"),
            "awkward": ("awkward", "weird", "idk what to say", "uncomfortable", "ajeeb"),
            "bored": ("boring", "bored", "whatever", "same old", "meh", "kuch nahi")}

def _get(item: Any, key: str, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

def _tone(texts: list[str]) -> dict:
    if len(texts) < 3:
        return {"state": "uncertain", "confidence": 0.0, "evidence_messages": len(texts)}
    recent = texts[-6:]
    joined = " ".join(recent).casefold()
    counts = {name: sum(joined.count(token) for token in tokens) for name, tokens in {**POSITIVE, **NEGATIVE}.items()}
    ranked = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    name, count = ranked[0]
    if count == 0:
        return {"state": "neutral", "confidence": 0.35, "evidence_messages": len(recent)}
    return {"state": name, "confidence": round(min(.85, .35 + .12 * count), 2), "evidence_messages": len(recent)}

def analyze_mood(messages: list[Any]) -> dict:
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in messages or []:
        sender = _get(item, "sender_id", _get(item, "sender"))
        text = _get(item, "content", _get(item, "message", _get(item, "text", "")))
        if sender is not None and isinstance(text, str) and text.strip(): grouped[str(sender)].append(text.strip())
    individual = {sender: _tone(texts) for sender, texts in grouped.items()}
    shared = _tone([_get(i, "content", _get(i, "message", _get(i, "text", ""))) for i in (messages or []) if isinstance(_get(i, "content", _get(i, "message", _get(i, "text", ""))), str)])
    return {"participants": individual, "shared": shared, "note": "Tone cues are uncertain language heuristics, not judgments about feelings."}

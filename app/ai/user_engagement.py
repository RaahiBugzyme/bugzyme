"""Transparent, recent participant engagement signals; pauses are not penalties."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.ai.communication_analyzer import analyze_communication


def _get(item: Any, key: str, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def analyze_engagement(messages: list[Any], window: int = 24) -> dict:
    usable = []
    for item in messages or []:
        sender = _get(item, "sender_id", _get(item, "sender"))
        text = _get(item, "content", _get(item, "message", _get(item, "text", "")))
        if sender is not None and isinstance(text, str) and text.strip():
            usable.append((str(sender), text.strip()))
    recent = usable[-window:]
    styles = analyze_communication(messages)
    groups: dict[str, list[str]] = defaultdict(list)
    for sender, text in recent:
        groups[sender].append(text)
    scores = {}
    features = {}
    for sender, texts in groups.items():
        word_counts = [len(re.findall(r"\S+", text)) for text in texts]
        typical = styles.get(sender, {}).get("average_words") or 8
        # Length is normalized to this user's observed style, so concise users aren't penalized.
        effort = sum(min(n / max(typical, 5), 1.5) for n in word_counts) / len(texts) / 1.5
        substance = sum(n >= 5 or len(t) >= 28 for n, t in zip(word_counts, texts)) / len(texts)
        questions = sum("?" in t for t in texts) / len(texts)
        distinct = len(set(re.findall(r"[\w'-]{4,}", " ".join(texts).casefold())))
        variety = min(distinct / max(sum(word_counts), 1) * 2.5, 1)
        # A 0.5 neutral reciprocity baseline avoids interpreting unequal turn counts as disinterest.
        share = len(texts) / max(len(recent), 1)
        score = 100 * (.35 * effort + .30 * substance + .20 * questions + .15 * variety)
        scores[sender] = round(max(0, min(100, score)), 1)
        features[sender] = {"message_count": len(texts), "effort": round(effort, 2), "substantive_rate": round(substance, 2), "question_rate": round(questions, 2), "topic_contribution_proxy": round(variety, 2), "recent_turn_share": round(share, 2)}
    enough = len(recent) >= 8 and len(groups) == 2 and all(len(v) >= 2 for v in groups.values())
    health = round(sum(scores.values()) / len(scores), 1) if enough and scores else None
    return {"scores": scores, "features": features, "shared_health_score": health,
            "confidence": "medium" if enough and len(recent) >= 16 else ("low" if enough else "insufficient"),
            "method_note": "Heuristic observable signals; timestamps and delayed replies are not scored."}

"""Deterministic, conservative selection of conversation recovery approaches."""
from collections import Counter
from datetime import datetime, timedelta
import re

PROMPT_VERSION = "bugzyme-recovery-v1"

def _get(item, key, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

def select_recovery_strategy(messages: list, intelligence: dict | None = None,
                             previous_strategies: list[str] | None = None,
                             now: datetime | None = None) -> dict:
    usable = [m for m in (messages or []) if isinstance(_get(m, "content", _get(m, "message", "")), str) and _get(m, "content", _get(m, "message", "")).strip()]
    if len(usable) < 8:
        return {"should_intervene": False, "strategy": "give_space", "reason": "insufficient_context", "confidence": "low"}
    timestamps = [_get(m, "created_at") for m in usable]
    latest = timestamps[-1]
    if isinstance(latest, datetime):
        current = now or datetime.now(latest.tzinfo) if latest.tzinfo else (now or datetime.utcnow())
        try:
            if current - latest > timedelta(hours=24):
                return {"should_intervene": False, "strategy": "give_space", "reason": "natural_pause", "confidence": "medium"}
        except TypeError:
            pass
    content = [_get(m, "content", _get(m, "message", "")).strip() for m in usable]
    recent = content[-8:]
    senders = [str(_get(m, "sender_id", _get(m, "sender", ""))) for m in usable[-12:]]
    counts = Counter(senders)
    reason, strategy = "conversation_stagnation", "natural_continuation"
    last_topics = []
    from app.ai.memory import TOPIC_KEYWORDS, contains_keyword
    for text in recent:
        last_topics.extend(topic for topic, kws in TOPIC_KEYWORDS.items() if contains_keyword(text, kws))
    if len(last_topics) >= 4 and len(set(last_topics[-4:])) == 1:
        reason, strategy = "repetitive_topic", "shared_interest_discovery"
    elif len(recent) >= 4 and sum("?" in text for text in recent[-8:]) >= 3:
        reason, strategy = "question_heavy_flow", "personal_experience_sharing"
    elif sum(len(text.split()) <= 2 for text in recent[-4:]) >= 3:
        reason, strategy = "repeated_short_responses", "low_pressure_natural_continuation"
    elif len(counts) == 2 and max(counts.values()) >= 2 * min(counts.values()):
        reason, strategy = "one_sided_communication", "low_pressure_natural_continuation"
    elif not last_topics:
        reason, strategy = "few_new_topics", "open_ended_discussion"
    shared = (intelligence or {}).get("shared", {})
    shared_mood = shared.get("mood", {})
    if shared_mood.get("state") in {"frustrated", "awkward"} and shared_mood.get("confidence", 0) >= .6:
        reason, strategy = "tense_or_awkward_tone", "thoughtful_follow_up"
    elif shared_mood.get("state") == "bored" and shared_mood.get("confidence", 0) >= .6:
        reason, strategy = "low_energy_tone", "topic_revival"
    shared_topics = shared.get("topics", {}).get("supported_shared_topics", [])
    if reason == "few_new_topics" and shared_topics:
        reason, strategy = "new_direction_available", "shared_interest_discovery"
    history = previous_strategies or []
    failed = [s for s in history[-3:] if s]
    if failed and strategy in failed:
        alternatives = ["topic_revival", "thoughtful_follow_up", "shared_interest_discovery", "open_ended_discussion"]
        strategy = next((option for option in alternatives if option != strategy and option not in failed),
                        next(option for option in alternatives if option != strategy))
        reason += "_previous_strategy_unsuccessful"
    return {"should_intervene": True, "strategy": strategy, "reason": reason,
            "confidence": "medium" if len(usable) >= 12 else "low",
            "recent_repeated_responses": sum(len(t.split()) <= 2 for t in recent[-4:])}

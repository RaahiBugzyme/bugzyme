"""Participant-level effort analysis for conversation suggestion targeting.

These scores describe observable message effort only. They are not a judgment
about interest, intent, or personality.
"""

from collections import Counter, defaultdict
from typing import Any
import re

from app.ai.user_engagement import analyze_engagement

MIN_MESSAGES = 8
MIN_MESSAGES_PER_USER = 2
MIN_SCORE = 35.0
MIN_GAP = 18.0

_WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)


def _value(message: Any, key: str, default=None):
    return message.get(key, default) if isinstance(message, dict) else getattr(message, key, default)


def analyze_participant_effort(messages: list[Any]) -> dict:
    """Return a single clear assistance target from style-normalized signals."""
    normalized = []
    for item in messages if isinstance(messages, list) else []:
        if _value(item, "is_deleted", False):
            continue
        sender = _value(item, "sender_id", _value(item, "sender"))
        content = _value(item, "content", _value(item, "text", ""))
        if sender is None or not isinstance(content, str) or not content.strip():
            continue
        normalized.append((str(sender), content.strip()))

    by_user: dict[str, list[str]] = defaultdict(list)
    for sender, content in normalized[-12:]:
        by_user[sender].append(content)

    result = {
        "target_user_id": None,
        "eligible": False,
        "scores": {},
        "reason": "insufficient_evidence",
        "message_count": len(normalized),
    }
    if len(normalized) < MIN_MESSAGES or len(by_user) != 2:
        return result
    if any(len(items) < MIN_MESSAGES_PER_USER for items in by_user.values()):
        return result

    engagement = analyze_engagement(messages)
    for user_id in by_user:
        result["scores"][user_id] = engagement["scores"].get(user_id, 0.0)

    ranked = sorted(result["scores"].items(), key=lambda pair: pair[1], reverse=True)
    (candidate, high), (_, low) = ranked
    gap = high - low
    if high >= MIN_SCORE and gap >= MIN_GAP:
        try:
            target_id = int(candidate)
        except (TypeError, ValueError):
            target_id = candidate
        result.update(target_user_id=target_id, eligible=True, reason="clear_effort_gap", effort_gap=round(gap, 1))
    else:
        result.update(reason="balanced_or_unclear", effort_gap=round(gap, 1))
    return result

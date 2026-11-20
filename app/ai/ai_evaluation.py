"""Small, explicit lifecycle event and conservative outcome helpers."""
from __future__ import annotations

VALID_EVENTS = {"generated", "viewed", "selected", "edited", "sent", "meaningful_response", "continued", "engagement_improved", "user_feedback"}
CLIENT_EVENTS = {"viewed", "selected", "edited", "sent", "user_feedback"}

def meaningful_response(content: str | None) -> bool:
    if not content or not content.strip(): return False
    text = content.strip()
    return len(text.split()) >= 4 or "?" in text or len(text) >= 24

def event_quality(event_type: str, feedback: str | None = None) -> dict:
    """Return observations only; absence of selection/reply is not a failure."""
    return {"event_type": event_type, "explicit_feedback": feedback,
            "interpretable_as_negative": event_type == "user_feedback" and feedback == "not_helpful"}

"""Evidence-based, shared conversation insights without private participant scores."""
from collections import Counter
import re

from app.ai.mood_detector import analyze_mood
from app.ai.topic_discovery import discover_topics


def _get(item, key, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def build_conversation_insights(messages: list) -> dict:
    usable = [item for item in (messages or [])
              if isinstance(_get(item, "content", ""), str)
              and _get(item, "content", "").strip()]
    if not usable:
        return {"available": False, "reason": "no_context", "engagement_trend": None,
                "mood": None, "shared_topics": [], "patterns": []}

    texts = [_get(item, "content", "").strip() for item in usable]
    senders = [str(_get(item, "sender_id", "unknown")) for item in usable]
    counts = Counter(senders)
    patterns = []
    if len(counts) >= 2:
        balance = min(counts.values()) / max(counts.values())
        if balance >= .75:
            patterns.append("Message counts are fairly balanced across the two participants.")
        else:
            patterns.append("The message count is uneven across participants in this sample.")
    else:
        patterns.append("Only one participant has messages in the available sample.")

    topics = discover_topics(usable)
    shared_topics = topics.get("supported_shared_topics", [])
    unanswered = topics.get("unanswered_latest_questions", [])
    if unanswered:
        patterns.append(f"There {'is' if len(unanswered) == 1 else 'are'} {len(unanswered)} recent question{'s' if len(unanswered) != 1 else ''} without a later reply in this sample.")
    if shared_topics:
        patterns.append("Both participants have mentioned: " + ", ".join(shared_topics[:5]) + ".")

    trend = None
    if len(usable) >= 8 and len(counts) >= 2:
        midpoint = len(usable) // 2
        prior = texts[:midpoint]
        recent = texts[midpoint:]
        prior_average = sum(len(re.findall(r"\S+", text)) for text in prior) / len(prior)
        recent_average = sum(len(re.findall(r"\S+", text)) for text in recent) / len(recent)
        relative_change = (recent_average - prior_average) / max(prior_average, 1)
        if relative_change >= .2:
            state = "rising"
            explanation = f"Average message length rose from {prior_average:.1f} to {recent_average:.1f} words in the latest half of this sample."
        elif relative_change <= -.2:
            state = "declining"
            explanation = f"Average message length fell from {prior_average:.1f} to {recent_average:.1f} words in the latest half of this sample."
        else:
            state = "steady"
            explanation = f"Average message length stayed similar across both halves of this sample ({prior_average:.1f} vs {recent_average:.1f} words)."
        trend = {"state": state, "explanation": explanation,
                 "prior_average_words": round(prior_average, 1),
                 "recent_average_words": round(recent_average, 1)}

    mood_result = analyze_mood(usable).get("shared", {})
    mood = {"state": mood_result.get("state", "uncertain"),
            "confidence": mood_result.get("confidence", 0),
            "evidence_messages": mood_result.get("evidence_messages", len(usable))}
    return {"available": True, "message_count": len(usable),
            "engagement_trend": trend, "mood": mood,
            "shared_topics": shared_topics[:5], "patterns": patterns[:4],
            "caveat": "These are conversation-level signals from the recent message sample, not judgments about either person."}

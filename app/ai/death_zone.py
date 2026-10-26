
from collections import Counter
from typing import Any, Dict, List, Optional


DEFAULT_RECENT_WINDOW = 12
MIN_MESSAGES = 8
MIN_BASELINE_MESSAGES = 6
MIN_PARTICIPANTS = 2


def _get(
    message: Any,
    *keys: str,
    default: Any = None,
) -> Any:
    """Read a field from a dictionary or an object."""
    for key in keys:
        if isinstance(message, dict):
            value = message.get(key)
        else:
            value = getattr(message, key, None)

        if value is not None:
            return value

    return default


def _normalize_messages(messages: List[Any]) -> List[Dict[str, str]]:
    """
    Normalize incoming messages.

    Supported content fields:
        content, message, text

    Supported sender fields:
        sender_id, sender, speaker, role, name

    Optional:
        is_deleted
    """
    normalized: List[Dict[str, str]] = []

    for message in messages:
        if _get(message, "is_deleted", default=False):
            continue

        content = _get(
            message,
            "content",
            "message",
            "text",
            default="",
        )

        if not isinstance(content, str) or not content.strip():
            continue

        sender = _get(
            message,
            "sender_id",
            "sender_name",
            "sender",
            "speaker",
            "role",
            "name",
            default=None,
        )

        # Unknown senders cannot reliably establish reciprocity.
        if sender is None:
            sender = "unknown"

        normalized.append({
            "sender": str(sender),
            "content": content.strip(),
        })

    return normalized


def _window_metrics(
    messages: List[Dict[str, str]],
) -> Dict[str, float]:
    """Calculate interpretable engagement signals for a message window."""
    if not messages:
        return {
            "substantive_rate": 0.0,
            "question_rate": 0.0,
            "participation_balance": 0.0,
            "average_word_count": 0.0,
            "engagement_index": 0.0,
        }

    contents = [item["content"] for item in messages]
    word_counts = [len(text.split()) for text in contents]

    # A rough heuristic for whether a message adds conversational substance.
    substantive_count = sum(
        count >= 5 or len(text) >= 30
        for text, count in zip(contents, word_counts)
    )
    substantive_rate = substantive_count / len(messages)

    question_count = sum("?" in text for text in contents)
    question_rate = question_count / len(messages)

    sender_counts = Counter(item["sender"] for item in messages)

    if len(sender_counts) >= MIN_PARTICIPANTS:
        # 1.0 means equal participation; lower values mean more imbalance.
        participation_balance = (
            1.0
            - (
                max(sender_counts.values())
                - min(sender_counts.values())
            ) / len(messages)
        )
    else:
        participation_balance = 0.0

    average_word_count = sum(word_counts) / len(word_counts)

    # Normalize length to a 0–1 range.
    length_signal = min(average_word_count / 12.0, 1.0)

    # Transparent heuristic index, not a probability.
    engagement_index = 100.0 * (
        0.35 * substantive_rate
        + 0.20 * question_rate
        + 0.20 * participation_balance
        + 0.25 * length_signal
    )

    return {
        "substantive_rate": round(substantive_rate, 3),
        "question_rate": round(question_rate, 3),
        "participation_balance": round(participation_balance, 3),
        "average_word_count": round(average_word_count, 2),
        "engagement_index": round(engagement_index, 1),
    }


def analyze_death_zone(
    messages: List[Any],
    recent_window: int = DEFAULT_RECENT_WINDOW,
) -> Dict[str, Any]:
    """
    Analyze conversation engagement and stagnation.

    Args:
        messages:
            Chronologically ordered messages. Each message should contain
            a sender identifier and textual content.
        recent_window:
            Number of latest usable messages to analyze as the recent window.

    Returns:
        {
            "status": str,
            "death_zone_score": float | None,
            "confidence": str,
            "message_count": int,
            "baseline": dict | None,
            "recent": dict | None,
            "engagement_change": float | None,
            "signals": list[str],
        }

    Possible statuses:
        healthy
        stagnant
        declining
        possible_disengagement
        insufficient_data
    """
    if not isinstance(messages, list):
        raise TypeError("messages must be a list")

    if isinstance(recent_window, bool) or not isinstance(recent_window, int):
        raise TypeError("recent_window must be an integer")

    if recent_window < 2:
        raise ValueError("recent_window must be at least 2")

    normalized = _normalize_messages(messages)

    participant_count = len({
        item["sender"]
        for item in normalized
        if item["sender"] != "unknown"
    })

    if (
        len(normalized) < MIN_MESSAGES
        or participant_count < MIN_PARTICIPANTS
    ):
        return {
            "status": "insufficient_data",
            "death_zone_score": None,
            "confidence": "low",
            "message_count": len(normalized),
            "baseline": None,
            "recent": None,
            "engagement_change": None,
            "signals": [
                "Need at least 8 usable messages from at least 2 identified participants."
            ],
        }

    recent = normalized[-recent_window:]
    baseline_messages = normalized[:-recent_window]

    recent_metrics = _window_metrics(recent)

    baseline_metrics: Optional[Dict[str, float]] = None

    if len(baseline_messages) >= MIN_BASELINE_MESSAGES:
        baseline_metrics = _window_metrics(baseline_messages)

    current_index = recent_metrics["engagement_index"]
    engagement_change: Optional[float] = None
    signals: List[str] = []

    # Recent-window observations.
    if recent_metrics["substantive_rate"] < 0.40:
        signals.append(
            "Many recent messages are brief or contain limited substance."
        )

    if recent_metrics["question_rate"] < 0.15:
        signals.append(
            "Few recent messages contain questions."
        )

    if recent_metrics["participation_balance"] < 0.50:
        signals.append(
            "Recent message participation is uneven."
        )

    # Compare the recent window with earlier conversation history.
    if baseline_metrics is not None:
        engagement_change = round(
            current_index - baseline_metrics["engagement_index"],
            1,
        )

        if engagement_change <= -15:
            signals.append(
                "Recent engagement signals are below the historical baseline."
            )
        elif engagement_change >= 15:
            signals.append(
                "Recent engagement signals have improved compared with baseline."
            )

        substantive_change = (
            recent_metrics["substantive_rate"]
            - baseline_metrics["substantive_rate"]
        )

        if substantive_change <= -0.25:
            signals.append(
                "The proportion of substantive messages has declined."
            )

        question_change = (
            recent_metrics["question_rate"]
            - baseline_metrics["question_rate"]
        )

        if question_change <= -0.20:
            signals.append(
                "Question frequency has declined compared with baseline."
            )

    # Determine the conversation state.
    # A historical comparison is required to label a possible decline.
    if (
        engagement_change is not None
        and engagement_change <= -25
    ):
        status = "possible_disengagement"

    elif (
        engagement_change is not None
        and engagement_change <= -15
    ):
        status = "declining"

    elif current_index < 40:
        status = "stagnant"

    else:
        status = "healthy"

    # Confidence reflects available history, not certainty about feelings.
    if len(normalized) >= 24 and baseline_metrics is not None:
        confidence = "medium"
    else:
        confidence = "low"

    # Higher score means stronger heuristic evidence of stagnation/decline.
    # This score is not the probability that someone has lost interest.
    decline_penalty = max(
        0.0,
        -(engagement_change or 0.0),
    ) * 0.8

    death_zone_score = round(
        min(
            100.0,
            max(
                0.0,
                100.0 - current_index + decline_penalty,
            ),
        ),
        1,
    )

    if not signals:
        signals.append(
            "No strong negative engagement pattern detected by the current heuristics."
        )

    return {
        "status": status,
        "death_zone_score": death_zone_score,
        "confidence": confidence,
        "message_count": len(normalized),
        "baseline": baseline_metrics,
        "recent": recent_metrics,
        "engagement_change": engagement_change,
        "signals": signals,
    }


def is_death_zone(
    result: Dict[str, Any],
    threshold: float = 65.0,
) -> bool:
    """
    Convenience helper for downstream workflow routing.

    Returns False when evidence is insufficient.
    The threshold should be calibrated against labeled conversations.
    """
    if not 0.0 <= threshold <= 100.0:
        raise ValueError("threshold must be between 0 and 100")

    score = result.get("death_zone_score")

    if score is None:
        return False

    return (
        result.get("status") in {
            "stagnant",
            "declining",
            "possible_disengagement",
        }
        and score >= threshold
    )

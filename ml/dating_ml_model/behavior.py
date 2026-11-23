"""Layer 2 (OPTIONAL, separate): supervised behavioral model.

Only exists if the notebook was given a legitimate labeled dataset (Columbia
Speed Dating, target `match`). It is NOT combined with the compatibility score.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


class BehaviorModel:
    def __init__(self, path: Optional[str] = None):
        import joblib

        path = Path(path) if path else Path(__file__).with_name("behavior_model.joblib")
        if not path.exists():
            raise FileNotFoundError("behavior_model.joblib was not trained/exported for this package")
        bundle = joblib.load(path)
        self.pipeline, self.features, self.metadata = bundle["pipeline"], bundle["features"], bundle["metadata"]

    def predict_match_probability(self, features: Dict[str, Any]) -> float:
        import pandas as pd

        row = pd.DataFrame([{f: features.get(f) for f in self.features}]).apply(pd.to_numeric, errors="coerce")
        return float(self.pipeline.predict_proba(row)[0, 1])


# ==========================================================================
# v2.2.0 (append-only): interaction events, behavior summary, recency weighting.
# `BehaviorModel` above is UNCHANGED: it only loads the optional Columbia benchmark
# (a separate, experimental layer). Everything below is the user-behavior system.
# ==========================================================================
import math
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Tuple

CORE_ACTIONS = ("VIEW", "LIKE", "PASS", "MATCH")
EXTRA_ACTIONS = ("SUPER_LIKE", "SAVE", "UNMATCH")          # stored + counted; SUPER_LIKE also learns as a like
FUTURE_ACTIONS = ("MESSAGE", "DATE", "DATE_FEEDBACK")      # accepted + stored, never used for learning yet
INFORMATIONAL_ACTIONS = ("VIEW", "SEARCH")
POSITIVE_INTENT_ACTIONS = ("LIKE", "SUPER_LIKE", "SAVE")
NEGATIVE_INTENT_ACTIONS = ("PASS",)
RELATIONSHIP_STATE_ACTIONS = ("MATCH", "UNMATCH")
NEW_CONVERSATION_ACTIONS = (
    "CONVERSATION_START",
    "CONVERSATION_STARTED",
    "MESSAGE_SENT",
    "MESSAGE_RECEIVED",
    "RECIPROCAL_CHAT",
    "RECIPROCAL_CONVERSATION",
)
CONVERSATION_ACTIONS = ("MESSAGE",) + NEW_CONVERSATION_ACTIONS
SUPPORTED_ACTIONS = CORE_ACTIONS + EXTRA_ACTIONS + FUTURE_ACTIONS + ("SEARCH",) + NEW_CONVERSATION_ACTIONS
POSITIVE_DECISIONS = ("LIKE", "SUPER_LIKE")
NEGATIVE_DECISIONS = ("PASS",)
DECISION_ACTIONS = POSITIVE_DECISIONS + NEGATIVE_DECISIONS

ACTION_SIGNAL_WEIGHTS: Dict[str, float] = {
    "VIEW": 0.1,  # Weak signal (exploration, not proof of attraction)
    "SEARCH": 0.2,
    "SAVE": 0.8,
    "LIKE": 1.0,
    "SUPER_LIKE": 1.2,
    "PASS": -1.0,
    "CONVERSATION_START": 1.2,
    "CONVERSATION_STARTED": 1.2,
    "MESSAGE": 1.0,
    "MESSAGE_SENT": 1.2,
    "MESSAGE_RECEIVED": 0.5,
    "RECIPROCAL_CHAT": 1.5,
    "RECIPROCAL_CONVERSATION": 1.5,
    "MATCH": 1.0,
    "UNMATCH": -1.2,
}

# This contract describes validation and current accounting behavior. It does not
# change how recommendation or personalization logic consumes existing actions.
EVENT_CONTRACT = {
    action: {
        "requires_candidate_id": action != "SEARCH",
        "requires_search_metadata": False,
        "contributes_to_personalization": action in DECISION_ACTIONS,
        "counts_toward_behavioral_summary": True,
        "excludes_candidate": action in DECISION_ACTIONS + ("MATCH", "UNMATCH"),
        "changes_relationship_state": action in RELATIONSHIP_STATE_ACTIONS,
    }
    for action in SUPPORTED_ACTIONS
}


def utcnow() -> datetime:
    """Naive UTC 'now' (avoids the deprecated datetime.utcnow())."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_timestamp(value: Any) -> Optional[datetime]:
    """ISO-8601 string, epoch seconds or datetime -> naive UTC datetime (None if unparseable)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def format_timestamp(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def validate_event(event: Dict[str, Any], default_timestamp: Optional[datetime] = None) -> Dict[str, Any]:
    """Normalize one interaction event or raise ValueError.

    Existing callers may use ``action``. The explicit event contract also accepts
    ``event_type``; both are normalized to the same canonical action. SEARCH is
    the only supported event that does not require a candidate_id.
    """
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    user_id, candidate_id = event.get("user_id"), event.get("candidate_id")
    if user_id in (None, ""):
        raise ValueError("user_id is required")
    raw_action, raw_event_type = event.get("action"), event.get("event_type")
    if raw_action in (None, "") and raw_event_type in (None, ""):
        raise ValueError("action or event_type is required")
    action = str(raw_action if raw_action not in (None, "") else raw_event_type).strip().upper().replace(" ", "_")
    event_type = str(raw_event_type).strip().upper().replace(" ", "_") if raw_event_type not in (None, "") else action
    if raw_action not in (None, "") and raw_event_type not in (None, "") and action != event_type:
        raise ValueError("action and event_type must match")
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported action '{event.get('action')}'; supported: {', '.join(SUPPORTED_ACTIONS)}")
    contract = EVENT_CONTRACT[action]
    if contract["requires_candidate_id"] and candidate_id in (None, ""):
        raise ValueError(f"candidate_id is required for {action}")
    if candidate_id not in (None, "") and str(user_id) == str(candidate_id):
        raise ValueError("user_id and candidate_id must differ")
    ts = parse_timestamp(event.get("timestamp")) if event.get("timestamp") is not None else default_timestamp
    if ts is None:
        raise ValueError("a valid timestamp is required")
    metadata = event.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    search_criteria = event.get("search_criteria")
    if search_criteria is not None and not isinstance(search_criteria, dict):
        raise ValueError("search_criteria must be an object")
    return {"user_id": str(user_id), "candidate_id": None if candidate_id in (None, "") else str(candidate_id),
            "action": action, "event_type": event_type,
            "timestamp": format_timestamp(ts), "session_id": event.get("session_id"),
            "source": event.get("source"), "metadata": metadata or {},
            "search_criteria": search_criteria}


def recency_weight(age_days: float, config: Dict[str, Any]) -> float:
    """Configurable decay. `behavior_decay` (per-day multiplier in (0,1)) wins if set, else half-life."""
    age_days = max(0.0, float(age_days))
    decay = config.get("behavior_decay")
    if decay is not None:
        return float(decay) ** age_days
    return 0.5 ** (age_days / float(config["behavior_half_life_days"]))


def usable_events(events: Iterable[Dict[str, Any]], user_id: Any, now: datetime) -> Tuple[List[Dict[str, Any]], int]:
    """Events of this user known at `now`, oldest first. Future-dated events are dropped (leakage guard)."""
    kept, future = [], 0
    for event in events:
        if str(event.get("user_id")) != str(user_id):
            continue
        ts = parse_timestamp(event.get("timestamp"))
        if ts is None:
            continue
        if ts > now:
            future += 1
            continue
        action = event.get("action", event.get("event_type"))
        kept.append({**event, "action": str(action).strip().upper().replace(" ", "_"), "_ts": ts})
    kept.sort(key=lambda e: (e["_ts"], str(e.get("candidate_id")), str(e.get("action"))))
    return kept, future


def deduplicate_events(events: Iterable[Dict[str, Any]], window_seconds: float = 2.0) -> List[Dict[str, Any]]:
    """Deduplicates interaction events by user, candidate, action, timestamp, and context.

    Also suppresses rapid duplicate clicks on the same candidate within `window_seconds`.
    """
    seen_exact = set()
    last_action_time: Dict[Tuple[str, Optional[str], str], datetime] = {}
    deduped: List[Dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        uid = str(ev.get("user_id"))
        cid = str(ev.get("candidate_id")) if ev.get("candidate_id") not in (None, "") else None
        act = str(ev.get("action", ev.get("event_type", ""))).strip().upper().replace(" ", "_")
        ts_val = ev.get("timestamp")
        ts = parse_timestamp(ts_val)

        exact_key = (uid, cid, act, format_timestamp(ts) if ts else str(ts_val))
        if exact_key in seen_exact:
            continue
        seen_exact.add(exact_key)

        if ts is not None and window_seconds > 0:
            user_cand_act = (uid, cid, act)
            prev_ts = last_action_time.get(user_cand_act)
            if prev_ts is not None and abs((ts - prev_ts).total_seconds()) < window_seconds:
                continue
            last_action_time[user_cand_act] = ts

        deduped.append(dict(ev))
    return deduped


def latest_decisions(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Latest LIKE/SUPER_LIKE/PASS per candidate (repeated or reversed decisions are not independent evidence)."""
    decisions: Dict[str, Dict[str, Any]] = {}
    for event in events:  # events are time-sorted, so later ones overwrite earlier ones
        if event.get("action") in DECISION_ACTIONS:
            decisions[str(event["candidate_id"])] = event
    return decisions


def summarize_behavior(events: Iterable[Dict[str, Any]], user_id: Any, config: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """Counts, rates, recency, evidence, status and confidence. Never invents a score."""
    kept, future = usable_events(events, user_id, now)
    counts = {a: 0 for a in SUPPORTED_ACTIONS}
    for e in kept:
        counts[e["action"]] += 1
    likes = counts["LIKE"] + counts["SUPER_LIKE"]
    passes = counts["PASS"]
    decisions = latest_decisions(kept)
    evidence_count = len(decisions)
    weighted = sum(recency_weight((now - d["_ts"]).total_seconds() / 86400.0, config) for d in decisions.values())
    min_events = int(config["min_behavior_events"])
    if not config.get("behavior_enabled", True):
        status = "disabled"
    elif evidence_count == 0:
        status = "cold_start"
    elif evidence_count < min_events:
        status = "insufficient_data"
    else:
        status = "sufficient_data"
    k = float(config["behavior_evidence_k"])
    confidence = 0.0 if status in ("cold_start", "disabled") else 100.0 * weighted / (weighted + k)
    last = kept[-1]["_ts"] if kept else None
    window = timedelta(days=float(config["recent_window_days"]))
    return {
        "user_id": str(user_id), "behavior_status": status, "behavior_confidence": round(confidence, 4),
        "total_events": len(kept), "total_views": counts["VIEW"], "total_likes": likes, "total_super_likes": counts["SUPER_LIKE"],
        "total_passes": passes, "total_matches": counts["MATCH"], "total_searches": counts["SEARCH"],
        "other_event_counts": {a: counts[a] for a in EXTRA_ACTIONS[1:] + FUTURE_ACTIONS if counts[a]},
        "like_rate": round(likes / (likes + passes), 4) if likes + passes else None,
        "pass_rate": round(passes / (likes + passes), 4) if likes + passes else None,
        "match_rate": round(counts["MATCH"] / likes, 4) if likes else None,
        "recent_events": sum(1 for e in kept if now - e["_ts"] <= window), "recent_window_days": float(config["recent_window_days"]),
        "last_event_at": format_timestamp(last) if last else None,
        "days_since_last_event": round((now - last).total_seconds() / 86400.0, 4) if last else None,
        "evidence_count": evidence_count, "weighted_evidence": round(weighted, 4),
        "min_behavior_events": min_events, "ignored_future_events": future,
    }

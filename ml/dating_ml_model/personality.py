"""Personality and Communication Preferences (Phase 6).

Supports optional, user-provided personality and communication styles:
- Self-reported only (or via optional questionnaire).
- Explicit rule: NEVER infer personality labels from message frequency, response times, or writing style.
- Configurable, explainable signal (not a mandatory filter unless explicitly requested as a hard exclusion).
- Allows users to skip, update, or remove preferences at any time.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

VALID_PERSONALITY_TYPES = {"introvert", "extrovert", "ambivert"}
VALID_COMMUNICATION_FREQUENCIES = {"daily", "few_times_a_week", "weekly", "as_needed"}
VALID_CONVERSATION_STYLES = {"deep_conversations", "casual_banter", "direct_and_concise", "storyteller"}
VALID_SOCIAL_ACTIVITIES = {
    "quiet_nights_in",
    "outdoor_adventures",
    "social_gatherings",
    "cultural_events",
    "fitness_sports",
    "creative_arts",
    "travel_exploration",
    "gaming_tech",
}

# Complementarity / alignment matrix for personality types (0 to 1 scale)
# Research & relationship psychology shows ambiverts pair smoothly with all;
# introverts and extroverts often have rewarding complementarity; shared styles share pacing.
PERSONALITY_TYPE_COMPATIBILITY: Dict[Tuple[str, str], float] = {
    ("introvert", "introvert"): 0.90,  # shared pacing, comfort with quiet
    ("extrovert", "extrovert"): 0.90,  # shared high social energy
    ("ambivert", "ambivert"): 0.95,    # highly versatile
    ("introvert", "ambivert"): 0.90,   # balanced
    ("ambivert", "introvert"): 0.90,
    ("extrovert", "ambivert"): 0.90,   # balanced
    ("ambivert", "extrovert"): 0.90,
    ("introvert", "extrovert"): 0.80,  # complementary dynamic
    ("extrovert", "introvert"): 0.80,
}

COMMUNICATION_FREQUENCY_RANKS: Dict[str, int] = {
    "as_needed": 1,
    "weekly": 2,
    "few_times_a_week": 3,
    "daily": 4,
}


def normalize_personality_profile(payload: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Validates and normalizes self-reported personality preferences.

    Returns (normalized_profile, warnings). Invalid values are omitted with a warning.
    """
    warnings: List[str] = []
    if payload is None or not isinstance(payload, dict):
        return {
            "personality_type": None,
            "communication_frequency": None,
            "conversation_style": None,
            "social_activities": [],
            "hard_exclusions": {},
            "status": "not_set",
        }, warnings

    p_type = payload.get("personality_type")
    if p_type is not None:
        p_type = str(p_type).strip().lower().replace(" ", "_")
        if p_type not in VALID_PERSONALITY_TYPES:
            warnings.append(f"Invalid personality_type '{payload.get('personality_type')}'; dropped.")
            p_type = None

    comm_freq = payload.get("communication_frequency")
    if comm_freq is not None:
        comm_freq = str(comm_freq).strip().lower().replace(" ", "_")
        if comm_freq not in VALID_COMMUNICATION_FREQUENCIES:
            warnings.append(f"Invalid communication_frequency '{payload.get('communication_frequency')}'; dropped.")
            comm_freq = None

    conv_style = payload.get("conversation_style")
    if conv_style is not None:
        conv_style = str(conv_style).strip().lower().replace(" ", "_")
        if conv_style not in VALID_CONVERSATION_STYLES:
            warnings.append(f"Invalid conversation_style '{payload.get('conversation_style')}'; dropped.")
            conv_style = None

    raw_activities = payload.get("social_activities") or []
    social_activities: List[str] = []
    if isinstance(raw_activities, (list, tuple, set)):
        for act in raw_activities:
            act_clean = str(act).strip().lower().replace(" ", "_")
            if act_clean in VALID_SOCIAL_ACTIVITIES:
                if act_clean not in social_activities:
                    social_activities.append(act_clean)
            else:
                warnings.append(f"Unrecognized social activity '{act}' ignored.")

    # Hard exclusions (e.g. user cannot date an extrovert)
    hard_exclusions: Dict[str, List[str]] = {}
    raw_hard = payload.get("hard_exclusions")
    if isinstance(raw_hard, dict):
        for field, values in raw_hard.items():
            if field in ("personality_type", "communication_frequency"):
                vals = [str(v).strip().lower().replace(" ", "_") for v in (values if isinstance(values, (list, tuple)) else [values])]
                hard_exclusions[field] = sorted(v for v in vals if v)

    has_any = (p_type is not None or comm_freq is not None or conv_style is not None or bool(social_activities))
    status = "set" if has_any else "not_set"

    return {
        "personality_type": p_type,
        "communication_frequency": comm_freq,
        "conversation_style": conv_style,
        "social_activities": sorted(social_activities),
        "hard_exclusions": hard_exclusions,
        "status": status,
    }, warnings


def evaluate_personality_compatibility(
    user_personality: Optional[Dict[str, Any]],
    candidate_personality: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluates compatibility between two self-reported personality profiles.

    - Returns score in [0, 100], confidence in [0, 1], and descriptive breakdown.
    - If either profile is missing personality information, returns status 'unavailable' without penalty.
    - If hard exclusions are violated, reports hard_failures.
    """
    u_norm, _ = normalize_personality_profile(user_personality)
    c_norm, _ = normalize_personality_profile(candidate_personality)

    hard_failures: List[str] = []

    # Check hard exclusions
    for field, excluded_vals in u_norm.get("hard_exclusions", {}).items():
        cand_val = c_norm.get(field)
        if cand_val is not None and cand_val in set(excluded_vals):
            hard_failures.append(f"Candidate's {field.replace('_', ' ')} ({cand_val}) is in your hard exclusions")

    for field, excluded_vals in c_norm.get("hard_exclusions", {}).items():
        user_val = u_norm.get(field)
        if user_val is not None and user_val in set(excluded_vals):
            hard_failures.append(f"Your {field.replace('_', ' ')} ({user_val}) is in candidate's hard exclusions")

    if u_norm["status"] == "not_set" or c_norm["status"] == "not_set":
        return {
            "score": None,
            "confidence": 0.0,
            "status": "unavailable",
            "criteria": {},
            "hard_failures": hard_failures,
            "explanations": ["Personality profile not provided by one or both users (no penalty applied)."],
        }

    criteria: Dict[str, Optional[float]] = {}
    explanations: List[str] = []
    components: List[float] = []

    # 1. Personality Type
    u_type, c_type = u_norm["personality_type"], c_norm["personality_type"]
    if u_type and c_type:
        pt_score = PERSONALITY_TYPE_COMPATIBILITY.get((u_type, c_type), 0.75)
        criteria["personality_type"] = pt_score
        components.append(pt_score)
        if u_type == c_type:
            explanations.append(f"Shared personality orientation: both are {u_type}s.")
        else:
            explanations.append(f"Complementary personality styles: {u_type} with {c_type}.")
    else:
        criteria["personality_type"] = None

    # 2. Communication Frequency
    u_freq, c_freq = u_norm["communication_frequency"], c_norm["communication_frequency"]
    if u_freq and c_freq:
        rank_u = COMMUNICATION_FREQUENCY_RANKS.get(u_freq, 2)
        rank_c = COMMUNICATION_FREQUENCY_RANKS.get(c_freq, 2)
        gap = abs(rank_u - rank_c)
        # gap 0 -> 1.0; gap 1 -> 0.8; gap 2 -> 0.5; gap 3 -> 0.2
        freq_score = max(0.0, 1.0 - (gap * 0.25))
        criteria["communication_frequency"] = freq_score
        components.append(freq_score)
        if gap == 0:
            explanations.append(f"Aligned communication rhythm: both prefer {u_freq.replace('_', ' ')} messaging.")
        elif gap == 1:
            explanations.append("Close communication rhythms with compatible pacing.")
        else:
            explanations.append("Different preferred communication frequencies (soft signal; still eligible).")
    else:
        criteria["communication_frequency"] = None

    # 3. Conversation Style
    u_style, c_style = u_norm["conversation_style"], c_norm["conversation_style"]
    if u_style and c_style:
        if u_style == c_style:
            style_score = 1.0
            explanations.append(f"Shared conversation style: both prefer {u_style.replace('_', ' ')}.")
        elif {u_style, c_style} in ({"deep_conversations", "storyteller"}, {"casual_banter", "direct_and_concise"}):
            style_score = 0.85
            explanations.append(f"Harmonious conversation styles: {u_style.replace('_', ' ')} and {c_style.replace('_', ' ')}.")
        else:
            style_score = 0.70
            explanations.append(f"Varied conversation styles: {u_style.replace('_', ' ')} and {c_style.replace('_', ' ')}.")
        criteria["conversation_style"] = style_score
        components.append(style_score)
    else:
        criteria["conversation_style"] = None

    # 4. Social Activities
    u_acts, c_acts = set(u_norm["social_activities"]), set(c_norm["social_activities"])
    if u_acts and c_acts:
        overlap = u_acts & c_acts
        jaccard = len(overlap) / len(u_acts | c_acts)
        criteria["social_activities"] = round(jaccard, 4)
        components.append(jaccard)
        if overlap:
            overlap_labels = ", ".join(a.replace("_", " ") for a in sorted(overlap))
            explanations.append(f"Shared social interests in: {overlap_labels}.")
    else:
        criteria["social_activities"] = None

    if not components:
        return {
            "score": None,
            "confidence": 0.0,
            "status": "unavailable",
            "criteria": criteria,
            "hard_failures": hard_failures,
            "explanations": ["Insufficient overlapping personality attributes."],
        }

    overall_score = round(100.0 * (sum(components) / len(components)), 4)
    confidence = round(100.0 * (len(components) / 4.0), 2)

    return {
        "score": overall_score,
        "confidence": confidence,
        "status": "known",
        "criteria": criteria,
        "hard_failures": hard_failures,
        "explanations": explanations,
    }

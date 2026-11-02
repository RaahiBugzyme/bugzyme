"""Build private participant views and shared, conversation-derived signals."""
from app.ai.communication_analyzer import analyze_communication
from app.ai.death_zone import analyze_death_zone
from app.ai.mood_detector import analyze_mood
from app.ai.topic_discovery import discover_topics
from app.ai.user_engagement import analyze_engagement

def build_conversation_intelligence(messages: list, death_zone: dict | None = None) -> dict:
    """Return scoped participant profiles plus shared evidence; no private memories."""
    communication = analyze_communication(messages)
    engagement = analyze_engagement(messages)
    moods = analyze_mood(messages)
    topics = discover_topics(messages)
    participants = sorted(set(communication) | set(engagement["scores"]))
    private_views = {user_id: {"communication": communication.get(user_id, {}),
                               "engagement_score": engagement["scores"].get(user_id),
                               "mood": moods["participants"].get(user_id, {})}
                     for user_id in participants}
    return {"participant_views": private_views,
            "shared": {"engagement": engagement, "mood": moods["shared"], "topics": topics,
                       "conversation_health": death_zone or analyze_death_zone(messages)},
            "privacy_note": "Participant views are internal and must only guide that participant's suggestions."}

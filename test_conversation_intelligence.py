from datetime import datetime, timedelta

from app.ai.communication_analyzer import analyze_communication
from app.ai.conversation_intelligence import build_conversation_intelligence
from app.ai.mood_detector import analyze_mood
from app.ai.topic_discovery import discover_topics
from app.ai.user_engagement import analyze_engagement


def test_communication_profiles_are_independent_and_withhold_small_samples():
    messages = [{"sender_id": 1, "content": "Yep"}] * 4 + [
        {"sender_id": 2, "content": "I went hiking in the mountains last weekend and took so many photos! 😄"}
    ] * 7
    profiles = analyze_communication(messages)
    assert profiles["1"]["observable_style"] == "insufficient_data"
    assert profiles["2"]["observable_style"] in {"usually_detailed", "often_expressive"}
    assert profiles["2"]["emoji_message_rate"] > 0


def test_concise_user_not_automatically_penalized_and_timestamps_ignored():
    now = datetime.utcnow()
    messages = []
    for i in range(12):
        messages.append({"sender_id": 1, "content": ["Yep", "Nice", "True", "Wow"][i % 4], "created_at": now - timedelta(days=i * 4)})
        messages.append({"sender_id": 2, "content": "I went hiking last weekend and loved the mountain view, what places do you enjoy?", "created_at": now - timedelta(days=i * 4)})
    result = analyze_engagement(messages)
    assert set(result["scores"]) == {"1", "2"}
    assert 0 <= result["scores"]["1"] <= 100
    assert result["shared_health_score"] is not None
    assert "not scored" in result["method_note"]


def test_topic_overlap_requires_both_participants_and_detects_unanswered_last_question():
    messages = [
        {"sender_id": 1, "content": "I love travelling and hiking."},
        {"sender_id": 2, "content": "Travelling is my favorite too, especially road trips."},
        {"sender_id": 1, "content": "Have you been to the mountains?"},
    ]
    result = discover_topics(messages)
    assert "travel" in result["supported_shared_topics"]
    assert result["unanswered_latest_questions"] == ["Have you been to the mountains?"]


def test_mood_is_probabilistic_and_insufficient_data_stays_uncertain():
    messages = [{"sender_id": 1, "content": "Excited! Can't wait, this is amazing 😄"}]
    result = analyze_mood(messages)
    assert result["participants"]["1"]["state"] == "uncertain"
    longer = messages * 3
    assert analyze_mood(longer)["participants"]["1"]["confidence"] <= .85


def test_intelligence_has_separate_participant_views_and_shared_topics():
    messages = [
        {"sender_id": 1, "content": "I love travelling and hiking."},
        {"sender_id": 2, "content": "I love travelling too, road trips are great."},
    ] * 5
    result = build_conversation_intelligence(messages)
    assert set(result["participant_views"]) == {"1", "2"}
    assert "travel" in result["shared"]["topics"]["supported_shared_topics"]
    assert "private_memories" not in result["shared"]

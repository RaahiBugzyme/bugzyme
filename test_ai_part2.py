from datetime import datetime, timedelta
import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main, models
from app.ai.ai_evaluation import meaningful_response
from app.ai.conversation_coach import build_private_coaching
from app.ai.recovery_strategy import select_recovery_strategy
from app.ai.strategy_performance import summarize_strategy_performance


@pytest.fixture
def ai_db():
    engine = create_engine("sqlite://")
    tables = [models.User.__table__, models.Chat.__table__, models.Message.__table__,
              models.DeathZoneConversationState.__table__, models.DeathZoneNotification.__table__,
              models.AIRecoveryIntervention.__table__, models.AISuggestionRecord.__table__,
              models.AISuggestionEvent.__table__]
    models.Base.metadata.create_all(engine, tables=tables)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close(); engine.dispose()


def _conversation(sender_id=1, other_id=2, contents=None, stamp=None):
    contents = contents or [
        "I had a long day at work today.", "Oh okay.",
        "I finally tried the new little cafe near my place.", "Nice.",
        "They had a really good coffee and a quiet reading corner.", "Cool.",
        "I might go back and try one of their desserts soon.", "Yeah.",
    ]
    now = stamp or datetime.utcnow()
    return [{"sender_id": sender_id if i % 2 == 0 else other_id,
             "content": text, "created_at": now - timedelta(minutes=(len(contents)-i))}
            for i, text in enumerate(contents)]


def test_recovery_selects_distinct_approach_for_question_heavy_flow():
    messages = _conversation(contents=[
        "What do you do?", "I work in design.", "Do you like it?", "Yeah.",
        "What do you do after work?", "Mostly read.", "What do you read?", "Novels.",
    ])
    result = select_recovery_strategy(messages)
    assert result["should_intervene"] is True
    assert result["reason"] == "question_heavy_flow"
    assert result["strategy"] == "personal_experience_sharing"


def test_recovery_respects_insufficient_context_and_natural_pause():
    assert select_recovery_strategy(_conversation(contents=["Hi", "Hey"]))["should_intervene"] is False
    old = _conversation(stamp=datetime.utcnow() - timedelta(days=2))
    assert select_recovery_strategy(old)["reason"] == "natural_pause"
    assert select_recovery_strategy(old)["strategy"] == "give_space"


def test_failed_strategy_is_not_immediately_repeated():
    messages = _conversation(contents=[
        "Today was busy at work.", "Okay.", "I got home late.", "Hmm.",
        "I made dinner and watched a show.", "Nice.", "It was a quiet night.", "Cool.",
    ])
    result = select_recovery_strategy(messages, previous_strategies=["open_ended_discussion"])
    assert result["strategy"] != "open_ended_discussion"
    assert result["reason"].endswith("previous_strategy_unsuccessful")


def test_coach_uses_only_requesting_users_messages():
    messages = [
        {"sender_id": 1, "content": "What do you like?"},
        {"sender_id": 2, "content": "I like travel."},
        {"sender_id": 2, "content": "What about you?"},
        {"sender_id": 2, "content": "Any favourite place?"},
        {"sender_id": 2, "content": "Have you been to Japan?"},
        {"sender_id": 2, "content": "What do you think?"},
    ]
    result = build_private_coaching(messages, {"shared_topics": ["travel"]}, own_user_id=1)
    assert all(item["key"] != "share_experience" for item in result["insights"])
    assert result["private"] is True


def test_meaningful_reply_is_not_equated_with_any_reply():
    assert meaningful_response("Yep") is False
    assert meaningful_response("I tried that trail last spring and loved the view") is True


def test_strategy_performance_waits_for_sufficient_explicit_feedback():
    few = summarize_strategy_performance([
        {"strategy": "topic_revival", "rating": "not_helpful"},
        {"strategy": "topic_revival", "rating": "not_helpful"},
    ])
    assert few["topic_revival"]["avoid_for_now"] is False
    enough = summarize_strategy_performance(
        [{"strategy": "topic_revival", "rating": "not_helpful"}] * 5
    )
    assert enough["topic_revival"]["avoid_for_now"] is True


def test_private_coach_api_and_suggestion_events_are_owner_scoped(ai_db, monkeypatch):
    a = models.User(username="coach_a", email="coach_a@example.test", hashed_password="x")
    b = models.User(username="coach_b", email="coach_b@example.test", hashed_password="x")
    stranger = models.User(username="coach_c", email="coach_c@example.test", hashed_password="x")
    ai_db.add_all([a, b, stranger]); ai_db.flush()
    chat = models.Chat(user1_id=a.id, user2_id=b.id); ai_db.add(chat); ai_db.flush()
    for i, text in enumerate(["What do you like?", "I like travel and music." ] * 5):
        ai_db.add(models.Message(chat_id=chat.id, sender_id=a.id if i % 2 == 0 else b.id, content=text))
    intervention = models.AIRecoveryIntervention(chat_id=chat.id, user_id=a.id,
        recovery_reason="question_heavy_flow", strategy="personal_experience_sharing", prompt_version="test-v1")
    ai_db.add(intervention); ai_db.flush()
    suggestion_text = "I tried the trail last spring and loved the view."
    record = models.AISuggestionRecord(intervention_id=intervention.id, chat_id=chat.id,
        user_id=a.id, suggestion_hash=hashlib.sha256(suggestion_text.encode()).hexdigest(), strategy="personal_experience_sharing",
        prompt_version="test-v1", model_id="test", validation_passed=True)
    ai_db.add(record); ai_db.flush()
    sent_message = models.Message(chat_id=chat.id, sender_id=a.id, content=suggestion_text)
    ai_db.add(sent_message); ai_db.commit()
    monkeypatch.setattr("app.ai.conversation_coach.generate_private_coaching", lambda *args, **kwargs: {
        "available": True, "private": True,
        "insights": [{"category": "Strength", "message": "You share helpful context."},
                     {"category": "Try next", "message": "Add a personal example."}],
    })
    coach = main.get_private_conversation_coach(chat.id, current_user=a, db=ai_db)
    assert coach["private"] is True and coach["user_id"] == a.id
    insights = main.get_private_conversation_insights(chat.id, current_user=a, db=ai_db)
    assert insights["user_id"] == a.id
    assert "engagement_score" not in insights
    with pytest.raises(main.HTTPException) as exc:
        main.get_private_conversation_coach(chat.id, current_user=stranger, db=ai_db)
    assert exc.value.status_code == 403
    with pytest.raises(main.HTTPException) as exc:
        main.get_private_conversation_insights(chat.id, current_user=stranger, db=ai_db)
    assert exc.value.status_code == 403
    payload = {"event_type": "selected", "event_key": "click-1", "details": {}}
    assert main.track_ai_suggestion_event(record.id, payload, current_user=a, db=ai_db)["ok"] is True
    sent = {"event_type": "sent", "event_key": "sent-1", "details": {"message_id": sent_message.id}}
    assert main.track_ai_suggestion_event(record.id, sent, current_user=a, db=ai_db)["ok"] is True
    assert ai_db.query(models.AISuggestionEvent).filter_by(suggestion_id=record.id).count() == 2
    with pytest.raises(main.HTTPException) as exc:
        main.track_ai_suggestion_event(record.id, payload, current_user=b, db=ai_db)
    assert exc.value.status_code == 404


def test_outcome_is_recorded_only_after_a_persisted_reply(ai_db):
    a = models.User(username="outcome_a", email="outcome_a@example.test", hashed_password="x")
    b = models.User(username="outcome_b", email="outcome_b@example.test", hashed_password="x")
    ai_db.add_all([a, b]); ai_db.flush()
    chat = models.Chat(user1_id=a.id, user2_id=b.id); ai_db.add(chat); ai_db.flush()
    for i in range(10):
        ai_db.add(models.Message(chat_id=chat.id, sender_id=a.id if i % 2 == 0 else b.id,
                                 content="I enjoyed the mountain walk and the view was beautiful."))
    ai_db.flush()
    trigger = ai_db.query(models.Message).order_by(models.Message.id.desc()).first()
    intervention = models.AIRecoveryIntervention(chat_id=chat.id, user_id=a.id,
        trigger_message_id=trigger.id, recovery_reason="one_sided_communication",
        strategy="natural_continuation", prompt_version="test-v1", status="generated")
    ai_db.add(intervention); ai_db.flush()
    record = models.AISuggestionRecord(intervention_id=intervention.id, chat_id=chat.id,
        user_id=a.id, suggestion_hash="b" * 64, strategy="natural_continuation",
        prompt_version="test-v1", model_id="test", validation_passed=True)
    ai_db.add(record); ai_db.flush()
    ai_db.add(models.AISuggestionEvent(suggestion_id=record.id, chat_id=chat.id, user_id=a.id,
        event_key="sent-test", event_type="sent"))
    reply = models.Message(chat_id=chat.id, sender_id=b.id,
                           content="That mountain trail was lovely. What other hikes do you like?")
    ai_db.add(reply); ai_db.commit()
    main._evaluate_ai_response(ai_db, chat.id, b.id, reply.id)
    ai_db.refresh(intervention)
    assert intervention.status in {"responded", "observed_improvement"}
    types = {row.event_type for row in ai_db.query(models.AISuggestionEvent).filter_by(suggestion_id=record.id)}
    assert "continued" in types and "meaningful_response" in types

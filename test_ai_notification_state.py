from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main, models
from app.main import _notification_payload, utcnow


def _notification(*, viewed_at=None, expires_at=None):
    return SimpleNamespace(
        id=4,
        chat_id=12,
        user_id=7,
        event_key="message-99",
        status="ready",
        suggestions_json='[{"style":"natural","message":"Ask about the book."}]',
        death_zone_json='{"status":"stagnant"}',
        created_at=utcnow(),
        viewed_at=viewed_at,
        expires_at=expires_at,
    )


def test_unviewed_notification_remains_active_until_opened():
    result = _notification_payload(_notification())
    assert result["active"] is True
    assert result["suggestions"][0]["message"] == "Ask about the book."


def test_viewed_notification_is_active_only_during_its_thirty_second_window():
    now = utcnow()
    assert _notification_payload(_notification(
        viewed_at=now, expires_at=now + timedelta(seconds=30)
    ))["active"] is True
    assert _notification_payload(_notification(
        viewed_at=now - timedelta(seconds=31), expires_at=now - timedelta(seconds=1)
    ))["active"] is False


@pytest.fixture
def ai_db():
    engine = create_engine("sqlite://")
    tables = [
        models.User.__table__, models.Chat.__table__, models.Message.__table__,
        models.DeathZoneConversationState.__table__, models.DeathZoneNotification.__table__,
        models.AIRecoveryIntervention.__table__, models.AISuggestionRecord.__table__,
        models.AISuggestionEvent.__table__,
    ]
    models.Base.metadata.create_all(engine, tables=tables)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_declining_chat(db):
    effort_user = models.User(username="effort", email="effort@example.test", hashed_password="x")
    dry_user = models.User(username="dry", email="dry@example.test", hashed_password="x")
    db.add_all([effort_user, dry_user])
    db.flush()
    chat = models.Chat(user1_id=effort_user.id, user2_id=dry_user.id)
    db.add(chat)
    db.flush()
    messages = []
    for index in range(12):
        messages.append(models.Message(
            chat_id=chat.id,
            sender_id=effort_user.id if index % 2 == 0 else dry_user.id,
            content="We spent a wonderful afternoon walking around the old market and trying a new restaurant.",
        ))
    for index, short_reply in enumerate(["Yeah", "Okay", "Fine", "Hmm", "Sure", "Yep", "Okay", "Hmm"]):
        if index < 4:
            messages.append(models.Message(
                chat_id=chat.id,
                sender_id=effort_user.id,
                content=f"I remember that exhibition and the photography section was beautiful, it reminded me of the art walk in Pune {index}.",
            ))
        messages.append(models.Message(chat_id=chat.id, sender_id=dry_user.id, content=short_reply))
    db.add_all(messages)
    db.commit()
    return chat, effort_user, dry_user, messages[-1]


def test_detection_persists_one_private_notification_and_view_starts_expiry(ai_db, monkeypatch):
    chat, effort_user, dry_user, last_message = _seed_declining_chat(ai_db)
    suggestions = [
        {"style": "natural", "message": "What did you like most about the exhibition?"},
        {"style": "playful", "message": "I need your top-secret art-walk recommendation."},
        {"style": "thoughtful", "message": "That photography section sounds memorable."},
    ]
    calls = []

    def fake_workflow(**kwargs):
        calls.append(kwargs["requesting_user_id"])
        return {"should_generate": True, "suggestion_result": {"suggestions": suggestions}}

    monkeypatch.setattr(main, "run_conversation_workflow", fake_workflow)
    payload = main._prepare_death_zone_notification(ai_db, chat.id, last_message.id)
    assert payload["user_id"] == effort_user.id
    assert payload["active"] is True
    assert [row["message"] for row in payload["suggestions"]] == [row["message"] for row in suggestions]
    assert all(row.get("suggestion_id") for row in payload["suggestions"])
    assert calls == [effort_user.id]

    # The same still-active episode must not generate or notify a duplicate.
    assert main._prepare_death_zone_notification(ai_db, chat.id, last_message.id) is None
    assert calls == [effort_user.id]
    row = ai_db.query(models.DeathZoneNotification).one()
    assert row.user_id != dry_user.id

    viewed = main.view_ai_notification(row.id, current_user=effort_user, db=ai_db)
    first_expiry = viewed["expires_at"]
    assert viewed["active"] is True
    assert viewed["viewed_at"] is not None
    parsed_expiry = datetime.fromisoformat(first_expiry.removesuffix("Z"))
    assert timedelta(seconds=29) < parsed_expiry - utcnow() <= timedelta(seconds=30)
    assert main.view_ai_notification(row.id, current_user=effort_user, db=ai_db)["expires_at"] == first_expiry
    with pytest.raises(main.HTTPException) as error:
        main.view_ai_notification(row.id, current_user=dry_user, db=ai_db)
    assert error.value.status_code == 404

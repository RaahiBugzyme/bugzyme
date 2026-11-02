import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main, models, schemas
from app.connection_manager import ConnectionManager


class FakeSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, payload):
        self.events.append(payload)


@pytest.fixture
def presence_db(monkeypatch):
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    manager = ConnectionManager()
    monkeypatch.setattr(main, "manager", manager)
    try:
        yield db, manager
    finally:
        db.close()
        engine.dispose()


def test_presence_preference_overrides_active_sockets_and_resumes(presence_db):
    db, manager = presence_db
    user = models.User(username="presence_a", email="presence_a@example.test", hashed_password="x")
    viewer = models.User(username="presence_b", email="presence_b@example.test", hashed_password="x")
    db.add_all([user, viewer])
    db.commit()

    user_socket_a, user_socket_b, viewer_socket = FakeSocket(), FakeSocket(), FakeSocket()
    manager.connect(user.id, user_socket_a)
    manager.connect(user.id, user_socket_b)
    manager.connect(viewer.id, viewer_socket)

    user.activity_status_enabled = True
    db.commit()
    assert user.id in main.visible_online_ids(db)
    assert next(row for row in main.get_users(viewer, db) if row.id == user.id).is_online is True

    hidden = asyncio.run(main.update_presence_preference(
        schemas.PresencePreferenceUpdate(activity_status_enabled=False), user, db
    ))
    assert hidden["activity_status_enabled"] is False
    assert hidden["is_online"] is False
    assert main.me(user).activity_status_enabled is False  # persisted state used after refresh/login
    assert main.set_online(db, user.id, True)["is_online"] is False  # reconnect/heartbeat cannot override opt-out
    assert user.id not in main.visible_online_ids(db)  # heartbeat/socket remains connected
    assert next(row for row in main.get_users(viewer, db) if row.id == user.id).is_online is False
    assert viewer_socket.events[-1]["status"] == "offline"

    visible = asyncio.run(main.update_presence_preference(
        schemas.PresencePreferenceUpdate(activity_status_enabled=True), user, db
    ))
    assert visible["activity_status_enabled"] is True
    assert visible["is_online"] is True
    assert user.id in main.visible_online_ids(db)
    assert next(row for row in main.get_users(viewer, db) if row.id == user.id).is_online is True
    assert viewer_socket.events[-1]["status"] == "online"

    # One of multiple tabs closing must not mark the account offline.
    assert manager.disconnect(user.id, user_socket_a) is False
    assert manager.is_online(user.id) is True

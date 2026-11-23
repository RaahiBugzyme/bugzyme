"""Profile storage is kept OUT of the model. Implement ProfileRepository for your database."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .feature_engineering import is_missing


class ProfileRepository(ABC):
    @abstractmethod
    def get(self, user_id: Any) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def all(self) -> List[Dict[str, Any]]: ...


class InMemoryProfileRepository(ProfileRepository):
    def __init__(self, profiles: List[Dict[str, Any]]):
        self._profiles = [dict(p) for p in profiles]
        self._by_id = {str(p["id"]): p for p in self._profiles}

    def get(self, user_id):
        return self._by_id.get(str(user_id))

    def all(self):
        return list(self._profiles)


class CsvProfileRepository(InMemoryProfileRepository):
    """Loads profiles from a CSV. Example/dev only; use your real DB in production."""

    def __init__(self, path: str, id_column: Optional[str] = None):
        import pandas as pd

        frame = pd.read_csv(path)
        records = []
        for index, row in frame.iterrows():
            record = {k: (None if is_missing(v) else (v.item() if hasattr(v, "item") else v)) for k, v in row.items()}
            record["id"] = str(record[id_column]) if id_column else str(index)
            records.append(record)
        super().__init__(records)


# ==========================================================================
# v2.2.0 (append-only): extended, database-ready interface. `ProfileRepository` above is
# unchanged, so existing subclasses keep working. Implement RecommendationRepository on top of
# your SQL tables; the CSV / in-memory versions below are for research and tests.
# ==========================================================================
import threading  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Iterable  # noqa: E402

from .behavior import summarize_behavior, utcnow  # noqa: E402


class RecommendationRepository(ProfileRepository):
    """Adds interactions and preferences. SQL-ready: every method maps to one query."""

    # --- profiles
    def get_user(self, user_id: Any) -> Optional[Dict[str, Any]]:
        return self.get(user_id)

    def get_candidate_profiles(self, exclude_user_id: Any = None) -> List[Dict[str, Any]]:
        return [p for p in self.all() if exclude_user_id is None or str(p.get("id")) != str(exclude_user_id)]

    @abstractmethod
    def get_blocked_user_ids(self, user_id: Any) -> List[str]: ...

    @abstractmethod
    def block_user(self, user_id: Any, blocked_user_id: Any) -> Dict[str, Any]: ...

    @abstractmethod
    def unblock_user(self, user_id: Any, blocked_user_id: Any) -> Dict[str, Any]: ...

    # --- interactions
    @abstractmethod
    def get_interactions(self, user_id: Any) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def save_interaction(self, event: Dict[str, Any]) -> Dict[str, Any]: ...

    # --- explicit preferences
    @abstractmethod
    def get_user_preferences(self, user_id: Any) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def save_user_preferences(self, user_id: Any, preferences: Dict[str, Any]) -> Dict[str, Any]: ...

    # --- personality preferences (Phase 6)
    def get_user_personality(self, user_id: Any) -> Optional[Dict[str, Any]]:
        return None

    def save_user_personality(self, user_id: Any, personality: Dict[str, Any]) -> Dict[str, Any]:
        return dict(personality)

    # --- privacy controls (Phase 6)
    def get_privacy_settings(self, user_id: Any) -> Dict[str, Any]:
        return {
            "user_id": str(user_id),
            "personalization_enabled": True,
            "message_analysis_consent": False,
            "raw_message_retention": False,
        }

    def save_privacy_settings(self, user_id: Any, settings: Dict[str, Any]) -> Dict[str, Any]:
        return dict(settings)

    def delete_interactions(self, user_id: Any) -> int:
        return 0

    # --- external interest personalization (Phase 1)
    def get_external_interests(self, user_id: Any, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    def save_external_interests(self, user_id: Any, provider: str, interests: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"user_id": str(user_id), "provider": str(provider).lower(), "count": len(interests)}

    def delete_external_interests(self, user_id: Any, provider: Optional[str] = None) -> int:
        return 0

    def get_external_accounts(self, user_id: Any) -> List[Dict[str, Any]]:
        return []

    def remove_external_interest(self, user_id: Any, token: str, provider: Optional[str] = None) -> int:
        return 0

    def update_external_interest(self, user_id: Any, token: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    # --- derived (override with an aggregate SQL query if you prefer)
    def get_behavior_summary(self, user_id: Any, config: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        return summarize_behavior(self.get_interactions(user_id), user_id, config, now or utcnow())


class InMemoryRecommendationRepository(RecommendationRepository):
    def __init__(self, profiles: Iterable[Dict[str, Any]] = (), interactions: Iterable[Dict[str, Any]] = (),
                 preferences: Optional[Dict[str, Dict[str, Any]]] = None,
                 personalities: Optional[Dict[str, Dict[str, Any]]] = None):
        self._lock = threading.Lock()
        self._profiles = [dict(p) for p in profiles]
        self._by_id = {str(p["id"]): p for p in self._profiles}
        self._interactions: List[Dict[str, Any]] = [dict(e) for e in interactions]
        self._preferences = {str(k): dict(v) for k, v in (preferences or {}).items()}
        self._personalities = {str(k): dict(v) for k, v in (personalities or {}).items()}
        self._privacy_settings: Dict[str, Dict[str, Any]] = {}
        self._external_interests: Dict[str, List[Dict[str, Any]]] = {}
        self._external_accounts: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._blocks = set()

    def get(self, user_id):
        return self._by_id.get(str(user_id))

    def all(self):
        return list(self._profiles)

    def get_interactions(self, user_id):
        return [dict(e) for e in self._interactions if str(e["user_id"]) == str(user_id)]

    def save_interaction(self, event):
        with self._lock:
            self._interactions.append(dict(event))
        return dict(event)

    def delete_interactions(self, user_id) -> int:
        uid = str(user_id)
        with self._lock:
            before = len(self._interactions)
            self._interactions = [e for e in self._interactions if str(e.get("user_id")) != uid]
            return before - len(self._interactions)

    def get_user_preferences(self, user_id):
        prefs = self._preferences.get(str(user_id))
        return None if prefs is None else dict(prefs)

    def save_user_preferences(self, user_id, preferences):
        with self._lock:
            self._preferences[str(user_id)] = dict(preferences)
        return dict(preferences)

    def get_user_personality(self, user_id):
        p = self._personalities.get(str(user_id))
        return None if p is None else dict(p)

    def save_user_personality(self, user_id, personality):
        with self._lock:
            self._personalities[str(user_id)] = dict(personality)
        return dict(personality)

    def get_privacy_settings(self, user_id):
        uid = str(user_id)
        if uid not in self._privacy_settings:
            return {
                "user_id": uid,
                "personalization_enabled": True,
                "message_analysis_consent": False,
                "raw_message_retention": False,
            }
        return dict(self._privacy_settings[uid])

    def save_privacy_settings(self, user_id, settings):
        uid = str(user_id)
        with self._lock:
            curr = self.get_privacy_settings(uid)
            curr.update(settings)
            curr["user_id"] = uid
            self._privacy_settings[uid] = curr
        return dict(curr)

    def get_external_interests(self, user_id, provider=None):
        uid = str(user_id)
        with self._lock:
            items = [dict(i) for i in self._external_interests.get(uid, [])]
            if provider is not None:
                p = str(provider).lower()
                items = [i for i in items if str(i.get("provider", "")).lower() == p]
            return items

    def save_external_interests(self, user_id, provider, interests):
        uid = str(user_id)
        p = str(provider).lower()
        clean = [dict(i) for i in interests]
        with self._lock:
            curr = [i for i in self._external_interests.get(uid, []) if str(i.get("provider", "")).lower() != p]
            curr.extend(clean)
            self._external_interests[uid] = curr
            accts = self._external_accounts.setdefault(uid, {})
            accts[p] = {
                "provider": p,
                "user_id": uid,
                "item_count": len(clean),
                "updated_at": utcnow().isoformat() + "Z",
            }
        return {"user_id": uid, "provider": p, "count": len(clean), "total_external_interests": len(curr)}

    def delete_external_interests(self, user_id, provider=None):
        uid = str(user_id)
        with self._lock:
            curr = self._external_interests.get(uid, [])
            if provider is None:
                deleted_count = len(curr)
                self._external_interests.pop(uid, None)
                self._external_accounts.pop(uid, None)
                return deleted_count
            p = str(provider).lower()
            remaining = [i for i in curr if str(i.get("provider", "")).lower() != p]
            deleted_count = len(curr) - len(remaining)
            self._external_interests[uid] = remaining
            if uid in self._external_accounts:
                self._external_accounts[uid].pop(p, None)
            return deleted_count

    def get_external_accounts(self, user_id):
        uid = str(user_id)
        with self._lock:
            return [dict(v) for v in self._external_accounts.get(uid, {}).values()]

    def remove_external_interest(self, user_id, token, provider=None):
        uid = str(user_id)
        tok = str(token)
        with self._lock:
            curr = self._external_interests.get(uid, [])
            p_filter = str(provider).lower() if provider else None
            remaining = [
                i for i in curr
                if not (i.get("canonical_token") == tok and (p_filter is None or str(i.get("provider", "")).lower() == p_filter))
            ]
            deleted_count = len(curr) - len(remaining)
            self._external_interests[uid] = remaining
            if p_filter and uid in self._external_accounts and p_filter in self._external_accounts[uid]:
                p_items = [i for i in remaining if str(i.get("provider", "")).lower() == p_filter]
                self._external_accounts[uid][p_filter]["item_count"] = len(p_items)
            return deleted_count

    def update_external_interest(self, user_id, token, updates):
        uid = str(user_id)
        tok = str(token)
        with self._lock:
            curr = self._external_interests.get(uid, [])
            updated_item = None
            for i in curr:
                if i.get("canonical_token") == tok:
                    i.update(updates)
                    updated_item = dict(i)
            return updated_item

    def get_blocked_user_ids(self, user_id):
        return sorted(blocked_id for owner, blocked_id in self._blocks if owner == str(user_id))

    def block_user(self, user_id, blocked_user_id):
        if str(user_id) == str(blocked_user_id):
            raise ValueError("users cannot block themselves")
        if self.get(blocked_user_id) is None:
            raise KeyError(f"unknown user: {blocked_user_id}")
        with self._lock:
            self._blocks.add((str(user_id), str(blocked_user_id)))
        return {"user_id": str(user_id), "blocked_user_id": str(blocked_user_id), "blocked": True}

    def unblock_user(self, user_id, blocked_user_id):
        with self._lock:
            self._blocks.discard((str(user_id), str(blocked_user_id)))
        return {"user_id": str(user_id), "blocked_user_id": str(blocked_user_id), "blocked": False}


class CsvRecommendationRepository(InMemoryRecommendationRepository):
    """Profiles from a CSV (like CsvProfileRepository) + optional interactions CSV
    (columns: user_id, candidate_id, action, timestamp[, session_id, source])."""

    def __init__(self, profiles_path: str, id_column: Optional[str] = None, interactions_path: Optional[str] = None):
        base = CsvProfileRepository(profiles_path, id_column=id_column)
        events: List[Dict[str, Any]] = []
        if interactions_path:
            import pandas as pd
            from .behavior import validate_event
            for row in pd.read_csv(interactions_path, dtype=str).to_dict("records"):
                events.append(validate_event({k: (None if is_missing(v) else v) for k, v in row.items()}))
        super().__init__(base.all(), events)

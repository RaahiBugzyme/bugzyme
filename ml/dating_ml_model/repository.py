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


class SQLAlchemyUserRepository(ProfileRepository):
    """SQLAlchemy-backed ProfileRepository that reads from the existing User table.

    Accepts an existing SQLAlchemy Session (does not create one).
    Implements only ProfileRepository.get() and ProfileRepository.all().
    No fake profiles, no hardcoded user IDs, no new database models.
    """

    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: Any) -> Optional[Dict[str, Any]]:
        from app.models import User  # lazy import to avoid circular import
        user = self.db.get(User, user_id)
        if user is None:
            return None
        return _user_row_to_dict(user)

    def all(self) -> List[Dict[str, Any]]:
        from app.models import User  # lazy import to avoid circular import
        users = self.db.query(User).all()
        return [_user_row_to_dict(u) for u in users]


def _user_row_to_dict(user) -> Dict[str, Any]:
    """Convert a SQLAlchemy User row to a DatingML profile dict.

    Includes ``id`` because MatchingService.get_matches() and
    predict_matches() rely on profile.get("id") to identify candidates.
    Other fields mirror the existing user_to_datingml_profile adapter.
    """
    from app.models import DatingProfile  # lazy import to avoid circular import

    profile: Dict[str, Any] = {}
    profile["id"] = user.id
    profile["username"] = user.username
    # Prefer DatingProfile fields over User fields
    dp = user.dating_profile
    if dp:
        if dp.full_name:
            profile["full_name"] = dp.full_name
        if dp.bio:
            profile["bio"] = dp.bio
        if dp.activity_status_enabled is not None:
            profile["activity_status_enabled"] = dp.activity_status_enabled
        if dp.ai_memory_enabled is not None:
            profile["ai_memory_enabled"] = dp.ai_memory_enabled
        if dp.is_face_verified is not None:
            profile["is_face_verified"] = dp.is_face_verified
        if dp.is_id_verified is not None:
            profile["is_id_verified"] = dp.is_id_verified
        if dp.verification_status:
            profile["verification_status"] = dp.verification_status
        if dp.profile_completion_pct is not None:
            profile["profile_completion_pct"] = dp.profile_completion_pct
        if dp.is_profile_public is not None:
            profile["is_profile_public"] = dp.is_profile_public
        if dp.height is not None:
            profile["height"] = dp.height
        if dp.body_type:
            profile["body_type"] = dp.body_type
        if dp.orientation:
            profile["orientation"] = dp.orientation
        if dp.target_gender_preference:
            profile["target_gender_preference"] = dp.target_gender_preference
        if dp.match_era_preference:
            profile["match_era_preference"] = dp.match_era_preference
        if dp.sex:
            profile["sex"] = dp.sex
        if dp.drinks:
            profile["drinks"] = dp.drinks
        if dp.drugs:
            profile["drugs"] = dp.drugs
        if dp.smokes:
            profile["smokes"] = dp.smokes
        if dp.diet:
            profile["diet"] = dp.diet
        if dp.offspring:
            profile["offspring"] = dp.offspring
        if dp.pets:
            profile["pets"] = dp.pets
        if dp.religion:
            profile["religion"] = dp.religion
        if dp.ethnicity:
            profile["ethnicity"] = dp.ethnicity
        if dp.education:
            profile["education"] = dp.education
        if dp.job:
            profile["job"] = dp.job
        if dp.city:
            profile["city"] = dp.city
        if dp.state:
            profile["state"] = dp.state
        if dp.country:
            profile["country"] = dp.country
    else:
        # Fall back to User fields
        if user.full_name:
            profile["full_name"] = user.full_name
        if user.bio:
            profile["bio"] = user.bio
        profile["activity_status_enabled"] = user.activity_status_enabled
        profile["ai_memory_enabled"] = user.ai_memory_enabled
        if user.last_seen:
            profile["last_seen"] = (
                user.last_seen.isoformat()
                if hasattr(user.last_seen, "isoformat")
                else str(user.last_seen)
            )
    return profile


# -----------------------------------------------------------------
#  DatingProfile Repository
# -----------------------------------------------------------------
class DatingProfileRepository:
    """SQLAlchemy-backed DatingProfile repository.

    Accepts an existing SQLAlchemy Session (does not create one).
    """

    def __init__(self, db: Session):
        from app.models import DatingProfile  # lazy import to avoid circular import
        self.db = db

    def get(self, user_id: Any) -> Optional[Dict[str, Any]]:
        from app.models import User  # lazy import to avoid circular import
        dp = self.db.get(DatingProfile, user_id)
        if dp is None:
            return None
        return _dp_to_dict(dp)

    def get_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        from app.models import User
        dp = self.db.query(DatingProfile).filter(DatingProfile.user_id == user_id).first()
        if dp is None:
            return None
        return _dp_to_dict(dp)

    def create(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        from app.models import User
        # Check if profile already exists
        existing = self.db.get(DatingProfile, user_id)
        if existing:
            raise ValueError("Dating profile already exists for this user")
        
        dp = DatingProfile(user_id=user_id, **data)
        self.db.add(dp)
        self.db.commit()
        self.db.refresh(dp)
        return _dp_to_dict(dp)

    def update(self, user_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from app.models import User
        dp = self.db.get(DatingProfile, user_id)
        if dp is None:
            return None
        for key, value in data.items():
            if hasattr(dp, key) and value is not None:
                setattr(dp, key, value)
        self.db.commit()
        self.db.refresh(dp)
        return _dp_to_dict(dp)

    def delete(self, user_id: int) -> bool:
        from app.models import User
        dp = self.db.get(DatingProfile, user_id)
        if dp is None:
            return False
        self.db.delete(dp)
        self.db.commit()
        return True


def _dp_to_dict(dp: DatingProfile) -> Dict[str, Any]:
    """Convert DatingProfile to dict for DatingML compatibility."""
    profile: Dict[str, Any] = {}
    profile["id"] = dp.id
    profile["user_id"] = dp.user_id
    profile["date_of_birth"] = dp.date_of_birth
    profile["sex"] = dp.sex
    profile["orientation"] = dp.orientation
    profile["full_name"] = dp.full_name
    profile["bio"] = dp.bio
    profile["education"] = dp.education
    profile["job"] = dp.job
    profile["religion"] = dp.religion
    profile["ethnicity"] = dp.ethnicity
    profile["drinks"] = dp.drinks
    profile["drugs"] = dp.drugs
    profile["smokes"] = dp.smokes
    profile["diet"] = dp.diet
    profile["offspring"] = dp.offspring
    profile["pets"] = dp.pets
    profile["height"] = dp.height
    profile["body_type"] = dp.body_type
    profile["city"] = dp.city
    profile["state"] = dp.state
    profile["country"] = dp.country
    profile["match_era_preference"] = dp.match_era_preference
    profile["target_gender_preference"] = dp.target_gender_preference
    profile["behavioral_personalization_enabled"] = dp.behavioral_personalization_enabled
    profile["is_face_verified"] = dp.is_face_verified
    profile["is_id_verified"] = dp.is_id_verified
    profile["verification_status"] = dp.verification_status
    profile["profile_completion_pct"] = dp.profile_completion_pct
    profile["is_profile_public"] = dp.is_profile_public
    profile["created_at"] = dp.created_at.isoformat() if dp.created_at else None
    profile["updated_at"] = dp.updated_at.isoformat() if dp.updated_at else None
    return profile


class CsvRecommendationRepository(InMemoryRecommendationRepository):
    """Profiles from a CSV (like CsvProfileRepository) + optional interactions CSV
    (columns: user_id, candidate_id, action, timestamp[, session_id, source]).
    """


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

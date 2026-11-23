"""Service layer: orchestrates repository + model. Contains NO scoring formulas."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .model import CompatibilityModel
from .repository import ProfileRepository


class MatchingService:
    def __init__(self, model: CompatibilityModel, repository: ProfileRepository):
        self.model = model
        self.repository = repository

    def predict_pair(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> Dict[str, Any]:
        return self.model.predict_pair(profile_a, profile_b)

    def get_matches(self, user_id: Any, top_k: int = 10) -> List[Dict[str, Any]]:
        user = self.repository.get(user_id)
        if user is None:
            raise KeyError(f"unknown user: {user_id}")
        return self.model.predict_matches(user, self.repository.all(), top_k)


# ==========================================================================
# v2.2.0 (append-only): recommendation / interaction use-cases. No scoring formulas live here.
# ==========================================================================
from datetime import datetime  # noqa: E402
from typing import Callable  # noqa: E402

from .behavior import utcnow, validate_event  # noqa: E402
from .model import RecommendationModel  # noqa: E402
from .preferences import evaluate_preferences, normalize_preferences  # noqa: E402
from .repository import RecommendationRepository  # noqa: E402
from .search_intent import learn_search_intent  # noqa: E402
from .preference_interpreter import interpret_preference_request  # noqa: E402
from .personality import normalize_personality_profile  # noqa: E402
from .privacy import PrivacyManager  # noqa: E402
from .interests import UserInterestProfile  # noqa: E402
from .external_interests import (  # noqa: E402
    ExternalInterestProvider,
    MockGoogleInterestProvider,
    MockInstagramInterestProvider,
    validate_and_normalize_manual_interest,
    MAX_MANUAL_INTERESTS_PER_USER,
    normalize_interest_tag,
)


class RecommendationService(MatchingService):
    """MatchingService + personalized recommendations. Needs a RecommendationRepository."""

    def __init__(self, model: CompatibilityModel, repository: RecommendationRepository,
                 recommendation_model: Optional[RecommendationModel] = None,
                 clock: Optional[Callable[[], datetime]] = None,
                 preference_ai_client: Optional[Callable[[str], Any]] = None):
        super().__init__(model, repository)
        if not isinstance(repository, RecommendationRepository):
            raise TypeError("RecommendationService requires a RecommendationRepository")
        self.recommender = recommendation_model or RecommendationModel(compatibility_model=model)
        self.clock = clock or utcnow
        self.preference_ai_client = preference_ai_client
        self.privacy_manager = PrivacyManager()
        self.mock_providers: Dict[str, ExternalInterestProvider] = {
            "google": MockGoogleInterestProvider(),
            "instagram": MockInstagramInterestProvider(),
        }

    def _user(self, user_id) -> Dict[str, Any]:
        user = self.repository.get_user(user_id)
        if user is None:
            raise KeyError(f"unknown user: {user_id}")
        return user

    def predict_pair(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any],
                     preferences_a: Optional[Dict[str, Any]] = None,
                     preferences_b: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        id_a, id_b = profile_a.get("id"), profile_b.get("id")
        prefs_a = preferences_a or profile_a.get("preferences") or profile_a.get("user_preferences")
        if prefs_a is None and id_a is not None:
            prefs_a = self.repository.get_user_preferences(id_a)
        prefs_b = preferences_b or profile_b.get("preferences") or profile_b.get("user_preferences")
        if prefs_b is None and id_b is not None:
            prefs_b = self.repository.get_user_preferences(id_b)
        return self.recommender.compatibility.predict_pair(
            profile_a, profile_b, user_preferences=prefs_a, candidate_preferences=prefs_b
        )

    def record_interaction(self, event: Dict[str, Any]) -> Dict[str, Any]:
        clean = validate_event(event, default_timestamp=self.clock())
        self._user(clean["user_id"])
        if clean["candidate_id"] is not None:
            self._user(clean["candidate_id"])
        sanitized = self.privacy_manager.sanitize_event_for_storage(clean)
        return self.repository.save_interaction(sanitized)

    def get_preferences(self, user_id) -> Dict[str, Any]:
        self._user(user_id)
        prefs = self.repository.get_user_preferences(user_id)
        return {"user_id": str(user_id), "preferences": prefs, "status": "not_set" if prefs is None else "set"}

    def save_preferences(self, user_id, preferences: Dict[str, Any]) -> Dict[str, Any]:
        self._user(user_id)
        normalized, warnings = normalize_preferences(preferences)
        self.repository.save_user_preferences(user_id, normalized)
        return {"user_id": str(user_id), "normalized": normalized, "warnings": warnings}

    def get_personality(self, user_id) -> Dict[str, Any]:
        self._user(user_id)
        pers = self.repository.get_user_personality(user_id)
        norm, warnings = normalize_personality_profile(pers)
        return {"user_id": str(user_id), "personality": norm, "warnings": warnings}

    def save_personality(self, user_id, personality: Dict[str, Any]) -> Dict[str, Any]:
        self._user(user_id)
        norm, warnings = normalize_personality_profile(personality)
        self.repository.save_user_personality(user_id, norm)
        return {"user_id": str(user_id), "personality": norm, "warnings": warnings}

    get_user_personality = get_personality
    save_user_personality = save_personality

    def get_privacy_settings(self, user_id) -> Dict[str, Any]:
        self._user(user_id)
        return self.repository.get_privacy_settings(user_id)

    def save_privacy_settings(self, user_id, settings: Dict[str, Any]) -> Dict[str, Any]:
        self._user(user_id)
        updated = self.repository.save_privacy_settings(user_id, settings)
        self.privacy_manager.update_settings(user_id, settings)
        return updated

    def delete_interactions(self, user_id) -> Dict[str, Any]:
        self._user(user_id)
        deleted_count = self.repository.delete_interactions(user_id)
        return {"user_id": str(user_id), "deleted_events_count": deleted_count, "success": True}

    def get_interest_profile(self, user_id) -> Dict[str, Any]:
        user = self._user(user_id)
        privacy = self.repository.get_privacy_settings(user_id)
        self.privacy_manager.update_settings(user_id, privacy)
        if not privacy.get("personalization_enabled", True):
            return {"user_id": str(user_id), "status": "disabled", "message": "Personalization is disabled by user settings."}
        events = self.repository.get_interactions(user_id)
        raw_ext = self.repository.get_external_interests(user_id)
        consented_ext = [
            i for i in raw_ext
            if self.privacy_manager.get_external_interest_consent(user_id, i.get("provider", ""))
        ]
        profile = UserInterestProfile(self.recommender.config).fit(
            user, events, self.repository.get_user, self.clock(),
            external_interests=consented_ext if consented_ext else None,
        )
        return profile.to_dict()

    def get_behavior_summary(self, user_id) -> Dict[str, Any]:
        self._user(user_id)
        return self.repository.get_behavior_summary(user_id, self.recommender.config, self.clock())

    def get_search_intent(self, user_id) -> Dict[str, Any]:
        self._user(user_id)
        privacy = self.repository.get_privacy_settings(user_id)
        if not privacy.get("personalization_enabled", True):
            return {"user_id": str(user_id), "status": "disabled", "message": "Search intent disabled by user settings."}
        return learn_search_intent(user_id, self.repository.get_interactions(user_id),
                                   self.recommender.config, self.clock())

    def get_preference_profile(self, user_id) -> Dict[str, Any]:
        user = self._user(user_id)
        privacy = self.repository.get_privacy_settings(user_id)
        events = self.repository.get_interactions(user_id) if privacy.get("personalization_enabled", True) else []
        model = self.recommender.fit_preference_model(user, events, self.repository.get_user, self.clock())
        return {**model.to_dict(), "explicit_preferences": self.repository.get_user_preferences(user_id)}

    def get_recommendations(self, user_id, limit: int = 20, include_interests: bool = False,
                            external_interests: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        user = self._user(user_id)
        blocked = set(self.repository.get_blocked_user_ids(user_id))
        candidates = [p for p in self.repository.get_candidate_profiles(exclude_user_id=user_id)
                      if str(p.get("id")) not in blocked]
        privacy = self.repository.get_privacy_settings(user_id)
        self.privacy_manager.update_settings(user_id, privacy)
        user_pers = self.repository.get_user_personality(user_id)
        p_enabled = bool(privacy.get("personalization_enabled", True))
        interactions = self.repository.get_interactions(user_id) if p_enabled else []
        interest_prof = None
        if p_enabled:
            raw_ext = (external_interests if external_interests is not None
                       else self.repository.get_external_interests(user_id))
            consented_ext = [
                i for i in raw_ext
                if self.privacy_manager.get_external_interest_consent(user_id, i.get("provider", ""))
            ]
            if include_interests or consented_ext:
                interest_prof = UserInterestProfile(self.recommender.config).fit(
                    user, interactions, self.repository.get_user, self.clock(),
                    external_interests=consented_ext if consented_ext else None,
                )
        return self.recommender.recommend(
            user, candidates,
            user_preferences=self.repository.get_user_preferences(user_id),
            preferences_lookup=self.repository.get_user_preferences,
            personality_lookup=self.repository.get_user_personality,
            user_personality=user_pers,
            interest_profile=interest_prof,
            privacy_settings=privacy,
            interactions=interactions, profile_lookup=self.repository.get_user,
            now=self.clock(), limit=limit)

    def block_user(self, user_id, blocked_user_id):
        self._user(user_id)
        return self.repository.block_user(user_id, blocked_user_id)

    def unblock_user(self, user_id, blocked_user_id):
        self._user(user_id)
        return self.repository.unblock_user(user_id, blocked_user_id)

    def get_blocked_users(self, user_id):
        self._user(user_id)
        return {"user_id": str(user_id), "blocked_user_ids": self.repository.get_blocked_user_ids(user_id)}

    def search_profiles(self, user_id, preferences=None):
        self._user(user_id)
        blocked = set(self.repository.get_blocked_user_ids(user_id))
        own_preferences = self.repository.get_user_preferences(user_id)
        results = []
        for candidate in self.repository.get_candidate_profiles(exclude_user_id=user_id):
            if str(candidate.get("id")) in blocked:
                continue
            evaluation = evaluate_preferences(own_preferences, candidate, self.recommender.config)
            if evaluation["hard_failures"]:
                continue
            if preferences is not None:
                query_eval = evaluate_preferences(preferences, candidate, self.recommender.config)
                if query_eval["hard_failures"]:
                    continue
            results.append(dict(candidate))
        return results

    def interpret_preferences(self, user_id, request, ai_client=None):
        self._user(user_id)
        return interpret_preference_request(request, ai_client=ai_client or self.preference_ai_client)

    def confirm_interpreted_preferences(self, user_id, interpreted):
        self._user(user_id)
        if interpreted.get("confirmed") is not True:
            raise ValueError("interpreted preferences must be confirmed before saving")
        payload = interpreted.get("preferences")
        if not isinstance(payload, dict):
            raise ValueError("confirmed preferences are invalid")
        normalized, warnings = normalize_preferences(payload)
        if warnings or not (normalized["hard_exclusions"] or normalized["criteria"]):
            raise ValueError("confirmed preferences are invalid")
        return self.save_preferences(user_id, normalized)

    def explain_candidate(self, user_id, candidate_id) -> Dict[str, Any]:
        user = self._user(user_id)
        candidate = self._user(candidate_id)
        privacy = self.repository.get_privacy_settings(user_id)
        self.privacy_manager.update_settings(user_id, privacy)
        user_pers = self.repository.get_user_personality(user_id)
        cand_pers = self.repository.get_user_personality(candidate_id)
        p_enabled = bool(privacy.get("personalization_enabled", True))
        interactions = self.repository.get_interactions(user_id) if p_enabled else []
        interest_prof = None
        if p_enabled:
            raw_ext = self.repository.get_external_interests(user_id)
            consented_ext = [
                i for i in raw_ext
                if self.privacy_manager.get_external_interest_consent(user_id, i.get("provider", ""))
            ]
            if consented_ext or interactions:
                interest_prof = UserInterestProfile(self.recommender.config).fit(
                    user, interactions, self.repository.get_user, self.clock(),
                    external_interests=consented_ext if consented_ext else None,
                )
        return self.recommender.explain_candidate(
            user, candidate,
            user_preferences=self.repository.get_user_preferences(user_id),
            candidate_preferences=self.repository.get_user_preferences(candidate_id),
            user_personality=user_pers,
            candidate_personality=cand_pers,
            interest_profile=interest_prof,
            privacy_settings=privacy,
            interactions=interactions,
            profile_lookup=self.repository.get_user,
            now=self.clock(),
        )

    def import_external_interests(
        self,
        user_id: Any,
        provider: str,
        payload: Dict[str, Any],
        provider_instance: Optional[ExternalInterestProvider] = None,
        user_confirmed: bool = False,
    ) -> Dict[str, Any]:
        self._user(user_id)
        p_name = str(provider).lower()
        prov = provider_instance or self.mock_providers.get(p_name)
        if prov is None:
            raise ValueError(f"unsupported external provider '{provider}'; available: {list(self.mock_providers.keys())}")
        extracted = prov.extract_interests(user_id, payload)
        from dataclasses import replace
        if user_confirmed:
            extracted.interests = [replace(i, user_confirmed=True) for i in extracted.interests]
        items_dict = [i.to_dict() for i in extracted.interests]
        saved = self.repository.save_external_interests(user_id, p_name, items_dict)
        return {
            "user_id": str(user_id),
            "provider": p_name,
            "imported_count": len(items_dict),
            "interests": items_dict,
            "warnings": extracted.warnings,
            "total_stored": saved.get("total_external_interests", len(items_dict)),
        }

    def get_external_interests(self, user_id: Any, provider: Optional[str] = None) -> Dict[str, Any]:
        self._user(user_id)
        items = self.repository.get_external_interests(user_id, provider=provider)
        return {
            "user_id": str(user_id),
            "provider": provider.lower() if provider else None,
            "count": len(items),
            "interests": items,
        }

    def delete_external_interests(self, user_id: Any, provider: Optional[str] = None) -> Dict[str, Any]:
        self._user(user_id)
        deleted = self.repository.delete_external_interests(user_id, provider=provider)
        return {
            "user_id": str(user_id),
            "provider": provider.lower() if provider else "all",
            "deleted_count": deleted,
            "success": True,
        }

    def set_external_interest_consent(self, user_id: Any, provider: str, consent: bool) -> Dict[str, Any]:
        self._user(user_id)
        updated = self.privacy_manager.set_external_interest_consent(user_id, provider, consent)
        self.repository.save_privacy_settings(user_id, updated)
        return {
            "user_id": str(user_id),
            "provider": str(provider).lower(),
            "consent": bool(consent),
            "privacy_settings": updated,
        }

    def get_external_accounts(self, user_id: Any) -> Dict[str, Any]:
        self._user(user_id)
        accounts = self.repository.get_external_accounts(user_id)
        settings = self.repository.get_privacy_settings(user_id)
        consent_map = settings.get("external_interests_consent") or {}
        for acct in accounts:
            p = acct.get("provider", "")
            acct["consent_active"] = bool(consent_map.get(p, False))
        return {
            "user_id": str(user_id),
            "accounts": accounts,
        }

    def add_manual_interest(self, user_id: Any, name: str, category: Optional[str] = None, user_confirmed: bool = True) -> Dict[str, Any]:
        self._user(user_id)
        norm_item = validate_and_normalize_manual_interest(name, category=category, user_confirmed=user_confirmed)
        current = self.repository.get_external_interests(user_id, provider="manual_entry")

        existing_idx = next((idx for idx, i in enumerate(current) if i.get("canonical_token") == norm_item.canonical_token), None)
        if existing_idx is not None:
            current[existing_idx] = norm_item.to_dict()
            is_new = False
        else:
            if len(current) >= MAX_MANUAL_INTERESTS_PER_USER:
                raise ValueError(f"Cannot add interest: user reached limit of {MAX_MANUAL_INTERESTS_PER_USER} manual interests")
            current.append(norm_item.to_dict())
            is_new = True

        self.repository.save_external_interests(user_id, "manual_entry", current)

        # Ensure manual_entry consent is active unless user explicitly opted out
        privacy = self.repository.get_privacy_settings(user_id)
        ext_consent = dict(privacy.get("external_interests_consent") or {})
        if "manual_entry" not in ext_consent:
            ext_consent["manual_entry"] = True
            self.privacy_manager.set_external_interest_consent(user_id, "manual_entry", True)
            self.repository.save_privacy_settings(user_id, {"external_interests_consent": ext_consent})

        return {
            "user_id": str(user_id),
            "interest": norm_item.to_dict(),
            "total_manual_interests": len(current),
            "is_new": is_new,
        }

    def add_manual_interests(self, user_id: Any, interests: List[Any]) -> Dict[str, Any]:
        self._user(user_id)
        if not isinstance(interests, (list, tuple)):
            raise TypeError("interests must be a list")
        if len(interests) > MAX_MANUAL_INTERESTS_PER_USER:
            raise ValueError(f"Cannot add more than {MAX_MANUAL_INTERESTS_PER_USER} interests at once")

        current = self.repository.get_external_interests(user_id, provider="manual_entry")
        by_token = {i.get("canonical_token"): i for i in current}
        added = []

        for item in interests:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("display_name")
                cat = item.get("category")
                conf = item.get("user_confirmed", True)
            else:
                name = item
                cat = None
                conf = True

            norm_item = validate_and_normalize_manual_interest(name, category=cat, user_confirmed=conf)
            tok = norm_item.canonical_token
            if tok not in by_token and (len(by_token) >= MAX_MANUAL_INTERESTS_PER_USER):
                raise ValueError(f"Adding interests exceeds maximum limit of {MAX_MANUAL_INTERESTS_PER_USER} manual interests per user")
            by_token[tok] = norm_item.to_dict()
            added.append(norm_item.to_dict())

        all_items = list(by_token.values())
        self.repository.save_external_interests(user_id, "manual_entry", all_items)

        privacy = self.repository.get_privacy_settings(user_id)
        ext_consent = dict(privacy.get("external_interests_consent") or {})
        if "manual_entry" not in ext_consent:
            ext_consent["manual_entry"] = True
            self.privacy_manager.set_external_interest_consent(user_id, "manual_entry", True)
            self.repository.save_privacy_settings(user_id, {"external_interests_consent": ext_consent})

        return {
            "user_id": str(user_id),
            "added_count": len(added),
            "total_manual_interests": len(all_items),
            "interests": all_items,
        }

    def get_manual_interests(self, user_id: Any) -> List[Dict[str, Any]]:
        self._user(user_id)
        return self.repository.get_external_interests(user_id, provider="manual_entry")

    def remove_manual_interest(self, user_id: Any, token_or_name: str) -> Dict[str, Any]:
        self._user(user_id)
        raw = str(token_or_name).strip()
        if raw.startswith("interest_tag:"):
            tok = raw
        else:
            norm = normalize_interest_tag(raw)
            if not norm:
                raise ValueError("Invalid interest tag or name")
            tok = f"interest_tag:{norm}"
        deleted = self.repository.remove_external_interest(user_id, tok, provider="manual_entry")
        return {
            "user_id": str(user_id),
            "canonical_token": tok,
            "removed": deleted > 0,
            "deleted_count": deleted,
        }

    def delete_manual_interests(self, user_id: Any) -> Dict[str, Any]:
        self._user(user_id)
        deleted = self.repository.delete_external_interests(user_id, provider="manual_entry")
        return {
            "user_id": str(user_id),
            "provider": "manual_entry",
            "deleted_count": deleted,
            "success": True,
        }

    def confirm_interest(self, user_id: Any, token_or_name: str, confirmed: bool = True) -> Dict[str, Any]:
        self._user(user_id)
        raw = str(token_or_name).strip()
        if raw.startswith("interest_tag:"):
            tok = raw
        else:
            norm = normalize_interest_tag(raw)
            if not norm:
                raise ValueError("Invalid interest tag or name")
            tok = f"interest_tag:{norm}"
        updated = self.repository.update_external_interest(user_id, tok, {"user_confirmed": bool(confirmed)})
        if updated is None:
            raise KeyError(f"Interest token '{tok}' not found for user '{user_id}'")
        return {
            "user_id": str(user_id),
            "canonical_token": tok,
            "user_confirmed": bool(confirmed),
            "interest": updated,
        }

    def set_manual_interest_consent(self, user_id: Any, consent: bool) -> Dict[str, Any]:
        return self.set_external_interest_consent(user_id, "manual_entry", consent)

    def get_manual_interest_consent(self, user_id: Any) -> bool:
        self._user(user_id)
        privacy = self.repository.get_privacy_settings(user_id)
        self.privacy_manager.update_settings(user_id, privacy)
        return self.privacy_manager.get_external_interest_consent(user_id, "manual_entry")

    def explain_pair(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any],
                     preferences_a: Optional[Dict[str, Any]] = None,
                     preferences_b: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        id_a, id_b = profile_a.get("id"), profile_b.get("id")
        prefs_a = preferences_a or profile_a.get("preferences") or profile_a.get("user_preferences")
        if prefs_a is None and id_a is not None:
            prefs_a = self.repository.get_user_preferences(id_a)
        prefs_b = preferences_b or profile_b.get("preferences") or profile_b.get("user_preferences")
        if prefs_b is None and id_b is not None:
            prefs_b = self.repository.get_user_preferences(id_b)
        return self.recommender.explain_candidate(
            profile_a, profile_b,
            user_preferences=prefs_a,
            candidate_preferences=prefs_b,
            profile_lookup=self.repository.get_user,
            now=self.clock(),
        )


def _service_explain_pair(self, profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> Dict[str, Any]:
    return self.model.explain_pair(profile_a, profile_b)


MatchingService.explain_pair = _service_explain_pair

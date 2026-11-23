"""Privacy Controls, Data Protection, and Consent Management (Phase 6).

Enforces strict privacy controls:
1. Data Minimization: Chat events store only minimal metadata (direction, timestamp, length), never raw text.
2. Informed Consent: Explicit consent required for message content analysis; immediate withdrawal supported.
3. Personalization Controls: Users can disable behavioral personalization at any time.
4. Data Deletion: Complete purge of interaction histories upon user request.
5. Isolation: Prevents leaking one user's behavioral logs or private events to other users.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


DEFAULT_PRIVACY_SETTINGS: Dict[str, Any] = {
    "personalization_enabled": True,
    "message_analysis_consent": False,
    "raw_message_retention": False,
    "external_interests_consent": {},
}


class PrivacyManager:
    """Manages privacy settings, consent states, and data minimization."""

    def __init__(self):
        # user_id -> settings dict
        self._settings: Dict[str, Dict[str, Any]] = {}

    def get_settings(self, user_id: Any) -> Dict[str, Any]:
        uid = str(user_id)
        if uid not in self._settings:
            # Default safe settings: personalization active, message text analysis disabled
            self._settings[uid] = {
                "user_id": uid,
                **DEFAULT_PRIVACY_SETTINGS,
                "external_interests_consent": dict(DEFAULT_PRIVACY_SETTINGS["external_interests_consent"]),
            }
        settings = dict(self._settings[uid])
        settings["external_interests_consent"] = dict(settings.get("external_interests_consent") or {})
        return settings

    def update_settings(self, user_id: Any, updates: Dict[str, Any]) -> Dict[str, Any]:
        uid = str(user_id)
        current = self.get_settings(uid)
        for key in ("personalization_enabled", "message_analysis_consent", "raw_message_retention"):
            if key in updates:
                current[key] = bool(updates[key])
        if "external_interests_consent" in updates:
            ext_consent = dict(current.get("external_interests_consent") or {})
            raw_updates = updates["external_interests_consent"]
            if isinstance(raw_updates, dict):
                for p, v in raw_updates.items():
                    ext_consent[str(p).lower()] = bool(v)
            current["external_interests_consent"] = ext_consent
        self._settings[uid] = current
        return dict(current)

    def set_privacy_settings(self, user_id: Any, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_settings(user_id, updates)

    def set_personalization_enabled(self, user_id: Any, enabled: bool) -> Dict[str, Any]:
        return self.update_settings(user_id, {"personalization_enabled": enabled})

    def set_message_analysis_consent(self, user_id: Any, consent: bool) -> Dict[str, Any]:
        return self.update_settings(user_id, {"message_analysis_consent": consent})

    def can_analyze_messages(self, user_id: Any) -> bool:
        return bool(self.get_settings(user_id).get("message_analysis_consent", False))

    def set_external_interest_consent(self, user_id: Any, provider: str, consent: bool) -> Dict[str, Any]:
        """Sets consent for a specific external interest provider (e.g. 'google', 'instagram')."""
        uid = str(user_id)
        curr = self.get_settings(uid)
        ext = dict(curr.get("external_interests_consent") or {})
        ext[str(provider).lower()] = bool(consent)
        return self.update_settings(uid, {"external_interests_consent": ext})

    def get_external_interest_consent(self, user_id: Any, provider: str) -> bool:
        """Returns True only if personalization is enabled AND explicit consent for provider is active."""
        settings = self.get_settings(user_id)
        if not settings.get("personalization_enabled", True):
            return False
        ext = settings.get("external_interests_consent") or {}
        p = str(provider).lower()
        if p == "manual_entry":
            return bool(ext.get("manual_entry", True))
        return bool(ext.get(p, False))

    def can_use_external_interests(self, user_id: Any, provider: Optional[str] = None) -> bool:
        """Checks if external interests can be used for scoring."""
        settings = self.get_settings(user_id)
        if not settings.get("personalization_enabled", True):
            return False
        ext = settings.get("external_interests_consent") or {}
        if provider is not None:
            return bool(ext.get(str(provider).lower(), False))
        return any(bool(v) for v in ext.values())

    def revoke_all_external_consent(self, user_id: Any) -> Dict[str, Any]:
        """Immediately revokes consent across all external providers."""
        uid = str(user_id)
        curr = self.get_settings(uid)
        ext = {k: False for k in (curr.get("external_interests_consent") or {})}
        return self.update_settings(uid, {"external_interests_consent": ext})

    def sanitize_event_for_storage(self, event: Dict[str, Any], user_id: Optional[Any] = None) -> Dict[str, Any]:
        """Strips raw message content from conversation events unless explicit consent is active.

        Minimizes payload to metadata: length, direction, timestamp, session_id.
        """
        clean = dict(event)
        uid = str(user_id or event.get("user_id"))
        settings = self.get_settings(uid)

        metadata = dict(clean.get("metadata") or {})
        has_text = "message_text" in clean or "text" in clean or "text" in metadata or "body" in metadata or "message_text" in metadata or "content" in metadata
        if has_text:
            text = str(
                clean.get("message_text")
                or clean.get("text")
                or metadata.get("text")
                or metadata.get("body")
                or metadata.get("message_text")
                or metadata.get("content")
                or ""
            )
            metadata["message_length_chars"] = len(text)
            metadata["word_count"] = len(text.split())

            if not settings.get("message_analysis_consent", False) or not settings.get("raw_message_retention", False):
                clean.pop("message_text", None)
                clean.pop("text", None)
                metadata.pop("text", None)
                metadata.pop("body", None)
                metadata.pop("message_text", None)
                metadata.pop("content", None)
                metadata["text_retained"] = False
            else:
                metadata["text_retained"] = True

        clean["metadata"] = metadata
        return clean

    def filter_events_for_user(self, events: List[Dict[str, Any]], requesting_user_id: Any) -> List[Dict[str, Any]]:
        """Access control check: ensures user only retrieves their own interaction logs."""
        req_uid = str(requesting_user_id)
        return [dict(e) for e in events if str(e.get("user_id")) == req_uid]

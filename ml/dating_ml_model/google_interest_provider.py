"""Stable Google-interest provider interface for the Dating ML V3 model (Phase 2).

IMPORTANT — PRODUCTION SCOPE STATEMENT
---------------------------------------
This module defines the INTERFACE CONTRACT between the backend team's
Google/YouTube OAuth import service and the Dating ML V3 matching model.

The backend team is responsible for:
  - Obtaining and managing Google OAuth 2.0 tokens
    (scope: https://www.googleapis.com/auth/youtube.readonly)
  - Calling the YouTube Data API v3 (Topics, Subscriptions, or related endpoints)
  - Converting raw API responses to the StandardizedGooglePayload format defined here
  - Supplying the payload to StandardizedGoogleInterestProvider.extract_interests()

This module does NOT:
  - Store or handle any OAuth tokens
  - Make any network calls to Google APIs
  - Require internet access at runtime

MockGoogleInterestProvider in external_interests.py remains the correct
provider for automated tests and offline development.

Usage example (backend integration):
    from dating_ml_model.google_interest_provider import (
        StandardizedGoogleInterestProvider,
        validate_google_payload,
    )

    # Backend prepares the payload from their YouTube API response
    validated_payload = validate_google_payload(raw_payload_from_backend)
    provider = StandardizedGoogleInterestProvider()
    result = provider.extract_interests(user_id, validated_payload)

    # result is an ExternalInterestPayload ready for repository storage
    service.import_external_interests(
        user_id=user_id,
        provider="google",
        payload=validated_payload,
        provider_instance=provider,
        user_confirmed=False,  # show to user for confirmation first
    )
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .external_interests import (
    ExternalInterestPayload,
    ExternalInterestProvider,
    NormalizedInterest,
    _utcnow_iso,
    infer_interest_category,
    normalize_interest_tag,
)

# ---------------------------------------------------------------------------
# Payload schema constants
# ---------------------------------------------------------------------------

# Maximum number of interest items accepted per payload call.
# Prevents unbounded memory use from misconfigured backends.
MAX_ITEMS_PER_PAYLOAD = 200

# Minimum confidence threshold: items below this are accepted but flagged.
MIN_CONFIDENCE_WARN_THRESHOLD = 0.50

# Maximum age of imported data in days before a freshness warning is issued.
# The model does not reject stale data; stale is a signal quality concern.
MAX_FRESHNESS_DAYS = 90

# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


class GooglePayloadValidationError(ValueError):
    """Raised when the backend-supplied Google payload fails schema validation."""


def validate_google_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validates a backend-supplied Google interest payload before model processing.

    Parameters
    ----------
    payload : dict
        Must conform to StandardizedGooglePayload shape (see below).

    Returns
    -------
    dict
        The same payload dict, augmented with a ``_validation_warnings`` key
        listing non-fatal issues (low confidence, staleness, etc.).

    Raises
    ------
    GooglePayloadValidationError
        If the payload is structurally invalid (missing required keys,
        wrong types, items list not a list, etc.).

    StandardizedGooglePayload shape
    --------------------------------
    {
      # Required
      "account_id_hash": str,          # SHA-256 hex of the user's Google account ID
                                        # (must be pseudonymized by the backend before
                                        # passing to the model — never pass the raw ID)
      "items": [                        # list of interest items
        {
          # Required per item
          "topic_name": str,            # human-readable interest name (e.g. "Jazz Music")

          # Optional per item
          "topic_id": str,              # YouTube topic freebase ID (e.g. "/m/03_d0")
                                        # presence elevates base confidence to 0.85
          "category": str,             # pre-classified taxonomy category (see
                                        # VALID_INTEREST_CATEGORIES in external_interests.py)
          "confidence": float,          # [0.0, 1.0] — provider-assessed confidence
                                        # defaults to 0.85 if topic_id present, else 0.70
          "source_detail": str,        # e.g. "youtube_liked_video", "youtube_subscription"
          "user_confirmed": bool,       # True if the user explicitly confirmed this interest
        },
        ...
      ],

      # Optional but recommended
      "fetched_at": str,               # ISO-8601 UTC timestamp when the backend fetched
                                        # the data from Google (for freshness tracking)
      "api_version": str,              # e.g. "youtube/v3" — for audit/debugging
    }
    """
    if not isinstance(payload, dict):
        raise GooglePayloadValidationError("Payload must be a dict")

    # account_id_hash is required; raw Google account IDs must never be passed
    acct_hash = payload.get("account_id_hash")
    if not acct_hash or not isinstance(acct_hash, str):
        raise GooglePayloadValidationError(
            "payload['account_id_hash'] is required and must be a non-empty string. "
            "The backend must pseudonymize the Google account ID (e.g. SHA-256 hex) "
            "before passing it to the model. Never pass the raw Google account ID."
        )

    items = payload.get("items")
    if items is None:
        raise GooglePayloadValidationError("payload['items'] is required")
    if not isinstance(items, list):
        raise GooglePayloadValidationError("payload['items'] must be a list")

    warnings: List[str] = []

    if len(items) > MAX_ITEMS_PER_PAYLOAD:
        raise GooglePayloadValidationError(
            f"payload['items'] exceeds maximum of {MAX_ITEMS_PER_PAYLOAD} items"
        )

    # Validate each item
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise GooglePayloadValidationError(
                f"payload['items'][{idx}] must be a dict"
            )
        topic_name = item.get("topic_name") or item.get("title") or item.get("name")
        if not topic_name or not isinstance(topic_name, str) or not topic_name.strip():
            raise GooglePayloadValidationError(
                f"payload['items'][{idx}] missing required 'topic_name' string"
            )
        conf = item.get("confidence")
        if conf is not None:
            if not isinstance(conf, (int, float)):
                raise GooglePayloadValidationError(
                    f"payload['items'][{idx}]['confidence'] must be a number"
                )
            conf_f = float(conf)
            if not (0.0 <= conf_f <= 1.0):
                raise GooglePayloadValidationError(
                    f"payload['items'][{idx}]['confidence'] must be in [0.0, 1.0], got {conf_f}"
                )
            if conf_f < MIN_CONFIDENCE_WARN_THRESHOLD:
                warnings.append(
                    f"item[{idx}] '{topic_name}' has low confidence {conf_f:.2f} "
                    f"(below recommended threshold {MIN_CONFIDENCE_WARN_THRESHOLD})"
                )

    # Freshness check
    fetched_at = payload.get("fetched_at")
    if fetched_at:
        try:
            fetched_dt = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
            age_days = (
                datetime.now(timezone.utc) - fetched_dt.astimezone(timezone.utc)
            ).days
            if age_days > MAX_FRESHNESS_DAYS:
                warnings.append(
                    f"payload was fetched {age_days} days ago "
                    f"(older than recommended {MAX_FRESHNESS_DAYS} days)"
                )
        except (ValueError, TypeError):
            warnings.append("payload['fetched_at'] could not be parsed as an ISO-8601 datetime")

    # Return augmented payload (non-mutating copy with warnings appended)
    return {**payload, "_validation_warnings": warnings}


# ---------------------------------------------------------------------------
# Standardized provider
# ---------------------------------------------------------------------------


class StandardizedGoogleInterestProvider(ExternalInterestProvider):
    """Production-ready Google interest provider for the Dating ML V3 model.

    Accepts pre-authorized, pre-validated payloads from the backend team's
    Google OAuth import service. Makes NO network calls and requires NO
    credentials at runtime.

    The backend team must:
      1. Obtain YouTube Data API v3 authorization (OAuth 2.0).
      2. Call the API (Topics, Subscriptions, or related endpoints).
      3. Convert the raw API response to the StandardizedGooglePayload format.
      4. Pseudonymize the Google account ID (SHA-256) before passing to this class.
      5. Call validate_google_payload() to catch structural errors early.
      6. Pass the validated payload to extract_interests().

    This class is a drop-in replacement for MockGoogleInterestProvider in
    production; test code should continue to use MockGoogleInterestProvider.
    """

    @property
    def provider_id(self) -> str:
        return "google"

    @property
    def supported_scopes(self) -> List[str]:
        return [
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube-paid-content",
        ]

    def extract_interests(
        self,
        user_id: Any,
        payload: Dict[str, Any],
    ) -> ExternalInterestPayload:
        """Extract and normalize Google-derived interests from a validated payload.

        Parameters
        ----------
        user_id : Any
            The application's internal user identifier (NOT the Google account ID).
        payload : dict
            A payload dict that has already been through validate_google_payload().
            The ``account_id_hash`` field must be present.

        Returns
        -------
        ExternalInterestPayload
            Ready for storage via service.import_external_interests() or
            repository.save_external_interests().
        """
        uid = str(user_id)

        # Use the pre-pseudonymized hash supplied by the backend.
        # Never re-hash or attempt to recover the original account ID.
        acct_hash = str(payload.get("account_id_hash", ""))

        items: List[NormalizedInterest] = []
        warnings: List[str] = list(payload.get("_validation_warnings") or [])
        seen_tokens: set = set()
        now_iso = _utcnow_iso()

        raw_items = payload.get("items") or []

        for idx, item in enumerate(raw_items):
            if not isinstance(item, dict):
                warnings.append(f"item[{idx}] is not a dict; skipped")
                continue

            # Resolve topic name from multiple possible keys
            raw_name = (
                item.get("topic_name") or item.get("title") or item.get("name") or ""
            ).strip()
            if not raw_name:
                warnings.append(f"item[{idx}] has no topic name; skipped")
                continue

            tag = normalize_interest_tag(raw_name)
            if not tag:
                warnings.append(f"item[{idx}] '{raw_name}' produced an empty tag; skipped")
                continue

            canonical = f"interest_tag:{tag}"
            if canonical in seen_tokens:
                warnings.append(f"item[{idx}] '{raw_name}' is a duplicate; skipped")
                continue
            seen_tokens.add(canonical)

            # Confidence: topic_id presence → 0.85, channel/subscription → 0.70
            has_topic_id = bool(item.get("topic_id") or item.get("is_topic"))
            base_conf = 0.85 if has_topic_id else 0.70
            conf = float(item.get("confidence", base_conf))
            conf = max(0.0, min(1.0, conf))

            category = str(item.get("category") or infer_interest_category(tag))
            source = str(item.get("source_detail") or (
                "youtube_topic" if has_topic_id else "youtube_subscription"
            ))
            user_confirmed = bool(item.get("user_confirmed", False))

            items.append(
                NormalizedInterest(
                    canonical_token=canonical,
                    display_name=raw_name,
                    category=category,
                    provider=self.provider_id,
                    source_detail=source,
                    confidence=conf,
                    affinity=1.0,
                    user_confirmed=user_confirmed,
                    imported_at=now_iso,
                )
            )

        return ExternalInterestPayload(
            user_id=uid,
            provider=self.provider_id,
            external_account_id_hash=acct_hash,
            timestamp=now_iso,
            interests=items,
            raw_metadata={
                "item_count": len(raw_items),
                "accepted_count": len(items),
                "api_version": str(payload.get("api_version", "youtube/v3")),
                "fetched_at": payload.get("fetched_at"),
                "synthetic": False,
            },
            warnings=warnings,
        )

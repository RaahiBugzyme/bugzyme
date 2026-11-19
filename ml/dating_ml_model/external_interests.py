"""Provider-independent external interest personalization layer (Phase 1).

Defines:
- Normalized interest record schemas (`NormalizedInterest`, `ExternalInterestPayload`)
- Provider-independent abstract base interface (`ExternalInterestProvider`)
- Deterministic mock providers for Google and Instagram (synthetic data only, no live network calls or credentials)
- Normalization, validation, category inference, and synthetic fixture generators
"""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_interest_tag(raw: Any) -> Optional[str]:
    """Normalizes an arbitrary raw interest string into a clean canonical tag."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    # Strip leading hashtags or @ symbols
    text = re.sub(r"^[#@]+", "", text)
    # Replace whitespace and hyphens with underscores
    text = re.sub(r"[\s\-]+", "_", text)
    # Remove any characters other than lowercase ascii alphanumeric and underscores
    text = re.sub(r"[^a-z0-9_]", "", text)
    # Collapse consecutive underscores
    text = re.sub(r"_+", "_", text).strip("_")
    return text if text else None


# Deterministic category keyword maps for standardized taxonomy
_CATEGORY_KEYWORDS: Dict[str, Set[str]] = {
    "outdoors": {
        "hiking", "camping", "trekking", "backpacking", "trail_running", "mountaineering",
        "rock_climbing", "kayaking", "canoeing", "surfing", "skiing", "snowboarding",
        "nature", "wildlife", "national_parks", "gardening", "fishing",
    },
    "fitness": {
        "running", "marathon", "cycling", "weightlifting", "crossfit", "yoga", "pilates",
        "calisthenics", "swimming", "gym", "fitness", "triathlon", "boxing", "martial_arts",
    },
    "technology": {
        "programming", "python", "javascript", "machine_learning", "ai", "data_science",
        "open_source", "cybersecurity", "robotics", "gadgets", "web_development",
        "cloud_computing", "crypto", "electronics", "software_engineering", "technology",
    },
    "culinary": {
        "cooking", "baking", "specialty_coffee", "coffee", "wine", "craft_beer",
        "vegan_cooking", "gastronomy", "foodie", "mixology", "pastry", "bbq", "culinary",
    },
    "music": {
        "indie_rock", "jazz", "classical_music", "hip_hop", "electronic_music",
        "vinyl_records", "guitar", "piano", "live_concerts", "music_production",
        "folk_music", "blues", "metal", "r_and_b", "music",
    },
    "arts": {
        "photography", "photographer", "street_photography", "painting", "illustration", "pottery",
        "sculpture", "ceramics", "graphic_design", "architecture", "calligraphy", "arts",
    },
    "literature": {
        "reading", "bookstagram", "fiction", "sci_fi", "poetry", "philosophy",
        "creative_writing", "non_fiction", "history", "literature", "books",
    },
    "entertainment": {
        "indie_film", "cinema", "documentaries", "theatre", "standup_comedy",
        "podcasts", "anime", "board_games", "film", "movies",
    },
    "gaming": {
        "video_games", "pc_gaming", "rpg", "retro_gaming", "esports", "tabletop_games",
        "game_design", "gaming",
    },
    "sports": {
        "football", "soccer", "basketball", "tennis", "cricket", "badminton",
        "baseball", "volleyball", "rugby", "sports",
    },
}


def infer_interest_category(tag: str) -> str:
    """Classifies a normalized tag into a standard taxonomy category."""
    norm = normalize_interest_tag(tag)
    if not norm:
        return "general"
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if norm in keywords:
            return cat
        for kw in keywords:
            if kw in norm or norm in kw:
                return cat
    return "general"


VALID_INTEREST_CATEGORIES: Tuple[str, ...] = (
    "outdoors",
    "fitness",
    "technology",
    "culinary",
    "music",
    "arts",
    "literature",
    "entertainment",
    "gaming",
    "sports",
    "general",
)

MAX_MANUAL_INTERESTS_PER_USER = 50
MAX_INTEREST_NAME_LENGTH = 100


def validate_and_normalize_manual_interest(
    name: Any,
    category: Optional[str] = None,
    user_confirmed: bool = True,
) -> NormalizedInterest:
    """Validates, sanitizes, and maps user-entered interest input into a NormalizedInterest."""
    if name is None:
        raise ValueError("Interest name cannot be empty or None")
    text = str(name).strip()
    if not text:
        raise ValueError("Interest name cannot be empty or whitespace")
    if len(text) > MAX_INTEREST_NAME_LENGTH:
        raise ValueError(f"Interest name exceeds maximum length of {MAX_INTEREST_NAME_LENGTH} characters")

    norm_tag = normalize_interest_tag(text)
    if not norm_tag:
        raise ValueError(f"Interest name '{text}' does not contain any valid alphanumeric characters")

    # Validate or infer category
    if category is not None:
        cat_clean = str(category).strip().lower()
        if cat_clean not in VALID_INTEREST_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Valid categories: {', '.join(VALID_INTEREST_CATEGORIES)}"
            )
        final_cat = cat_clean
    else:
        final_cat = infer_interest_category(norm_tag)

    clean_display = text if len(text) <= 50 else norm_tag.replace("_", " ").title()

    return NormalizedInterest(
        canonical_token=f"interest_tag:{norm_tag}",
        display_name=clean_display,
        category=final_cat,
        provider="manual_entry",
        source_detail="user_selected",
        confidence=1.0,
        affinity=1.0,
        user_confirmed=bool(user_confirmed),
        imported_at=_utcnow_iso(),
    )


@dataclass(frozen=True)
class NormalizedInterest:
    """A single canonical interest item imported from an external provider."""
    canonical_token: str
    display_name: str
    category: str
    provider: str
    source_detail: str
    confidence: float
    affinity: float = 1.0
    user_confirmed: bool = False
    imported_at: Optional[str] = None

    def __post_init__(self):
        # Validation and bounds clamping
        if not self.canonical_token:
            raise ValueError("canonical_token cannot be empty")
        if not self.provider:
            raise ValueError("provider cannot be empty")
        clamped_conf = max(0.0, min(1.0, float(self.confidence)))
        clamped_aff = max(0.0, min(1.0, float(self.affinity)))
        object.__setattr__(self, "confidence", round(clamped_conf, 4))
        object.__setattr__(self, "affinity", round(clamped_aff, 4))
        if self.imported_at is None:
            object.__setattr__(self, "imported_at", _utcnow_iso())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NormalizedInterest":
        return cls(
            canonical_token=str(data["canonical_token"]),
            display_name=str(data.get("display_name", data["canonical_token"])),
            category=str(data.get("category", "general")),
            provider=str(data["provider"]).lower(),
            source_detail=str(data.get("source_detail", "unknown")),
            confidence=float(data.get("confidence", 0.7)),
            affinity=float(data.get("affinity", 1.0)),
            user_confirmed=bool(data.get("user_confirmed", False)),
            imported_at=data.get("imported_at"),
        )


@dataclass
class ExternalInterestPayload:
    """Container for imported external interests for one user and provider."""
    user_id: str
    provider: str
    external_account_id_hash: str
    timestamp: str
    interests: List[NormalizedInterest] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "provider": self.provider,
            "external_account_id_hash": self.external_account_id_hash,
            "timestamp": self.timestamp,
            "interests": [i.to_dict() for i in self.interests],
            "raw_metadata": dict(self.raw_metadata),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExternalInterestPayload":
        interests = [NormalizedInterest.from_dict(i) for i in data.get("interests", [])]
        return cls(
            user_id=str(data["user_id"]),
            provider=str(data["provider"]).lower(),
            external_account_id_hash=str(data.get("external_account_id_hash", "")),
            timestamp=str(data.get("timestamp", _utcnow_iso())),
            interests=interests,
            raw_metadata=dict(data.get("raw_metadata") or {}),
            warnings=list(data.get("warnings") or []),
        )


class ExternalInterestProvider(ABC):
    """Abstract provider interface for importing external interests."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g. 'google', 'instagram')."""
        ...

    @property
    @abstractmethod
    def supported_scopes(self) -> List[str]:
        """List of official OAuth scopes simulated or required."""
        ...

    @abstractmethod
    def extract_interests(self, user_id: Any, payload: Dict[str, Any]) -> ExternalInterestPayload:
        """Extracts and normalizes interest records from provider-specific synthetic payload."""
        ...


class MockGoogleInterestProvider(ExternalInterestProvider):
    """Deterministic mock provider simulating Google/YouTube data imports.

    Accepts synthetic YouTube topic categories and subscriptions,
    emitting normalized interests with provenance and confidence scores.
    Makes NO network calls and requires NO OAuth credentials.
    """

    @property
    def provider_id(self) -> str:
        return "google"

    @property
    def supported_scopes(self) -> List[str]:
        return ["https://www.googleapis.com/auth/youtube.readonly"]

    def extract_interests(self, user_id: Any, payload: Dict[str, Any]) -> ExternalInterestPayload:
        uid = str(user_id)
        raw_account_id = str(payload.get("account_id") or payload.get("channel_id") or f"google_{uid}")
        # Always pseudonymize account ID
        acct_hash = hashlib.sha256(raw_account_id.encode("utf-8")).hexdigest()[:16]

        interests: List[NormalizedInterest] = []
        warnings: List[str] = []
        seen_tokens: Set[str] = set()

        items = payload.get("items") or payload.get("subscriptions") or []
        if not isinstance(items, list):
            warnings.append("payload items must be a list")
            items = []

        now_iso = _utcnow_iso()

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            raw_name = item.get("topic_name") or item.get("title") or item.get("name")
            if not raw_name:
                warnings.append(f"item {idx} skipped: missing topic/title")
                continue

            tag = normalize_interest_tag(raw_name)
            if not tag:
                continue

            canonical = f"interest_tag:{tag}"
            if canonical in seen_tokens:
                continue
            seen_tokens.add(canonical)

            category = str(item.get("category") or infer_interest_category(tag))
            # Direct YouTube topic categories have higher confidence (0.85) than inferred channel titles (0.70)
            base_conf = 0.85 if item.get("topic_id") or item.get("is_topic") else 0.70
            conf = float(item.get("confidence", base_conf))
            user_confirmed = bool(item.get("user_confirmed", False))

            interests.append(
                NormalizedInterest(
                    canonical_token=canonical,
                    display_name=str(raw_name).strip(),
                    category=category,
                    provider=self.provider_id,
                    source_detail=str(item.get("source_detail") or "youtube_subscription"),
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
            interests=interests,
            raw_metadata={"item_count": len(items), "synthetic": True},
            warnings=warnings,
        )


class MockInstagramInterestProvider(ExternalInterestProvider):
    """Deterministic mock provider simulating Instagram public metadata imports.

    Accepts synthetic bio hashtags, creator account categories, and public interest tags.
    Makes NO network calls and requires NO OAuth credentials.
    """

    @property
    def provider_id(self) -> str:
        return "instagram"

    @property
    def supported_scopes(self) -> List[str]:
        return ["instagram_basic", "instagram_manage_insights"]

    def extract_interests(self, user_id: Any, payload: Dict[str, Any]) -> ExternalInterestPayload:
        uid = str(user_id)
        raw_account_id = str(payload.get("instagram_user_id") or payload.get("username") or f"ig_{uid}")
        acct_hash = hashlib.sha256(raw_account_id.encode("utf-8")).hexdigest()[:16]

        interests: List[NormalizedInterest] = []
        warnings: List[str] = []
        seen_tokens: Set[str] = set()
        now_iso = _utcnow_iso()

        meta = payload.get("profile_metadata") or {}

        # 1. Creator category if present
        creator_category = meta.get("category") or payload.get("category")
        if creator_category:
            tag = normalize_interest_tag(creator_category)
            if tag:
                canonical = f"interest_tag:{tag}"
                seen_tokens.add(canonical)
                interests.append(
                    NormalizedInterest(
                        canonical_token=canonical,
                        display_name=str(creator_category).strip(),
                        category=infer_interest_category(tag),
                        provider=self.provider_id,
                        source_detail="instagram_creator_category",
                        confidence=0.85,
                        affinity=1.0,
                        user_confirmed=bool(payload.get("user_confirmed", False)),
                        imported_at=now_iso,
                    )
                )

        # 2. Bio hashtags
        tags = meta.get("bio_hashtags") or payload.get("bio_hashtags") or payload.get("hashtags") or []
        if isinstance(tags, (list, tuple, set)):
            for raw_tag in tags:
                tag = normalize_interest_tag(raw_tag)
                if not tag:
                    continue
                canonical = f"interest_tag:{tag}"
                if canonical in seen_tokens:
                    continue
                seen_tokens.add(canonical)
                interests.append(
                    NormalizedInterest(
                        canonical_token=canonical,
                        display_name=f"#{tag}",
                        category=infer_interest_category(tag),
                        provider=self.provider_id,
                        source_detail="instagram_bio_hashtag",
                        confidence=0.80,
                        affinity=1.0,
                        user_confirmed=bool(payload.get("user_confirmed", False)),
                        imported_at=now_iso,
                    )
                )

        # 3. Explicit media tags or interest topics
        media_tags = meta.get("media_topics") or payload.get("media_topics") or []
        if isinstance(media_tags, (list, tuple, set)):
            for raw_item in media_tags:
                tag = normalize_interest_tag(raw_item)
                if not tag:
                    continue
                canonical = f"interest_tag:{tag}"
                if canonical in seen_tokens:
                    continue
                seen_tokens.add(canonical)
                interests.append(
                    NormalizedInterest(
                        canonical_token=canonical,
                        display_name=str(raw_item).strip(),
                        category=infer_interest_category(tag),
                        provider=self.provider_id,
                        source_detail="instagram_media_topic",
                        confidence=0.70,
                        affinity=1.0,
                        user_confirmed=bool(payload.get("user_confirmed", False)),
                        imported_at=now_iso,
                    )
                )

        return ExternalInterestPayload(
            user_id=uid,
            provider=self.provider_id,
            external_account_id_hash=acct_hash,
            timestamp=now_iso,
            interests=interests,
            raw_metadata={"synthetic": True, "account_type": meta.get("account_type", "PERSONAL")},
            warnings=warnings,
        )


# Synthetic data fixtures for offline development, tests, and demos
SYNTHETIC_GOOGLE_PERSONAS: Dict[str, Dict[str, Any]] = {
    "outdoors_tech": {
        "account_id": "google_user_alpha",
        "items": [
            {"title": "Rock Climbing", "topic_id": "/m/02mscn", "is_topic": True, "confidence": 0.90},
            {"title": "Hiking and Camping", "topic_id": "/m/019_rr", "is_topic": True, "confidence": 0.90},
            {"title": "Machine Learning", "topic_id": "/m/01hyh_", "is_topic": True, "confidence": 0.85},
            {"title": "Specialty Coffee", "topic_name": "specialty_coffee", "is_topic": False, "confidence": 0.75},
        ],
    },
    "music_cinema": {
        "account_id": "google_user_beta",
        "items": [
            {"title": "Jazz Music", "topic_id": "/m/03_d0", "is_topic": True, "confidence": 0.90},
            {"title": "Indie Film", "topic_name": "indie_film", "is_topic": True, "confidence": 0.85},
            {"title": "Classical Music", "topic_id": "/m/0ggq0m", "is_topic": True, "confidence": 0.85},
            {"title": "Vinyl Records", "topic_name": "vinyl_records", "is_topic": False, "confidence": 0.70},
        ],
    },
}

SYNTHETIC_INSTAGRAM_PERSONAS: Dict[str, Dict[str, Any]] = {
    "arts_culinary": {
        "username": "creator_artist_gamma",
        "profile_metadata": {
            "account_type": "CREATOR",
            "category": "Photographer",
            "bio_hashtags": ["#streetphotography", "#pottery", "#specialtycoffee", "#indiefilm"],
            "media_topics": ["architecture", "ceramics"],
        },
    },
    "fitness_outdoors": {
        "username": "runner_delta",
        "profile_metadata": {
            "account_type": "PERSONAL",
            "bio_hashtags": ["#trailrunning", "#marathon", "#hiking", "#plantbased"],
            "media_topics": ["rock_climbing", "vegan_cooking"],
        },
    },
}


def generate_synthetic_google_data(persona: str = "outdoors_tech") -> Dict[str, Any]:
    """Generates a synthetic Google payload fixture for a given persona."""
    return dict(SYNTHETIC_GOOGLE_PERSONAS.get(persona, SYNTHETIC_GOOGLE_PERSONAS["outdoors_tech"]))


def generate_synthetic_instagram_data(persona: str = "arts_culinary") -> Dict[str, Any]:
    """Generates a synthetic Instagram payload fixture for a given persona."""
    return dict(SYNTHETIC_INSTAGRAM_PERSONAS.get(persona, SYNTHETIC_INSTAGRAM_PERSONAS["arts_culinary"]))

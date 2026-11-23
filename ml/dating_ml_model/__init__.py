from .model import CompatibilityModel, RecommendationModel
from .compatibility_engine import CompatibilityEngine
from .search_intent import SearchIntentModel, learn_search_intent
from .explainability import explain_recommendation
from .interests import UserInterestProfile
from .personality import evaluate_personality_compatibility, normalize_personality_profile
from .privacy import PrivacyManager
from .evaluation import PersonalizationEvaluationHarness, compute_ranking_metrics_for_user

from .external_interests import (
    NormalizedInterest,
    ExternalInterestPayload,
    ExternalInterestProvider,
    MockGoogleInterestProvider,
    MockInstagramInterestProvider,
    validate_and_normalize_manual_interest,
    VALID_INTEREST_CATEGORIES,
)

from .preference_interpreter import (
    interpret_preference_request,
    interpret_extended_preference_request,
    GeminiPreferenceClient,
    GeminiProviderUnavailable,
)
from .google_interest_provider import (
    StandardizedGoogleInterestProvider,
    validate_google_payload,
    GooglePayloadValidationError,
)

__all__ = [
    "CompatibilityModel",
    "CompatibilityEngine",
    "RecommendationModel",
    "SearchIntentModel",
    "learn_search_intent",
    "explain_recommendation",
    "UserInterestProfile",
    "evaluate_personality_compatibility",
    "normalize_personality_profile",
    "PrivacyManager",
    "PersonalizationEvaluationHarness",
    "compute_ranking_metrics_for_user",
    "NormalizedInterest",
    "ExternalInterestPayload",
    "ExternalInterestProvider",
    "MockGoogleInterestProvider",
    "MockInstagramInterestProvider",
    "validate_and_normalize_manual_interest",
    "VALID_INTEREST_CATEGORIES",
    "interpret_preference_request",
    "interpret_extended_preference_request",
    "GeminiPreferenceClient",
    "GeminiProviderUnavailable",
    "StandardizedGoogleInterestProvider",
    "validate_google_payload",
    "GooglePayloadValidationError",
]
__version__ = "2.2.0"


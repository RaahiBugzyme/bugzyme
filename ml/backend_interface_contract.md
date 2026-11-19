# Dating ML V3 — Backend Interface Contract & Integration Specification

> **Document Version:** 3.0.0  
> **Package:** `dating_ml_model`  
> **Status:** APPROVED & VERIFIED (465 tests passing)  
> **Target Audience:** Backend Engineers, Platform Engineers, ML Engineers

---

## 1. Architectural Scope & Boundary Statement

This contract governs the integration between the application's backend services (HeartMatch Backend) and the **Dating ML V3 Model Package** (`dating_ml_model`).

### Strict Boundary Rules
1. **No Outbound Network Calls from ML Core:** The ML package contains zero HTTP clients to Google, YouTube, or external providers. All network requests (OAuth exchanges, API queries, rate-limit retries) must happen inside backend services before invoking the ML package.
2. **Credential Isolation:** Client credentials, OAuth refresh tokens, and service keys must **never** be passed into the ML package. Only pre-pseudonymized payload dictionaries are accepted.
3. **Deterministic & Testable:** Offline development and unit tests use deterministic mock providers (`MockGoogleInterestProvider`, `MockInstagramInterestProvider`). The production-ready interface is `StandardizedGoogleInterestProvider`.

---

## 2. Google-Derived Interest Integration Contract

### 2.1 Backend Responsibilities
The backend service must:
- Manage Google OAuth 2.0 authorization under scope:
  `https://www.googleapis.com/auth/youtube.readonly`
- Fetch YouTube topic categories or subscriptions on behalf of the user.
- Pseudonymize the user's Google Account ID using SHA-256 (first 16 hex chars or standard hex).
- Format the response into the standardized payload schema below.
- Pass the payload to `validate_google_payload(payload)` before invoking `service.import_external_interests()`.

### 2.2 Payload Schema (`StandardizedGooglePayload`)

```json
{
  "account_id_hash": "a1b2c3d4e5f60718",
  "fetched_at": "2026-10-30T10:00:00Z",
  "api_version": "youtube/v3",
  "items": [
    {
      "topic_name": "Jazz Music",
      "topic_id": "/m/03_d0",
      "category": "music",
      "confidence": 0.90,
      "source_detail": "youtube_subscription",
      "user_confirmed": false
    },
    {
      "topic_name": "Rock Climbing",
      "topic_id": "/m/02mscn",
      "category": "outdoors",
      "confidence": 0.85,
      "source_detail": "youtube_liked_topic",
      "user_confirmed": false
    }
  ]
}
```

#### Field Specifications:
- `account_id_hash` (*string, required*): SHA-256 hash of the Google account ID. Raw IDs are strictly rejected.
- `items` (*array of objects, required*): Max 200 items per payload.
  - `topic_name` (*string, required*): Non-empty human-readable interest title.
  - `topic_id` (*string, optional*): YouTube topic freebase ID (e.g. `/m/03_d0`). Elevates base confidence from 0.70 to 0.85.
  - `category` (*string, optional*): Taxonomy category (`outdoors`, `fitness`, `technology`, `culinary`, `music`, `arts`, `literature`, `entertainment`, `gaming`, `sports`, `general`). Inferred automatically if omitted.
  - `confidence` (*float, optional*): Value in `[0.0, 1.0]`. Values below 0.50 trigger non-fatal validation warnings.
  - `source_detail` (*string, optional*): Origin description for audit logging and explainability.
  - `user_confirmed` (*boolean, optional, default: false*): User explicit acceptance indicator.
- `fetched_at` (*string, optional*): ISO-8601 UTC timestamp. Items older than 90 days trigger a freshness warning.

### 2.3 Python Service Call Pattern

```python
from dating_ml_model.google_interest_provider import (
    StandardizedGoogleInterestProvider,
    validate_google_payload,
)
from dating_ml_model.service import RecommendationService

# 1. Validate payload structure
validated_payload = validate_google_payload(raw_backend_payload)

# 2. Ingest via RecommendationService using the Standardized Provider
provider = StandardizedGoogleInterestProvider()
import_result = service.import_external_interests(
    user_id=user_id,
    provider="google",
    payload=validated_payload,
    provider_instance=provider,
    user_confirmed=False,  # Present to user for confirmation before weighting as confirmed
)

# 3. Explicit User Consent must be recorded prior to ranking activation
service.set_external_interest_consent(user_id=user_id, provider="google", consent=True)
```

---

## 3. Gemini Preference Interpretation Contract

### 3.1 Architecture & Flow
```
User Natural Language Input
            │
            ▼
interpret_extended_preference_request()
            │
            ├─► If GEMINI_API_KEY: GeminiPreferenceClient (gemini-2.5-flash)
            │                         Strict JSON Schema Output
            │
            └─► If Unavailable / No Key: Deterministic Regex Fallback
            │
            ▼
_validate_extended_ai_shape() (Whitelist validation)
            │
            ▼
normalize_preferences() (Sanitization & type coercion)
            │
            ▼
Returns: {"status": "confirmation_required", "preferences": {...}, "confirmed": False}
            │
            ▼
Client UI prompts user: "Confirm these preferences?"
            │
            ▼ (User approves)
RecommendationService.confirm_interpreted_preferences()
            │
            ▼
Saved to Repository -> Active in Bilateral Scoring
```

### 3.2 Supported Preference Criteria
- **Range Fields:** `age` (`{"min": float, "max": float, "hard": bool}`), `height`, `education` (rank 1.0 to 5.0)
- **Categorical Criteria:** `profession`, `profession_group`, `religion`, `ethnicity`, `drinks`, `drugs`, `smokes`, `diet`, `children`, `pets`, `body_type`, `body_type_group`, `relationship_intention`, `region`
- **Hard Exclusions:** Strictly limited to `region`, `religion`, `profession` (server-side hard gates).

### 3.3 Python Service Call Pattern

```python
from dating_ml_model.preference_interpreter import interpret_extended_preference_request

# 1. Interpret user query
proposal = interpret_extended_preference_request("Looking for non-smokers ages 25 to 32 who want kids")

# Proposal shape:
# {
#   "status": "confirmation_required",
#   "preferences": {
#     "criteria": {
#       "age": {"min": 25.0, "max": 32.0, "hard": False},
#       "smokes": {"values": ["no"], "hard": False},
#       "children": {"values": ["yes"], "hard": False}
#     },
#     "hard_exclusions": {}
#   },
#   "confirmed": False
# }

# 2. Present proposal to user on frontend.
# 3. Upon explicit approval:
proposal["confirmed"] = True
service.confirm_interpreted_preferences(user_id=user_id, interpreted=proposal)
```

---

## 4. Production Ranking Weight Matrix (`config.json`)

The production weights in `config.json` under `final_ranking.weights` are:

| Signal | Config Weight | Scaling Mechanism | Description |
|---|---|---|---|
| `compatibility` | **0.50** | 1.0 (Fixed) | Core 14-component deterministic profile alignment |
| `location` | **0.15** | Scaled by confidence | Gazetteer distance curve interpolation |
| `preferences` | **0.15** | Scaled by confidence | Bilateral stated preference satisfaction (includes Gemini) |
| `relationship_intention` | **0.05** | 1.0 (Fixed) | Stated intention alignment table |
| `behavior` | **0.10** | Scaled by confidence | Learned like/pass feature affinity |
| `mutual_interest` | **0.05** | Scaled by confidence | Supervised mutual interaction probability |
| `search_intent` | **0.10** | Scaled by confidence | Recent search criteria alignment |
| `interests` | **0.05** | Scaled by confidence | External Google/Instagram + manual + behavioral interests |

**Effective Weight Formula (`ranking.py`):**
$$\text{Effective Weight} = \text{Base Weight} \times \text{Signal Confidence}$$
$$\text{Final Score} = \frac{\sum (\text{Effective Weight} \times \text{Signal Score})}{\sum \text{Effective Weight}}$$

---

## 5. Security, Privacy & Data Minimization Guardrails

1. **Consent Enforced at Query Time:** External interests are completely omitted from ranking if `service.get_external_interest_consent(user_id, provider)` is `False` or if `personalization_enabled` is `False`.
2. **Right to Be Forgotten:** Backend calls `service.delete_external_interests(user_id, provider=None)` to immediately purge stored interest records.
3. **Data Minimization:** Raw YouTube video titles, watch histories, or account identifiers are never stored. Only normalized tokens (`interest_tag:<canonical_name>`) and category classifications are persisted.

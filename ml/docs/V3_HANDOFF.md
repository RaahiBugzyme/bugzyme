# Dating ML V3 model handoff

This package contains the compatibility, eligibility, location, preference,
behavior, personalization, mutual-interest, ranking, evaluation, and natural
language preference interpretation layers. It is an AI/ML model package, not a
production application. Database, authentication, frontend, and deployment
infrastructure are intentionally out of scope.

## Install

Install the package dependencies from `dating_ml_model/requirements.txt` in the
backend team's environment. The Gemini SDK is optional at runtime:

```powershell
pip install -r dating_ml_model\requirements.txt
```

Set secrets only in the server environment:

```powershell
$env:GEMINI_API_KEY = "<secret>"
$env:GEMINI_MODEL = "gemini-2.5-flash"
```

Do not send `GEMINI_API_KEY` to clients or include it in logs, source code,
archives, or configuration committed to source control. If the key is absent or
Gemini is unavailable, the interpreter uses its deterministic local fallback.

## Core model calls

```python
from dating_ml_model.model import CompatibilityModel, RecommendationModel

compatibility = CompatibilityModel().predict_pair(profile_a, profile_b)
recommendations = RecommendationModel().recommend(
    user,
    candidates,
    user_preferences=confirmed_preferences,
    interactions=events,
    profile_lookup=lookup,
    limit=20,
)
```

Profiles are dictionaries. Missing attributes remain unknown; unknown values are
not converted into mismatches. The compatibility result includes eligibility,
component/category scores, confidence, adjusted score, and explanations.

`confirmed_preferences` must use the normalized preference shape produced by
`normalize_preferences`. Hard exclusions are server-side filters. Soft criteria
affect preference scoring/ranking only. The recommendation caller must apply the
returned recommendation records as the model's output and must not replace the
compatibility or ranking formulas.

## Natural-language preferences

Use the existing interpreter; do not create a second interpreter:

```python
from dating_ml_model.preference_interpreter import interpret_preference_request

proposal = interpret_preference_request("Exclude the Konkan region.")
```

The supported fields are only `region`, `religion`, and `profession`.

- A hard exclusion returns `status == "confirmation_required"`.
- A soft preference is placed under `preferences.criteria` with `hard: false`.
- Ambiguous requests return `status == "clarification_required"`.
- Similar terms are not equated automatically; for example, “Konkani” does
  not become “Konkan”.
- The returned proposal has `confirmed: false` and must not be persisted.

The backend team must show the proposal to the user, obtain explicit
confirmation, validate it again, then persist the normalized result using its
own durable storage. The package does not provide production persistence.

## Example service integration

`dating_ml_model/backend_integration_example.py` exposes an optional FastAPI
example using `RecommendationRepository`. It is suitable for integration tests
and local experimentation only. Its in-memory and CSV repositories are not
production databases, and its URL `user_id` parameters are not an
authentication system.

For a production adapter, implement `RecommendationRepository` against the
backend team's existing user/profile, interaction, blocklist, and preference
tables. The authenticated server-side identity must be passed into the
service; clients must not select another user's identity through a URL
parameter. The backend must enforce authorization, transactionality, and
durable persistence.

## Errors and validation

- `ValueError`: invalid request or provider response; return a client/input
  validation error at the backend boundary.
- `KeyError`: unknown user/profile in the example service.
- `GeminiProviderUnavailable`: provider configuration or request failure;
  use the local interpreter fallback when calling the public interpreter.
- A clarification is a response, not a preference to save.

Do not silently turn malformed or ambiguous AI output into an exclusion.

## Evaluation and tests

Run the complete suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The evaluation utilities accept caller-supplied profiles and interaction
events. No production or raw user dataset is bundled. The live Gemini smoke
test runs only when `GEMINI_API_KEY` is already present in the test process:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  dating_ml_model\tests\test_gemini_preference_interpreter.py::test_live_gemini_preference_smoke -q
```

The ordinary test suite uses fake clients and makes no paid API calls.

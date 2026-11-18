# Dating ML v2.2.0: compatibility + location + preferences + behavior (explainable, missing-data safe)

**Honest scope.** `compatibility` measures *profile alignment*. `behavior` measures *learned like/pass tendencies of one user*.
`mutual_interest` (only if a model was trained on genuine interaction logs) is *interaction-based*. **None of them is a probability of
relationship success**, and this system is NOT a scientifically validated long-term relationship predictor (that needs longitudinal
outcome data that does not exist here). 80 compatibility does not mean an 80% chance of anything.

```
profile -> eligibility / hard filters -> core compatibility -> location -> preferences -> behavior -> (optional) mutual interest/search intent -> ranking -> explanations
```
Every layer returns its OWN signal; nothing is collapsed into one opaque number. Unknown is never a penalty:
unknown location, missing preferences, no behavior history and untrained models all return `null` + an explicit status.

## What is new in 2.2.0
| Layer | Module | Key behavior |
|---|---|---|
| Location | `location.py` | coordinates > city (gazetteer) > region > country > unknown; Haversine; configurable distance curve; `preferred_distance_km` (soft) vs `max_distance_km` (hard, mutual, never applied to unknown); statuses `known / partial_unknown / unknown / unresolved / coarse / disabled` |
| Preferences | `preferences.py` | hard vs soft criteria, relationship-intention alignment, unknown candidate values kept by default |
| Behavior | `behavior.py` | events VIEW/LIKE/PASS/MATCH (+SUPER_LIKE/SAVE/UNMATCH; MESSAGE/DATE/DATE_FEEDBACK stored, not learned), summary, recency decay, `cold_start / insufficient_data / sufficient_data` |
| Search intent | `search_intent.py` | recency-weighted evidence from genuine SEARCH criteria; separate from explicit preferences and optionally contributes to personalized ranking |
| Personalization | `personalization.py` | `UserPreferenceModel`: learns from profile *features* (never IDs), confidence/evidence per value, shrinkage to the user's own baseline |
| Mutual interest | `mutual_interest.py` | trains only on genuine LIKE/PASS logs, chronological split, otherwise `insufficient_behavioral_data` |
| Ranking | `ranking.py`, `model.py::RecommendationModel` | configurable placeholder weights; unknown signals excluded; behavior/preference/mutual weights scaled by confidence (gradual, never abrupt) |
| Storage | `repository.py` | `RecommendationRepository` (SQL-ready interface) + in-memory/CSV versions |
| Use-cases / API | `service.py`, `backend_integration_example.py` | `RecommendationService`; new endpoints below |

## Quick start
```python
from dating_ml_model import CompatibilityModel, RecommendationModel
CompatibilityModel().predict_pair(a, b)                      # unchanged v2.1.0 API
rm = RecommendationModel()
rm.recommend(user, candidates, user_preferences=prefs, interactions=events, profile_lookup=lookup, now=now, limit=20)
```
`now` is an explicit input (deterministic; events dated after `now` are ignored = no future leakage).

## HTTP API (FastAPI example)
Existing: `POST /compatibility/pair`, `GET /matches/{user_id}`.
New (need a `RecommendationRepository`): `POST /interactions`, `GET|PUT /users/{id}/preferences`, `GET /users/{id}/recommendations?limit=20`,
`GET /users/{id}/behavior-summary`, `GET /users/{id}/preference-profile`, `GET /users/{id}/search-intent`.

`POST /users/{id}/preferences/interpret` uses the backend-only `google-genai` adapter
when `GEMINI_API_KEY` is configured. `GEMINI_MODEL` optionally selects the model and
defaults to `gemini-2.5-flash`. Responses are validated against the existing
`region`, `religion`, and `profession` preference format, and must be explicitly
confirmed through `POST /users/{id}/preferences/confirm` before saving. Missing
configuration or provider outages use the deterministic local interpreter; ambiguous
terms require clarification rather than becoming exclusions.

## Configuration (`config.json`, new keys only; old keys unchanged)
`location_enabled`, `default_preferred_distance_km`, `max_distance_enabled`, `location.*` (curve, confidences, gazetteer),
`preferences.*`, `behavior_enabled`, `behavior_decay`, `behavior_half_life_days`, `min_behavior_events`, `min_preference_evidence`,
`behavior_evidence_k`, `min_search_evidence`, `mutual_interest_enabled`, `mutual_interest_min_training_rows`, `final_ranking.weights.search_intent`.
**Every default is a documented, UNVALIDATED placeholder** (the distance curve is an example shape; the final-ranking weights only keep compatibility primary).
Calibrate with A/B tests / learning-to-rank once genuine interaction data exists.

## Offline evaluation
`dating_ml_model.evaluation.evaluate_recommendations(profiles, interactions, cutoff, k=10)`
uses only caller-supplied profiles and interaction events. It splits events chronologically,
reports Precision@K, Recall@K, NDCG@K, coverage, sample counts, incomplete-profile and
no-search-history groups, and compares the current ranking with an evaluation-only
search-intent-disabled copy. No default evaluation dataset or fabricated outcomes are used.

## Location notes
City names are resolved ONLY by exact lookup in `data/gazetteer_seed.csv` (30 major cities, approximate city centroids; replace with GeoNames for production
via `GazetteerResolver.from_csv`). Ambiguous or unknown names are `unresolved` (no score, no penalty). No coordinates are ever guessed.

## Known limitations
* Weights, curves, similarity tables and the placeholder ranking weights are design choices, not validated findings.
* Behavior learns tendencies from the platform's own shown candidates (selection bias) and reads profiles at training time (no as-of snapshots).
* `behavior_model.joblib` (Columbia speed-dating benchmark) is experimental and weak (see `docs/behavior_model_status.md`); it cannot score OkCupid users and is not used by the recommender.
* Religion/ethnicity are sensitive attributes; consider `"disabled_components": ["ethnicity"]` and get legal review.
* Mutual interest is a product of two directional like-probabilities (independence assumption) and exists only after genuine training.

## Part 1: core compatibility engine (v2.1.0, unchanged)

A **deterministic, unsupervised profile-alignment engine**. Given two profiles it answers:
*"How aligned are the attributes both people filled in?"* and *"How much evidence was that based on?"*

**It is NOT a relationship-success predictor.** The OkCupid profile data contains no outcome labels
(no matches, replies, dates or relationships), so nothing here was trained and no accuracy is claimed.
It does not reproduce any commercial dating app's algorithm and is not scientifically validated.

## Architecture

```
API (FastAPI, backend_integration_example.py)
  -> MatchingService (service.py)          orchestration only, no formulas
    -> CompatibilityModel (model.py)       predict_pair / predict_matches / check_eligibility
      -> CompatibilityEngine (compatibility_engine.py) + eligibility.py + feature_engineering.py
    -> ProfileRepository (repository.py)   storage, kept out of the model
Optional, separate: BehaviorModel (behavior.py + behavior_model.joblib), only if a labeled dataset was supplied.
```

## Scoring

1. **Eligibility gate** (`eligibility.py`): both adults (>= `min_age`, age known) and mutual, directional attraction from sex + orientation. Unknown sex/orientation/age => not eligible. Ineligible pairs get **no scores** and are never recommended.
2. **14 component similarities** in [0, 1], `None` when either side is unknown (never treated as a mismatch).
3. **6 macro-categories** (unknown-aware weighted means):

| Category | Components (weights) |
|---|---|
| Demographics | age 0.6 (linear over 20 yrs), generation 0.4 (same band = 1) |
| Career & education | education 0.5 (ordinal), profession 0.5 (exact 1.0 / same broad group 0.5 / else 0) |
| Values & culture | religion 0.6 (base religion), ethnicity 0.4 (Jaccard of sets) |
| Lifestyle | drinks, drugs, smokes, diet (0.25 each) |
| Family | children stance 0.7 (yes/maybe/no), pets 0.3 |
| Attraction | height 0.8 (linear over 12 in), body type 0.2 |

4. `compatibility_score` = weighted mean of known categories x 100 (weight profile `long_term`: demographics .20, career .10, values .20, lifestyle .15, family .25, attraction .10; `equal` also available).
5. `confidence_score` = share of total scoring weight with data on **both** profiles.
6. `adjusted_score = confidence * compatibility + (1 - confidence) * 50` (evidence-aware shrinkage; sparse profiles stay near 50). Rankings use `adjusted_score`.

Generations (reference year configurable, default 2026): Gen Z 1997-2012, Zillennial 1990-1996, Millennial 1981-1989, Gen X 1965-1980, Baby Boomer+ <= 1964.
Income, spoken languages and astrological sign are deliberately not used.

## Output contract

`user_a, user_b, eligible, eligibility_reason, compatibility_score, confidence_score, adjusted_score, categories{6}, components{...}, explanation[...], model_version`.
Note: `compatibility_score` is the **raw** aligned score; the shrunken value is `adjusted_score`.
Explanations are deterministic text derived from the component values (no LLM).

## Usage

```python
from dating_ml_model import CompatibilityModel
model = CompatibilityModel()
model.predict_pair(profile_a, profile_b)
model.predict_matches(user, candidates, top_k=10)   # eligibility-filtered, sorted by adjusted_score
model.check_eligibility(profile_a, profile_b)
```
Profiles are dicts using the OkCupid field names and values (`age, sex, orientation, education, job, religion, ethnicity, drinks, drugs, smokes, diet, offspring, pets, height (inches), body_type`). Map your app's fields to these values.
Run tests: `python -m pytest dating_ml_model/tests` from the folder that contains `dating_ml_model/`.

## Important limitations (read before shipping)

- **All weights, similarity functions, profession groups and the ordinal scales are design choices, not validated findings.** The age (20-year linear) function was carried over from the original engine; everything else is new in V2.1. Tune via `config.json` and validate against real user behavior (likes, replies, mutual matches, retention) before trusting the ranking.
- Similarity is not the same as compatibility: the engine rewards "alike", not "complementary".
- Religion and ethnicity are sensitive attributes. Ranking on them can create discriminatory outcomes and has legal implications (e.g. DPDP Act, GDPR). Get explicit consent, get legal review, and consider `"disabled_components": ["ethnicity"]` in `config.json`.
- Scoring is pure Python (about 0.1 ms/pair). Pre-filter candidates (eligibility, location, age range) before ranking; do not score an entire user table per request.
- Declared profile data is self-reported and can be false.
- The optional behavioral model (if present) is trained on the Columbia speed-dating `match` outcome (short-term mutual interest at a single event) and does not measure long-term relationship success. It is never blended with the compatibility score.

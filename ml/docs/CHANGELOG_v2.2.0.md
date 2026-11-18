# Changelog: 2.1.0 -> 2.2.0

* Previous package version: **2.1.0** (backup: `backup/dating_ml_model_v2.1.0_original.zip`)
* New package version: **2.2.0** (`config.package_version`, `dating_ml_model.__version__`)
* Compatibility engine version: **2.1.0, unchanged** (`predict_pair()["model_version"]` still reports `2.1.0`, so the golden predictions are byte-for-byte stable).

## Added
Location/distance, explicit hard+soft preferences, relationship-intention alignment, interaction events, behavior summary and recency decay,
`UserPreferenceModel`, optional mutual-interest model, final multi-signal ranking, `RecommendationModel`, `RecommendationService`,
`RecommendationRepository` (+ in-memory/CSV), 6 new HTTP endpoints, JSON schemas, gazetteer seed, new config keys, extended feature schema, 137 new tests.

## Backward compatibility
| Item | Status |
|---|---|
| `compatibility_engine.py`, `eligibility.py` | byte-identical |
| `CompatibilityModel`, `predict_pair`, `predict_matches`, `score_pair`, `check_eligibility` | unchanged (same code, same outputs; verified against the original golden file) |
| `ProfileRepository`, `InMemoryProfileRepository`, `CsvProfileRepository`, `MatchingService` | unchanged; new abstract methods live in the NEW `RecommendationRepository` |
| `BehaviorModel` (Columbia benchmark loader) | unchanged |
| `POST /compatibility/pair`, `GET /matches/{user_id}`, `create_app(repository, model=None)` | unchanged (new optional `clock` argument) |
| `config.json` | all previous keys unchanged (tested); only new keys added |
| Existing 56 tests | unchanged, all pass |
| **`feature_schema.json`** | **intentional change**: top-level list -> object. The previous list is preserved under `dataset_audit` |
| Files edited (not pure append) | `__init__.py` (exports/version), `backend_integration_example.py` (app factory extended) |

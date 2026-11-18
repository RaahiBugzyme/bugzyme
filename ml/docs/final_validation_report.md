# Dating ML v2.2.0 — final validation report

**Scope:** compatibility = profile alignment; behavior = learned like/pass tendency; mutual interest = interaction-based (only with genuine logs). None is a relationship-success probability.

## Stage 0 baseline

Before the Stage 1 event-model extension, the existing suite was run with:

```text
python -m pytest dating_ml_model/tests -q
```

Result: **193 passed, 0 failed**.

- Dataset: [59946, 19] (sha256 `450f73706a458689…`) | legitimate pairwise target in profiles data: **False**
- Baseline (v2.1.0) tests: **56** | final suite on the extracted package: **193 passed, 0 failed** (193 passed in 9.66s)

## Test groups

- core_engine_v2_1_0: 48 passed, 0 failed, 0 skipped
- regression_vs_v2_1_0_baseline: 7 passed, 0 failed, 0 skipped
- location_incl_null_cases: 39 passed, 0 failed, 0 skipped
- preferences: 16 passed, 0 failed, 0 skipped
- behavior_and_cold_start: 32 passed, 0 failed, 0 skipped
- recommendation_pipeline: 16 passed, 0 failed, 0 skipped
- mutual_interest: 10 passed, 0 failed, 0 skipped
- api: 12 passed, 0 failed, 0 skipped

## Gates

- PASS: missing_data_tests
- PASS: sparse_profile_tests
- PASS: recommendations_only_eligible
- PASS: location_unknown_never_penalized
- PASS: location_known_cases_have_distance
- PASS: preferences_hard_excludes_soft_reranks
- PASS: preferences_unknown_not_mismatch
- PASS: behavior_cold_start_thresholds
- PASS: behavior_weight_gradual_and_below_compatibility
- PASS: real_profiles_cold_start_no_penalty
- PASS: scenario_suite
- PASS: tests_core_engine_v2_1_0
- PASS: tests_regression_vs_v2_1_0_baseline
- PASS: tests_location_incl_null_cases
- PASS: tests_preferences
- PASS: tests_behavior_and_cold_start
- PASS: tests_recommendation_pipeline
- PASS: tests_mutual_interest
- PASS: tests_api
- PASS: exported_sources_byte_identical
- PASS: exported_package_test_suite
- PASS: determinism_5_fresh_models
- PASS: A_notebook_equals_exported
- PASS: B_exported_equals_backend
- PASS: D_eligibility_identical
- PASS: E_categories_identical
- PASS: F_adjusted_identical
- PASS: real_pairs_include_enough_eligible
- PASS: G_reco_notebook_equals_exported
- PASS: H_reco_exported_equals_service
- PASS: I_reco_service_equals_http_backend
- PASS: J_reco_parity_inputs_non_trivial

## Parser coverage on the real profiles (% of non-null values understood)

```
           parsed_%
education     96.84
job           84.49
religion      80.51
ethnicity    100.00
drinks       100.00
drugs        100.00
smokes       100.00
diet          94.96
offspring     53.56
pets         100.00
body_type     98.99
height        99.96
```

## Score distribution, random eligible pairs (sanity check, not accuracy)

```
       compatibility_score  confidence_score  adjusted_score
count              2410.00           2410.00         2410.00
mean                 57.76             59.91           54.69
std                  15.97             11.64            9.37
min                   2.67             20.00           26.31
25%                  46.53             52.25           47.87
50%                  58.15             59.25           54.75
75%                  69.59             66.75           61.69
max                  95.80            100.00           82.20

                  compatibility_score       adjusted_score      
                                 mean count           mean count
confidence_bucket                                               
<=50                            56.79   465          53.04   465
50-75                           57.84  1724          54.78  1724
75-90                           59.73   200          57.79   200
90-100                          54.38    21          54.20    21
```

## Behavioral layers

- Interaction log: not provided
- Optional Columbia benchmark (separate, short-term mutual interest; never blended): not trained (no speeddating.csv / insufficient data)

## Known limitations

- Weights, curves, similarity tables and ranking weights are design choices, not validated findings; calibrate with real behavior (A/B tests, learning-to-rank).
- Similarity is not compatibility; religion/ethnicity are sensitive (consider `disabled_components`).
- Self-reported data; not a reproduction of any proprietary app; not scientifically proven; NOT a long-term relationship predictor.
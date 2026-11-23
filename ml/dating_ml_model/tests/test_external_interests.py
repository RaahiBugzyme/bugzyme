"""Comprehensive tests for Phase 1: External Interest Personalization Architecture.

Covers:
1. Normalization and canonical token formatting
2. Deterministic mock Google and Instagram provider extraction (synthetic data only)
3. Per-user, per-provider consent tracking and global opt-out
4. Repository storage, retrieval, provider-specific deletion, and complete purge
5. User isolation (no cross-user data leakage)
6. Consent enforcement before external interests affect recommendations
7. Ranking influence on eligible candidates (soft re-ranking)
8. Strict non-override of eligibility, explicit preferences, and dealbreakers
9. Explainability with provider provenance and confidence
10. FastAPI integration endpoints in backend_integration_example
"""
from datetime import datetime, timezone
import pytest

from dating_ml_model import (
    CompatibilityModel,
    RecommendationModel,
    PrivacyManager,
    NormalizedInterest,
    ExternalInterestPayload,
    MockGoogleInterestProvider,
    MockInstagramInterestProvider,
)
from dating_ml_model.external_interests import (
    normalize_interest_tag,
    infer_interest_category,
    generate_synthetic_google_data,
    generate_synthetic_instagram_data,
)
from dating_ml_model.repository import InMemoryRecommendationRepository
from dating_ml_model.service import RecommendationService
from dating_ml_model.interests import UserInterestProfile
from dating_ml_model.explainability import explain_recommendation

NOW = datetime(2026, 10, 27, 12, 0, 0)


# ============================================================================
# 1. NORMALIZATION & TAXONOMY TESTS
# ============================================================================

def test_interest_tag_normalization():
    assert normalize_interest_tag("#RockClimbing") == "rockclimbing"
    assert normalize_interest_tag("#specialty-coffee") == "specialty_coffee"
    assert normalize_interest_tag("  Machine Learning & AI  ") == "machine_learning_ai"
    assert normalize_interest_tag("Indie-Rock / Folk Music") == "indie_rock_folk_music"
    assert normalize_interest_tag("___test___") == "test"
    assert normalize_interest_tag("") is None
    assert normalize_interest_tag("   ") is None
    assert normalize_interest_tag(None) is None


def test_infer_interest_category():
    assert infer_interest_category("rock_climbing") == "outdoors"
    assert infer_interest_category("hiking") == "outdoors"
    assert infer_interest_category("specialty_coffee") == "culinary"
    assert infer_interest_category("jazz") == "music"
    assert infer_interest_category("machine_learning") == "technology"
    assert infer_interest_category("photography") == "arts"
    assert infer_interest_category("pottery") == "arts"
    assert infer_interest_category("marathon") == "fitness"
    assert infer_interest_category("indie_film") == "entertainment"
    assert infer_interest_category("board_games") == "entertainment"
    assert infer_interest_category("some_unmapped_hobby_xyz") == "general"


# ============================================================================
# 2. MOCK PROVIDER EXTRACTION TESTS (SYNTHETIC FIXTURES ONLY)
# ============================================================================

def test_mock_google_provider_extraction():
    provider = MockGoogleInterestProvider()
    assert provider.provider_id == "google"
    assert "https://www.googleapis.com/auth/youtube.readonly" in provider.supported_scopes

    synthetic_payload = generate_synthetic_google_data("outdoors_tech")
    result = provider.extract_interests("user_101", synthetic_payload)

    assert isinstance(result, ExternalInterestPayload)
    assert result.user_id == "user_101"
    assert result.provider == "google"
    assert len(result.external_account_id_hash) == 16
    assert len(result.interests) == 4

    tokens = [i.canonical_token for i in result.interests]
    assert "interest_tag:rock_climbing" in tokens
    assert "interest_tag:hiking_and_camping" in tokens
    assert "interest_tag:machine_learning" in tokens
    assert "interest_tag:specialty_coffee" in tokens

    # Verify category inference and calibrated confidence
    rc = next(i for i in result.interests if i.canonical_token == "interest_tag:rock_climbing")
    assert rc.category == "outdoors"
    assert rc.confidence == 0.90
    assert rc.provider == "google"
    assert rc.source_detail == "youtube_subscription"


def test_mock_instagram_provider_extraction():
    provider = MockInstagramInterestProvider()
    assert provider.provider_id == "instagram"
    assert "instagram_basic" in provider.supported_scopes

    synthetic_payload = generate_synthetic_instagram_data("arts_culinary")
    result = provider.extract_interests("user_202", synthetic_payload)

    assert isinstance(result, ExternalInterestPayload)
    assert result.user_id == "user_202"
    assert result.provider == "instagram"
    assert len(result.external_account_id_hash) == 16

    tokens = [i.canonical_token for i in result.interests]
    assert "interest_tag:photographer" in tokens
    assert "interest_tag:streetphotography" in tokens
    assert "interest_tag:pottery" in tokens
    assert "interest_tag:specialtycoffee" in tokens
    assert "interest_tag:indiefilm" in tokens
    assert "interest_tag:architecture" in tokens

    photo = next(i for i in result.interests if i.canonical_token == "interest_tag:photographer")
    assert photo.category == "arts"
    assert photo.confidence == 0.85
    assert photo.source_detail == "instagram_creator_category"


# ============================================================================
# 3. CONSENT TRACKING & GLOBAL OPT-OUT TESTS
# ============================================================================

def test_per_user_per_provider_consent_and_opt_out():
    pm = PrivacyManager()
    uid = "user_consent_test"

    # Default: external consent is False
    assert pm.get_external_interest_consent(uid, "google") is False
    assert pm.get_external_interest_consent(uid, "instagram") is False
    assert pm.can_use_external_interests(uid) is False

    # Enable Google consent only
    pm.set_external_interest_consent(uid, "google", True)
    assert pm.get_external_interest_consent(uid, "google") is True
    assert pm.get_external_interest_consent(uid, "instagram") is False
    assert pm.can_use_external_interests(uid, "google") is True
    assert pm.can_use_external_interests(uid, "instagram") is False
    assert pm.can_use_external_interests(uid) is True

    # Global personalization opt-out immediately shuts off all external interests
    pm.set_personalization_enabled(uid, False)
    assert pm.get_external_interest_consent(uid, "google") is False
    assert pm.can_use_external_interests(uid, "google") is False
    assert pm.can_use_external_interests(uid) is False

    # Re-enabling personalization restores individual provider consent
    pm.set_personalization_enabled(uid, True)
    assert pm.get_external_interest_consent(uid, "google") is True

    # Specific revocation
    pm.revoke_all_external_consent(uid)
    assert pm.get_external_interest_consent(uid, "google") is False
    assert pm.can_use_external_interests(uid) is False


# ============================================================================
# 4. REPOSITORY STORAGE, RETRIEVAL, AND DELETION TESTS
# ============================================================================

def test_repository_external_interest_lifecycle():
    repo = InMemoryRecommendationRepository()
    uid = "u_storage_test"

    google_interests = [
        {"canonical_token": "interest_tag:hiking", "display_name": "Hiking", "provider": "google", "confidence": 0.9, "category": "outdoors"},
        {"canonical_token": "interest_tag:jazz", "display_name": "Jazz", "provider": "google", "confidence": 0.8, "category": "music"},
    ]
    instagram_interests = [
        {"canonical_token": "interest_tag:pottery", "display_name": "Pottery", "provider": "instagram", "confidence": 0.85, "category": "arts"},
    ]

    # Save Google interests
    res_g = repo.save_external_interests(uid, "google", google_interests)
    assert res_g["count"] == 2
    assert res_g["total_external_interests"] == 2

    # Save Instagram interests
    res_i = repo.save_external_interests(uid, "instagram", instagram_interests)
    assert res_i["count"] == 1
    assert res_i["total_external_interests"] == 3

    # Retrieval
    all_items = repo.get_external_interests(uid)
    assert len(all_items) == 3

    g_only = repo.get_external_interests(uid, provider="google")
    assert len(g_only) == 2
    assert all(i["provider"] == "google" for i in g_only)

    i_only = repo.get_external_interests(uid, provider="instagram")
    assert len(i_only) == 1
    assert i_only[0]["provider"] == "instagram"

    # Accounts metadata
    accounts = repo.get_external_accounts(uid)
    assert len(accounts) == 2
    providers = {a["provider"] for a in accounts}
    assert providers == {"google", "instagram"}

    # Provider-specific deletion: delete Instagram only
    deleted_ig = repo.delete_external_interests(uid, provider="instagram")
    assert deleted_ig == 1
    remaining = repo.get_external_interests(uid)
    assert len(remaining) == 2
    assert all(i["provider"] == "google" for i in remaining)

    # Purge all remaining
    deleted_all = repo.delete_external_interests(uid)
    assert deleted_all == 2
    assert len(repo.get_external_interests(uid)) == 0
    assert len(repo.get_external_accounts(uid)) == 0


# ============================================================================
# 5. USER ISOLATION TESTS
# ============================================================================

def test_external_interests_user_isolation():
    repo = InMemoryRecommendationRepository()
    u1, u2 = "user_alpha", "user_beta"

    repo.save_external_interests(u1, "google", [
        {"canonical_token": "interest_tag:climbing", "provider": "google", "confidence": 0.9}
    ])
    repo.save_external_interests(u2, "instagram", [
        {"canonical_token": "interest_tag:baking", "provider": "instagram", "confidence": 0.8}
    ])

    u1_items = repo.get_external_interests(u1)
    u2_items = repo.get_external_interests(u2)

    assert len(u1_items) == 1 and u1_items[0]["canonical_token"] == "interest_tag:climbing"
    assert len(u2_items) == 1 and u2_items[0]["canonical_token"] == "interest_tag:baking"

    # Purging u1 does not affect u2
    repo.delete_external_interests(u1)
    assert len(repo.get_external_interests(u1)) == 0
    assert len(repo.get_external_interests(u2)) == 1


# ============================================================================
# 6. CONSENT ENFORCEMENT IN RECOMMENDATIONS
# ============================================================================

def test_consent_enforced_before_recommendations_affected():
    user = {
        "id": "u_seeker", "age": 28, "sex": "m", "orientation": "straight",
        "interests": ["reading"],
    }
    candidate = {
        "id": "c_rockclimber", "age": 27, "sex": "f", "orientation": "straight",
        "interests": ["rock_climbing", "hiking"],
    }
    repo = InMemoryRecommendationRepository([user, candidate])
    service = RecommendationService(RecommendationModel().compatibility, repo, clock=lambda: NOW)

    # Import Google interests for u_seeker containing rock climbing
    service.import_external_interests(
        "u_seeker", "google",
        {"items": [{"title": "Rock Climbing", "is_topic": True, "confidence": 0.95}]}
    )

    # CASE A: Consent NOT granted -> external interests must NOT be used
    recs_no_consent = service.get_recommendations("u_seeker", limit=5)
    assert len(recs_no_consent) == 1
    # Without consent or behavioral events, interest profile should be omitted/cold_start
    assert recs_no_consent[0].get("interests") is None

    # CASE B: Consent granted -> external interests are active!
    service.set_external_interest_consent("u_seeker", "google", True)
    recs_consented = service.get_recommendations("u_seeker", limit=5)
    assert len(recs_consented) == 1
    int_res = recs_consented[0].get("interests")
    assert int_res is not None
    assert int_res["status"] == "known"
    assert any("rock_climbing" in a for a in int_res["aligned_interests"])

    # CASE C: Consent revoked -> immediately ceases using external interests
    service.set_external_interest_consent("u_seeker", "google", False)
    recs_revoked = service.get_recommendations("u_seeker", limit=5)
    assert recs_revoked[0].get("interests") is None


# ============================================================================
# 7. RANKING INFLUENCE ON ELIGIBLE CANDIDATES
# ============================================================================

def test_external_interest_ranking_influence_on_eligible_candidates():
    user = {
        "id": "u_main", "age": 30, "sex": "m", "orientation": "straight",
        "job": "software engineer", "education": "master", "religion": "agnostic",
    }
    cand_match = {
        "id": "c_has_interest", "age": 29, "sex": "f", "orientation": "straight",
        "job": "software engineer", "education": "master", "religion": "agnostic",
        "interests": ["rock_climbing", "jazz"],
    }
    cand_no_match = {
        "id": "c_no_interest", "age": 29, "sex": "f", "orientation": "straight",
        "job": "software engineer", "education": "master", "religion": "agnostic",
        "interests": ["knitting"],
    }

    # Custom config giving interests an explicit non-zero ranking weight
    cfg = dict(RecommendationModel().compatibility.config)
    cfg_weights = dict(cfg["final_ranking"]["weights"])
    cfg_weights["interests"] = 0.20  # Give interests a 20% ranking weight
    cfg["final_ranking"]["weights"] = cfg_weights

    model = RecommendationModel(config=cfg)
    repo = InMemoryRecommendationRepository([user, cand_match, cand_no_match])
    service = RecommendationService(model.compatibility, repo, recommendation_model=model, clock=lambda: NOW)

    # Provide user with consented external interests in rock climbing and jazz
    service.import_external_interests(
        "u_main", "google",
        {"items": [
            {"title": "Rock Climbing", "is_topic": True, "confidence": 0.95},
            {"title": "Jazz", "is_topic": True, "confidence": 0.90},
        ]},
        user_confirmed=True,
    )
    service.set_external_interest_consent("u_main", "google", True)

    recs = service.get_recommendations("u_main", limit=5)
    assert len(recs) == 2

    # cand_match must rank ahead of cand_no_match due to interest alignment
    top_cand = recs[0]
    second_cand = recs[1]
    assert top_cand["candidate_id"] == "c_has_interest"
    assert second_cand["candidate_id"] == "c_no_interest"

    top_int = top_cand["interests"]
    assert top_int["status"] == "known"
    assert top_int["score"] > 80.0
    assert top_cand["ranking"]["final_score"] > second_cand["ranking"]["final_score"]


# ============================================================================
# 8. STRICT NON-OVERRIDE OF DEALBREAKERS & ELIGIBILITY
# ============================================================================

def test_external_interests_never_override_dealbreakers():
    cfg = dict(RecommendationModel().compatibility.config)
    cfg["final_ranking"]["weights"]["interests"] = 0.30
    model = RecommendationModel(config=cfg)

    user = {
        "id": "u_gatekeeper", "age": 25, "sex": "m", "orientation": "straight",
        "city": "Mumbai", "country": "India",
    }
    # User has 100% matching external interests in climbing
    ext_interests = [{"canonical_token": "interest_tag:rock_climbing", "provider": "google", "confidence": 1.0}]
    interest_prof = UserInterestProfile(cfg).fit(user, [], lambda i: None, external_interests=ext_interests)

    # Dealbreaker A: Underage candidate
    cand_underage = {
        "id": "c_underage", "age": 17, "sex": "f", "orientation": "straight",
        "interests": ["rock_climbing"],
    }
    rec_a = model.evaluate_candidate(user, cand_underage, interest_profile=interest_prof)
    assert rec_a["eligibility"]["eligible"] is False
    assert "under 18" in rec_a["eligibility"]["reasons"][0]
    assert rec_a["ranking"]["final_score"] is None

    # Dealbreaker B: Directional sex/orientation attraction mismatch
    cand_gay = {
        "id": "c_gay", "age": 25, "sex": "f", "orientation": "gay",
        "interests": ["rock_climbing"],
    }
    rec_b = model.evaluate_candidate(user, cand_gay, interest_profile=interest_prof)
    assert rec_b["eligibility"]["eligible"] is False
    assert "not attracted" in rec_b["eligibility"]["reasons"][0]

    # Dealbreaker C: Hard user preference (age dealbreaker)
    hard_prefs = {
        "criteria": {
            "age": {"min": 24, "max": 27, "hard": True},
        }
    }
    cand_too_old = {
        "id": "c_old", "age": 35, "sex": "f", "orientation": "straight",
        "interests": ["rock_climbing"],
    }
    rec_c = model.evaluate_candidate(user, cand_too_old, user_preferences=hard_prefs, interest_profile=interest_prof)
    assert rec_c["eligibility"]["eligible"] is False
    assert any("hard preference" in r for r in rec_c["eligibility"]["reasons"])
    assert rec_c["ranking"]["final_score"] is None

    # Dealbreaker D: Hard exclusion (religion exclusion)
    hard_exclusions = {
        "hard_exclusions": {
            "religion": {"values": ["scientology"]},
        }
    }
    cand_excluded_rel = {
        "id": "c_rel", "age": 25, "sex": "f", "orientation": "straight",
        "religion": "scientology",
        "interests": ["rock_climbing"],
    }
    rec_d = model.evaluate_candidate(user, cand_excluded_rel, user_preferences=hard_exclusions, interest_profile=interest_prof)
    assert rec_d["eligibility"]["eligible"] is False
    assert any("explicitly excluded" in r for r in rec_d["eligibility"]["reasons"])

    # Dealbreaker E: Hard max geographic distance
    distance_prefs = {
        "max_distance_km": 50,
    }
    cand_london = {
        "id": "c_far", "age": 25, "sex": "f", "orientation": "straight",
        "city": "London", "country": "United Kingdom",
        "interests": ["rock_climbing"],
    }
    rec_e = model.evaluate_candidate(user, cand_london, user_preferences=distance_prefs, interest_profile=interest_prof)
    assert rec_e["eligibility"]["eligible"] is False
    assert any("maximum distance" in r for r in rec_e["eligibility"]["reasons"])


# ============================================================================
# 9. EXPLAINABILITY & PROVENANCE TESTS
# ============================================================================

def test_explainability_reports_external_interest_provenance():
    user = {
        "id": "u_expl_user", "age": 26, "sex": "m", "orientation": "straight",
    }
    candidate = {
        "id": "c_expl_cand", "age": 26, "sex": "f", "orientation": "straight",
        "interests": ["rock_climbing", "specialty_coffee"],
    }
    repo = InMemoryRecommendationRepository([user, candidate])
    service = RecommendationService(RecommendationModel().compatibility, repo, clock=lambda: NOW)

    # Import both Google and Instagram interests
    service.import_external_interests(
        "u_expl_user", "google",
        {"items": [{"title": "Rock Climbing", "is_topic": True, "confidence": 0.90}]}
    )
    service.import_external_interests(
        "u_expl_user", "instagram",
        {"profile_metadata": {"bio_hashtags": ["#specialty_coffee"]}}
    )
    # Enable consent for both
    service.set_external_interest_consent("u_expl_user", "google", True)
    service.set_external_interest_consent("u_expl_user", "instagram", True)

    explanation = service.explain_candidate("u_expl_user", "c_expl_cand")
    assert explanation["user_id"] == "u_expl_user"
    assert explanation["candidate_id"] == "c_expl_cand"

    # Verify structured explanation contains external interests with provenance
    matched = explanation["matched_preferences"]
    ext_matches = [m for m in matched if m.get("direction") == "external_interest"]
    assert len(ext_matches) >= 2

    climb_match = next(m for m in ext_matches if "rock_climbing" in m["criterion"])
    assert "Google" in climb_match["providers"]
    assert climb_match["confidence"] == 0.90

    coffee_match = next(m for m in ext_matches if "specialty_coffee" in m["criterion"] or "specialtycoffee" in m["criterion"])
    assert "Instagram" in coffee_match["providers"]

    # Verify text summary discloses provenance
    text_summary = " ".join(explanation["text_explanations"])
    assert "Google" in text_summary or "Instagram" in text_summary
    assert "relationship success" in explanation["disclaimer"].lower() or "not a predictor" in explanation["disclaimer"].lower()


# ============================================================================
# 10. FASTAPI BACKEND INTEGRATION ENDPOINTS
# ============================================================================

def test_fastapi_external_interest_endpoints():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dating_ml_model.backend_integration_example import create_app

    user = {"id": "api_user_1", "age": 28, "sex": "m", "orientation": "straight"}
    repo = InMemoryRecommendationRepository([user])
    app = create_app(repo, clock=lambda: NOW)
    client = TestClient(app)

    # 1. Import external interests
    import_resp = client.post(
        "/users/api_user_1/external-interests/google/import",
        json={
            "payload": {
                "items": [
                    {"title": "Jazz", "is_topic": True, "confidence": 0.90},
                    {"title": "Hiking", "is_topic": True, "confidence": 0.85},
                ]
            },
            "user_confirmed": True,
        },
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["imported_count"] == 2

    # 2. Grant consent
    consent_resp = client.put(
        "/users/api_user_1/external-interests/google/consent",
        json={"consent": True},
    )
    assert consent_resp.status_code == 200
    assert consent_resp.json()["consent"] is True

    # 3. Retrieve interests
    get_resp = client.get("/users/api_user_1/external-interests")
    assert get_resp.status_code == 200
    assert get_resp.json()["count"] == 2

    # 4. View accounts
    accts_resp = client.get("/users/api_user_1/external-accounts")
    assert accts_resp.status_code == 200
    assert len(accts_resp.json()["accounts"]) == 1
    assert accts_resp.json()["accounts"][0]["provider"] == "google"
    assert accts_resp.json()["accounts"][0]["consent_active"] is True

    # 5. Delete interests
    del_resp = client.delete("/users/api_user_1/external-interests?provider=google")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_count"] == 2

    # Verify empty
    get_after = client.get("/users/api_user_1/external-interests")
    assert get_after.json()["count"] == 0


# ============================================================================
# 11. MANUAL INTEREST PERSONALIZATION TESTS
# ============================================================================

def test_manual_interest_normalization_and_validation():
    from dating_ml_model.external_interests import (
        validate_and_normalize_manual_interest,
        VALID_INTEREST_CATEGORIES,
        MAX_INTEREST_NAME_LENGTH,
    )

    # 1. Valid normalization & category inference
    item = validate_and_normalize_manual_interest("  Rock Climbing  ")
    assert item.canonical_token == "interest_tag:rock_climbing"
    assert item.display_name == "Rock Climbing"
    assert item.category == "outdoors"
    assert item.provider == "manual_entry"
    assert item.source_detail == "user_selected"
    assert item.confidence == 1.0
    assert item.user_confirmed is True

    # 2. Explicit valid category override
    item_art = validate_and_normalize_manual_interest("Pottery Making", category="arts", user_confirmed=False)
    assert item_art.canonical_token == "interest_tag:pottery_making"
    assert item_art.category == "arts"
    assert item_art.user_confirmed is False

    # 3. Invalid category rejection
    with pytest.raises(ValueError, match="Invalid category"):
        validate_and_normalize_manual_interest("Cycling", category="non_existent_category_xyz")

    # 4. Empty / whitespace validation
    with pytest.raises(ValueError, match="empty or None"):
        validate_and_normalize_manual_interest(None)

    with pytest.raises(ValueError, match="empty or whitespace"):
        validate_and_normalize_manual_interest("   ")

    with pytest.raises(ValueError, match="valid alphanumeric"):
        validate_and_normalize_manual_interest("###@@@---___")

    # 5. Excessive length validation
    long_name = "a" * (MAX_INTEREST_NAME_LENGTH + 1)
    with pytest.raises(ValueError, match="exceeds maximum length"):
        validate_and_normalize_manual_interest(long_name)


def test_manual_interest_add_retrieve_deduplicate():
    user = {"id": "u_manual_1", "age": 28, "sex": "m", "orientation": "straight"}
    repo = InMemoryRecommendationRepository([user])
    service = RecommendationService(RecommendationModel().compatibility, repo, clock=lambda: NOW)

    # 1. Add single interest
    res1 = service.add_manual_interest("u_manual_1", "Jazz Music")
    assert res1["is_new"] is True
    assert res1["total_manual_interests"] == 1
    assert res1["interest"]["canonical_token"] == "interest_tag:jazz_music"
    assert res1["interest"]["category"] == "music"

    # 2. Duplicate addition: case-insensitive, idempotent
    res2 = service.add_manual_interest("u_manual_1", "  JAZZ-MUSIC  ")
    assert res2["is_new"] is False
    assert res2["total_manual_interests"] == 1
    assert len(service.get_manual_interests("u_manual_1")) == 1

    # 3. Batch addition
    batch_res = service.add_manual_interests(
        "u_manual_1",
        [
            {"name": "Rock Climbing", "category": "outdoors"},
            {"name": "Specialty Coffee", "category": "culinary", "user_confirmed": True},
            "Trail Running",
        ],
    )
    assert batch_res["added_count"] == 3
    assert batch_res["total_manual_interests"] == 4

    # 4. Retrieve manual interests
    all_manual = service.get_manual_interests("u_manual_1")
    tokens = {i["canonical_token"] for i in all_manual}
    assert tokens == {
        "interest_tag:jazz_music",
        "interest_tag:rock_climbing",
        "interest_tag:specialty_coffee",
        "interest_tag:trail_running",
    }
    assert all(i["provider"] == "manual_entry" for i in all_manual)
    assert all(i["source_detail"] == "user_selected" for i in all_manual)
    assert all(i["confidence"] == 1.0 for i in all_manual)


def test_manual_interest_confirm_and_remove():
    user = {"id": "u_manual_2", "age": 30, "sex": "f", "orientation": "straight"}
    repo = InMemoryRecommendationRepository([user])
    service = RecommendationService(RecommendationModel().compatibility, repo, clock=lambda: NOW)

    service.add_manual_interest("u_manual_2", "Photography", user_confirmed=False)
    service.add_manual_interest("u_manual_2", "Bouldering", user_confirmed=True)

    current = service.get_manual_interests("u_manual_2")
    photo = next(i for i in current if "photography" in i["canonical_token"])
    assert photo["user_confirmed"] is False

    # Confirm interest
    confirm_res = service.confirm_interest("u_manual_2", "photography", confirmed=True)
    assert confirm_res["user_confirmed"] is True
    assert confirm_res["interest"]["user_confirmed"] is True

    # Remove single interest
    del_res = service.remove_manual_interest("u_manual_2", "photography")
    assert del_res["removed"] is True
    remaining = service.get_manual_interests("u_manual_2")
    assert len(remaining) == 1
    assert "bouldering" in remaining[0]["canonical_token"]

    # Delete all manual interests
    purge_res = service.delete_manual_interests("u_manual_2")
    assert purge_res["deleted_count"] == 1
    assert len(service.get_manual_interests("u_manual_2")) == 0


def test_manual_interest_consent_and_opt_out():
    user = {"id": "u_manual_3", "age": 27, "sex": "m", "orientation": "straight"}
    candidate = {
        "id": "c_manual_cand", "age": 26, "sex": "f", "orientation": "straight",
        "interests": ["rock_climbing"],
    }
    repo = InMemoryRecommendationRepository([user, candidate])
    service = RecommendationService(RecommendationModel().compatibility, repo, clock=lambda: NOW)

    service.add_manual_interest("u_manual_3", "Rock Climbing")

    # 1. By default, manual interests are active when added
    recs_active = service.get_recommendations("u_manual_3", limit=5)
    assert len(recs_active) == 1
    int_info = recs_active[0].get("interests")
    assert int_info is not None
    assert int_info["status"] == "known"
    assert any("rock_climbing" in a for a in int_info["aligned_interests"])

    # 2. Revoke manual entry consent explicitly
    service.set_manual_interest_consent("u_manual_3", False)
    assert service.get_manual_interest_consent("u_manual_3") is False
    recs_revoked = service.get_recommendations("u_manual_3", limit=5)
    assert recs_revoked[0].get("interests") is None

    # 3. Re-grant consent, but trigger global personalization opt-out
    service.set_manual_interest_consent("u_manual_3", True)
    service.save_privacy_settings("u_manual_3", {"personalization_enabled": False})
    recs_opt_out = service.get_recommendations("u_manual_3", limit=5)
    assert recs_opt_out[0].get("interests") is None


def test_manual_interest_ranking_influence_and_dealbreakers():
    user = {
        "id": "u_manual_rank", "age": 29, "sex": "m", "orientation": "straight",
        "job": "software engineer", "education": "master", "smokes": "never",
    }
    cand_match = {
        "id": "c_has_manual_int", "age": 28, "sex": "f", "orientation": "straight",
        "job": "software engineer", "education": "master", "smokes": "never",
        "interests": ["rock_climbing"],
    }
    cand_nomatch = {
        "id": "c_no_manual_int", "age": 28, "sex": "f", "orientation": "straight",
        "job": "software engineer", "education": "master", "smokes": "never",
        "interests": ["pottery"],
    }
    cand_smoker = {
        "id": "c_dealbreaker_smoker", "age": 28, "sex": "f", "orientation": "straight",
        "job": "software engineer", "education": "master", "smokes": "regularly",
        "interests": ["rock_climbing"],  # 100% manual interest match, but dealbreaker!
    }

    # Isolated staging configuration with weight 0.05
    cfg = dict(RecommendationModel().compatibility.config)
    cfg_weights = dict(cfg["final_ranking"]["weights"])
    cfg_weights["interests"] = 0.05
    cfg["final_ranking"]["weights"] = cfg_weights

    model = RecommendationModel(config=cfg)
    repo = InMemoryRecommendationRepository([user, cand_match, cand_nomatch, cand_smoker])
    repo.save_user_preferences("u_manual_rank", {
        "criteria": {
            "smokes": {"values": ["never"], "hard": True},
        }
    })

    service = RecommendationService(model.compatibility, repo, clock=lambda: NOW)
    service.recommender = model

    service.add_manual_interest("u_manual_rank", "Rock Climbing")

    recs = service.get_recommendations("u_manual_rank", limit=10)
    rec_ids = [str(r.get("candidate_id", r.get("id"))) for r in recs]

    # Dealbreaker candidate is strictly excluded
    assert "c_dealbreaker_smoker" not in rec_ids
    assert len(recs) == 2

    # Matching candidate is boosted over non-matching candidate
    assert rec_ids[0] == "c_has_manual_int"
    assert rec_ids[1] == "c_no_manual_int"

    # Explanation reveals User Selected provenance
    expl = service.explain_candidate("u_manual_rank", "c_has_manual_int")
    ext_matches = [m for m in expl["matched_preferences"] if m.get("direction") == "external_interest"]
    assert len(ext_matches) == 1
    assert "Manual Entry" in ext_matches[0]["providers"]
    assert ext_matches[0]["confidence"] == 1.0


def test_manual_interest_fastapi_endpoints():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dating_ml_model.backend_integration_example import create_app

    user = {"id": "api_manual_user", "age": 29, "sex": "f", "orientation": "straight"}
    repo = InMemoryRecommendationRepository([user])
    app = create_app(repo)
    client = TestClient(app)

    # 1. Add single manual interest
    resp_add = client.post(
        "/users/api_manual_user/interests/manual",
        json={"name": "Specialty Coffee", "category": "culinary", "user_confirmed": True},
    )
    assert resp_add.status_code == 200
    assert resp_add.json()["interest"]["canonical_token"] == "interest_tag:specialty_coffee"

    # 2. Batch add
    resp_batch = client.post(
        "/users/api_manual_user/interests/manual",
        json={"interests": ["Rock Climbing", "Jazz"]},
    )
    assert resp_batch.status_code == 200
    assert resp_batch.json()["total_manual_interests"] == 3

    # 3. Retrieve
    resp_get = client.get("/users/api_manual_user/interests/manual")
    assert resp_get.status_code == 200
    assert len(resp_get.json()) == 3

    # 4. Confirm interest
    resp_confirm = client.put(
        "/users/api_manual_user/interests/interest_tag:jazz/confirm",
        json={"confirmed": True},
    )
    assert resp_confirm.status_code == 200
    assert resp_confirm.json()["user_confirmed"] is True

    # 5. Consent toggle
    resp_consent = client.put(
        "/users/api_manual_user/interests/manual/consent",
        json={"consent": False},
    )
    assert resp_consent.status_code == 200
    assert resp_consent.json()["consent"] is False

    # 6. Delete single
    resp_del_one = client.delete("/users/api_manual_user/interests/manual/interest_tag:jazz")
    assert resp_del_one.status_code == 200
    assert resp_del_one.json()["removed"] is True

    # 7. Delete all
    resp_del_all = client.delete("/users/api_manual_user/interests/manual")
    assert resp_del_all.status_code == 200
    assert resp_del_all.json()["deleted_count"] == 2

    # Verify empty
    resp_empty = client.get("/users/api_manual_user/interests/manual")
    assert len(resp_empty.json()) == 0

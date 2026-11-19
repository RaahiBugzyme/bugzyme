"""Minimal FastAPI integration. Layering:  API -> MatchingService -> CompatibilityModel -> Engine -> Repository.

Run:  uvicorn dating_ml_model.backend_integration_example:app --reload
(Replace CsvProfileRepository with your database-backed ProfileRepository.)
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from datetime import datetime
from typing import Callable

from .model import CompatibilityModel
from .repository import CsvProfileRepository, ProfileRepository, RecommendationRepository
from .service import MatchingService, RecommendationService


class PairRequest(BaseModel):
    profile_a: Dict[str, Any]
    profile_b: Dict[str, Any]
    preferences_a: Optional[Dict[str, Any]] = None
    preferences_b: Optional[Dict[str, Any]] = None


class InteractionRequest(BaseModel):
    user_id: str
    candidate_id: Optional[str] = None
    action: Optional[str] = None
    event_type: Optional[str] = None
    timestamp: Optional[Any] = None
    session_id: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    search_criteria: Optional[Dict[str, Any]] = None


class PreferenceInterpretRequest(BaseModel):
    request: str


class PreferenceConfirmation(BaseModel):
    preferences: Dict[str, Any]
    confirmed: bool


class ExternalInterestImportRequest(BaseModel):
    payload: Dict[str, Any]
    user_confirmed: bool = False


class ExternalInterestConsentRequest(BaseModel):
    consent: bool


class ManualInterestAddRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    user_confirmed: bool = True
    interests: Optional[List[Any]] = None


class ManualInterestConfirmRequest(BaseModel):
    confirmed: bool = True


class ManualInterestConsentRequest(BaseModel):
    consent: bool


def create_app(repository: ProfileRepository, model: Optional[CompatibilityModel] = None,
               clock: Optional[Callable[[], datetime]] = None,
               preference_ai_client: Optional[Callable[[str], Any]] = None) -> FastAPI:
    """Existing endpoints work with any ProfileRepository. The v2.2 endpoints need a RecommendationRepository."""
    model = model or CompatibilityModel()
    service = MatchingService(model, repository)
    extended = (RecommendationService(model, repository, clock=clock,
                                       preference_ai_client=preference_ai_client)
                if isinstance(repository, RecommendationRepository) else None)

    def need_extended() -> RecommendationService:
        if extended is None:
            raise HTTPException(status_code=501, detail="repository does not support interactions/preferences")
        return extended

    def guarded(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
    app = FastAPI(title="Dating ML V2.1 compatibility service")

    @app.post("/compatibility/pair")
    def pair(request: PairRequest):
        if extended is not None:
            return extended.predict_pair(
                request.profile_a, request.profile_b,
                preferences_a=request.preferences_a, preferences_b=request.preferences_b
            )
        return service.predict_pair(request.profile_a, request.profile_b)

    @app.get("/matches/{user_id}")
    def matches(user_id: str, top_k: int = 10):
        try:
            return service.get_matches(user_id, top_k)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))

    @app.post("/interactions")
    def post_interaction(request: InteractionRequest):
        return guarded(need_extended().record_interaction, request.model_dump())

    @app.get("/users/{user_id}/preferences")
    def get_preferences(user_id: str):
        return guarded(need_extended().get_preferences, user_id)

    @app.put("/users/{user_id}/preferences")
    def put_preferences(user_id: str, preferences: Dict[str, Any]):
        return guarded(need_extended().save_preferences, user_id, preferences)

    @app.get("/users/{user_id}/recommendations")
    def recommendations(user_id: str, limit: int = 20):
        return guarded(need_extended().get_recommendations, user_id, limit)

    @app.post("/users/{user_id}/blocks/{blocked_user_id}")
    def block(user_id: str, blocked_user_id: str):
        return guarded(need_extended().block_user, user_id, blocked_user_id)

    @app.delete("/users/{user_id}/blocks/{blocked_user_id}")
    def unblock(user_id: str, blocked_user_id: str):
        return guarded(need_extended().unblock_user, user_id, blocked_user_id)

    @app.get("/users/{user_id}/blocks")
    def blocks(user_id: str):
        return guarded(need_extended().get_blocked_users, user_id)

    @app.post("/users/{user_id}/search")
    def search(user_id: str, preferences: Optional[Dict[str, Any]] = None):
        return guarded(need_extended().search_profiles, user_id, preferences)

    @app.post("/users/{user_id}/preferences/interpret")
    def interpret(user_id: str, request: PreferenceInterpretRequest):
        return guarded(need_extended().interpret_preferences, user_id, request.request)

    @app.post("/users/{user_id}/preferences/confirm")
    def confirm(user_id: str, request: PreferenceConfirmation):
        return guarded(need_extended().confirm_interpreted_preferences, user_id, request.model_dump())

    @app.get("/users/{user_id}/behavior-summary")
    def behavior_summary(user_id: str):
        return guarded(need_extended().get_behavior_summary, user_id)

    @app.get("/users/{user_id}/search-intent")
    def search_intent(user_id: str):
        return guarded(need_extended().get_search_intent, user_id)

    @app.get("/users/{user_id}/preference-profile")
    def preference_profile(user_id: str):
        return guarded(need_extended().get_preference_profile, user_id)

    @app.get("/users/{user_id}/recommendations/{candidate_id}/explain")
    def explain_recommendation_endpoint(user_id: str, candidate_id: str):
        return guarded(need_extended().explain_candidate, user_id, candidate_id)

    @app.post("/compatibility/pair/explain")
    def pair_explain(request: PairRequest):
        if extended is not None:
            return guarded(
                extended.explain_pair,
                request.profile_a, request.profile_b,
                preferences_a=request.preferences_a, preferences_b=request.preferences_b
            )
        return guarded(service.explain_pair, request.profile_a, request.profile_b)

    @app.get("/users/{user_id}/personality")
    def get_personality(user_id: str):
        return guarded(need_extended().get_user_personality, user_id)

    @app.put("/users/{user_id}/personality")
    def put_personality(user_id: str, personality: Dict[str, Any]):
        return guarded(need_extended().save_user_personality, user_id, personality)

    @app.get("/users/{user_id}/privacy-settings")
    def get_privacy_settings(user_id: str):
        return guarded(need_extended().get_privacy_settings, user_id)

    @app.put("/users/{user_id}/privacy-settings")
    def put_privacy_settings(user_id: str, settings: Dict[str, Any]):
        return guarded(need_extended().save_privacy_settings, user_id, settings)

    @app.delete("/users/{user_id}/interactions")
    def delete_interactions(user_id: str):
        return guarded(need_extended().delete_interactions, user_id)

    @app.get("/users/{user_id}/interest-profile")
    def get_interest_profile(user_id: str):
        return guarded(need_extended().get_interest_profile, user_id)

    @app.post("/users/{user_id}/external-interests/{provider}/import")
    def import_external_interests_endpoint(user_id: str, provider: str, request: ExternalInterestImportRequest):
        return guarded(
            need_extended().import_external_interests,
            user_id, provider, request.payload, user_confirmed=request.user_confirmed,
        )

    @app.get("/users/{user_id}/external-interests")
    def get_external_interests_endpoint(user_id: str, provider: Optional[str] = None):
        return guarded(need_extended().get_external_interests, user_id, provider=provider)

    @app.delete("/users/{user_id}/external-interests")
    def delete_external_interests_endpoint(user_id: str, provider: Optional[str] = None):
        return guarded(need_extended().delete_external_interests, user_id, provider=provider)

    @app.put("/users/{user_id}/external-interests/{provider}/consent")
    def set_external_interest_consent_endpoint(user_id: str, provider: str, request: ExternalInterestConsentRequest):
        return guarded(need_extended().set_external_interest_consent, user_id, provider, request.consent)

    @app.get("/users/{user_id}/external-accounts")
    def get_external_accounts_endpoint(user_id: str):
        return guarded(need_extended().get_external_accounts, user_id)

    @app.post("/users/{user_id}/interests/manual")
    def add_manual_interest_endpoint(user_id: str, request: ManualInterestAddRequest):
        if request.interests is not None:
            return guarded(need_extended().add_manual_interests, user_id, request.interests)
        if request.name is not None:
            return guarded(need_extended().add_manual_interest, user_id, request.name, category=request.category, user_confirmed=request.user_confirmed)
        raise HTTPException(status_code=400, detail="Must provide 'name' or 'interests'")

    @app.get("/users/{user_id}/interests/manual")
    def get_manual_interests_endpoint(user_id: str):
        return guarded(need_extended().get_manual_interests, user_id)

    @app.delete("/users/{user_id}/interests/manual/{token_or_name}")
    def remove_manual_interest_endpoint(user_id: str, token_or_name: str):
        return guarded(need_extended().remove_manual_interest, user_id, token_or_name)

    @app.delete("/users/{user_id}/interests/manual")
    def delete_manual_interests_endpoint(user_id: str):
        return guarded(need_extended().delete_manual_interests, user_id)

    @app.put("/users/{user_id}/interests/{token_or_name}/confirm")
    def confirm_interest_endpoint(user_id: str, token_or_name: str, request: ManualInterestConfirmRequest):
        return guarded(need_extended().confirm_interest, user_id, token_or_name, confirmed=request.confirmed)

    @app.put("/users/{user_id}/interests/manual/consent")
    def set_manual_interest_consent_endpoint(user_id: str, request: ManualInterestConsentRequest):
        return guarded(need_extended().set_manual_interest_consent, user_id, request.consent)

    return app


# `uvicorn ...:app` entry point; set PROFILES_CSV to your data (dev only).
if os.environ.get("PROFILES_CSV"):
    app = create_app(CsvProfileRepository(os.environ["PROFILES_CSV"], id_column=os.environ.get("PROFILES_ID_COLUMN")))

"""Machine-readable contracts (JSON Schema files in this folder) + light validators (no extra dependencies)."""
import json
from pathlib import Path
from typing import Any, Dict

from ..behavior import EVENT_CONTRACT, SUPPORTED_ACTIONS, validate_event  # noqa: F401  (re-exported for convenience)
from ..preferences import normalize_preferences  # noqa: F401

SCHEMA_DIR = Path(__file__).parent


def load_schema(name: str) -> Dict[str, Any]:
    """name in {'interaction_event', 'user_preferences', 'recommendation'}"""
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def build_feature_schema(dataset_audit=None) -> Dict[str, Any]:
    """feature_schema.json (v2.2.0). status in {required, optional, derived, behavioral, future}.
    `dataset_audit` = per-column statistics of the profile dataset (kept from v2.1.0, previously the whole file)."""
    f = lambda name, typ, status, desc: {"name": name, "type": typ, "status": status, "description": desc}
    return {
        "schema_version": "2.2.0",
        "status_legend": {"required": "needed for eligibility", "optional": "improves scoring when present; unknown is never a penalty",
                          "derived": "computed by the package", "behavioral": "comes from interaction events", "future": "accepted/stored, not used yet"},
        "profile_features": [
            f("id", "string", "required", "stable user id (repository)"),
            f("age", "number", "required", "adult check (>=18) and demographics"),
            f("sex", "string m|f", "required", "eligibility"), f("orientation", "string straight|gay|bisexual", "required", "eligibility"),
            f("education", "string", "optional", "ordinal rank"), f("job", "string", "optional", "exact + broad profession group"),
            f("religion", "string", "optional", "base religion"), f("ethnicity", "string (comma separated)", "optional", "Jaccard overlap; can be disabled"),
            f("drinks", "string", "optional", "ordinal"), f("drugs", "string", "optional", "ordinal"), f("smokes", "string", "optional", "ordinal"),
            f("diet", "string", "optional", "base diet"), f("offspring", "string", "optional", "children stance yes/maybe/no"),
            f("pets", "string", "optional", "dog/cat attitudes"), f("height", "number inches", "optional", "attraction (80%)"),
            f("body_type", "string", "optional", "attraction (20%)"),
            f("relationship_intention", "string long_term|serious|marriage|casual|friendship|unsure", "optional", "stated intention alignment"),
            f("birth_year / derived_generation", "number / string", "optional", "overrides age-derived generation"),
            f("income, speaks, sign, status", "-", "future", "deliberately not scored"),
        ],
        "preference_features": [
            f("preferred_distance_km", "number>0", "optional", "SOFT distance preference (scales the location curve)"),
            f("max_distance_km", "number>0", "optional", "HARD limit; applied only when set; unknown location never excluded"),
            f("criteria.<age|height|education|profession|profession_group|religion|ethnicity|drinks|drugs|smokes|diet|children|pets|body_type|body_type_group|relationship_intention>",
              "object {min,max|min_rank|values, hard}", "optional", "hard=true can exclude; hard=false only re-ranks; missing = no preference"),
        ],
        "location_features": [
            f("latitude, longitude", "number", "optional", "both required and valid; otherwise ignored with a warning"),
            f("city, state|region, country, location(free text)", "string", "optional", "resolved ONLY via the gazetteer; unresolved => no score"),
        ],
        "behavior_features": [
            f("interaction.user_id, candidate_id, action|event_type, timestamp, session_id, source, metadata, search_criteria", "event", "behavioral",
              "VIEW/SEARCH informational; LIKE/SUPER_LIKE/SAVE positive intent; PASS negative intent; MATCH/UNMATCH relationship state; MESSAGE conversation"),
        ],
        "derived_features": [
            f("derived_generation", "string", "derived", "from reference_year - age"),
            f("education_rank, profession_group, religion_base, diet_base, children_stance, pets_liked, body_type_group", "mixed", "derived", "normalized attributes"),
            f("component similarities (14)", "number 0..1|null", "derived", "null = unknown"),
            f("behavior tokens (profession_group, education_level, religion, ethnicity, drinks, drugs, smokes, diet, children, body_type_group, generation, relationship_intention, age/height difference bins, distance bin)",
              "categorical", "derived", "learned preferences are keyed by these, never by candidate id"),
        ],
        "model_outputs": [
            f("compatibility.score|confidence|adjusted_score|categories|components", "numbers 0..100", "derived", "profile alignment; NOT a relationship-success probability"),
            f("location.distance_km|location_score|location_confidence|location_status|within_*", "number|null", "derived", "status known|partial_unknown|unknown|unresolved|coarse|disabled"),
            f("preferences.score|confidence|status", "number|null", "derived", "status known|no_preferences|unknown"),
            f("relationship_intention.score|status", "number|null", "derived", "alignment of STATED intentions"),
            f("behavior.score|confidence|status|evidence_count", "number|null", "behavioral", "status cold_start|insufficient_data|sufficient_data|no_applicable_evidence|disabled"),
            f("mutual_interest.probability|confidence|status", "number|null", "behavioral", "only with a model trained on genuine interaction logs"),
            f("ranking.final_score|components", "number|null", "derived", "weights are configurable placeholders, not validated"),
            f("explanation", "list[string]", "derived", "deterministic, derived from the signals above"),
        ],
        "dataset_audit": dataset_audit or [],
    }

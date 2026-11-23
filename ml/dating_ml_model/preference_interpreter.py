"""Safe natural-language preference interpretation with an injectable Gen AI client."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, Optional

from .preferences import normalize_preferences

SUPPORTED_FIELDS = ("region", "religion", "profession")
_CLARIFICATION = "Do you want a region, religion, or profession, and what exact value should be used?"
_RESPONSE_SCHEMA = {
    "type": "object",
    "propertyOrdering": ["status", "question", "preferences"],
    "properties": {
        "status": {"type": "string", "enum": ["clarification_required", "confirmation_required"]},
        "question": {"type": "string"},
        "preferences": {
            "type": "object",
            "propertyOrdering": ["criteria", "hard_exclusions"],
            "properties": {
                "criteria": {
                    "type": "object",
                    "properties": {
                        field: {
                            "type": "object",
                            "propertyOrdering": ["values", "hard"],
                            "properties": {
                                "values": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                "hard": {"type": "boolean"},
                            },
                            "required": ["values", "hard"],
                        }
                        for field in SUPPORTED_FIELDS
                    },
                },
                "hard_exclusions": {
                    "type": "object",
                    "properties": {
                        field: {
                            "type": "object",
                            "propertyOrdering": ["values"],
                            "properties": {"values": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
                            "required": ["values"],
                        }
                        for field in SUPPORTED_FIELDS
                    },
                },
            },
        },
    },
    "required": ["status"],
}


def _local_interpret(request: str) -> Dict[str, Any]:
    text = request.strip().lower()
    if not text:
        return {"status": "clarification_required", "question": _CLARIFICATION}
    if "konkani" in text:
        return {
            "status": "clarification_required",
            "question": "Do you mean Konkani as a religion/language or a specific region? Please provide the exact field and value.",
        }

    field = next((f for f in SUPPORTED_FIELDS if f in text), None)
    exclusion = re.search(r"\b(?:exclude|avoid|not|don't want)\s+(?P<value>[a-z][a-z -]+?)(?:\s+(?:region|religion|profession))?(?:$|\.)", text)
    if exclusion and field:
        value = re.sub(r"\s+(region|religion|profession)$", "", exclusion.group("value")).strip()
        value = re.sub(r"^the\s+", "", value).strip()
        return {"status": "confirmation_required", "preferences": {"hard_exclusions": {field: {"values": [value]}}}}

    preference = re.search(r"\b(?:prefer|like|want)\s+(?:people|someone|a person)?\s*(?:from|who is|working as)?\s*(?P<value>[a-z][a-z -]+?)(?:\s+(?:region|religion|profession))?(?:$|\.)", text)
    if preference and field and preference.group("value").strip() not in {"my", "my region", "my religion"}:
        value = re.sub(r"\s+(region|religion|profession)$", "", preference.group("value")).strip()
        return {"status": "confirmation_required", "preferences": {"criteria": {field: {"values": [value], "hard": False}}}}
    return {"status": "clarification_required", "question": _CLARIFICATION}


class GeminiProviderUnavailable(RuntimeError):
    """Raised when Gemini cannot be configured or reached."""


class GeminiPreferenceClient:
    """Backend-only adapter for the official google-genai SDK."""

    def __init__(self, api_key: str, model: Optional[str] = None):
        try:
            from google import genai
        except ImportError as error:
            raise GeminiProviderUnavailable("google-genai is not installed") from error
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        try:
            self._client = genai.Client(api_key=api_key)
        except Exception as error:
            raise GeminiProviderUnavailable("Gemini client could not be initialized") from error

    def __call__(self, request: str) -> Any:
        prompt = (
            "Interpret this dating preference request. Return JSON only with exactly one of these shapes: "
            '{"status":"clarification_required","question":"..."} or '
            '{"status":"confirmation_required","preferences":{...}}. '
            "Only use region, religion, and profession. Put exclusions in hard_exclusions; "
            "put non-exclusive preferences in criteria with hard:false. Never infer a value or equate "
            "similarly named terms such as Konkani and Konkan; ask a clarification instead. "
            "Do not include markdown or extra keys. Request: " + request
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": _RESPONSE_SCHEMA,
                },
            )
            return _parse_json_response(getattr(response, "text", None))
        except (GeminiProviderUnavailable, ValueError):
            raise
        except Exception as error:
            raise GeminiProviderUnavailable("Gemini request failed") from error


def _parse_json_response(text: str) -> Dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("Gemini response must be JSON text")
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError("Gemini response is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("Gemini response must be a JSON object")
    return value


def _validate_ai_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Reject provider output that is outside the deliberately small contract."""
    if set(raw) - {"status", "question", "preferences"}:
        raise ValueError("AI response contains unsupported fields")
    if raw["status"] == "clarification_required":
        if set(raw) - {"status", "question"}:
            raise ValueError("clarification response contains unsupported fields")
        return raw
    preferences = raw.get("preferences")
    if not isinstance(preferences, dict) or set(preferences) - {"criteria", "hard_exclusions"}:
        raise ValueError("AI preferences must contain only criteria or hard_exclusions")
    cleaned_preferences: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for group, specs in preferences.items():
        if not isinstance(specs, dict):
            raise ValueError("AI preference groups must be objects")
        for field, spec in specs.items():
            if field not in SUPPORTED_FIELDS or not isinstance(spec, dict):
                raise ValueError("AI response contains an unsupported preference field")
            allowed = {"values", "hard"} if group == "criteria" else {"values"}
            if set(spec) - allowed or not isinstance(spec.get("values"), list):
                raise ValueError("AI response contains an unsupported preference operator")
            if group == "criteria" and not isinstance(spec.get("hard"), bool):
                raise ValueError("AI criteria must declare hard as a boolean")
            if any(not isinstance(value, str) or not value.strip() for value in spec["values"]):
                raise ValueError("AI response contains an invalid preference value")
            if not spec["values"]:
                continue
            cleaned_preferences.setdefault(group, {})[field] = dict(spec)
    return {**raw, "preferences": cleaned_preferences}


def _configured_client() -> Optional[Callable[[str], Any]]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        return GeminiPreferenceClient(api_key)
    except GeminiProviderUnavailable:
        return None


def interpret_preference_request(request: str, ai_client: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    if not isinstance(request, str):
        raise ValueError("request must be text")
    client = ai_client or _configured_client()
    if client is None:
        raw = _local_interpret(request)
    else:
        try:
            raw = client(request)
        except GeminiProviderUnavailable:
            raw = _local_interpret(request)
    if not isinstance(raw, dict) or raw.get("status") not in {"clarification_required", "confirmation_required"}:
        raise ValueError("AI response must be a structured clarification or interpretation")
    raw = _validate_ai_shape(raw)
    if raw["status"] == "clarification_required":
        if not isinstance(raw.get("question"), str) or not raw["question"].strip():
            raise ValueError("AI clarification must include a question")
        return {"status": raw["status"], "question": raw["question"]}
    normalized, warnings = normalize_preferences(raw.get("preferences"))
    if warnings or not (normalized["hard_exclusions"] or normalized["criteria"]):
        raise ValueError("AI response contains unsupported or invalid preferences")
    return {"status": "confirmation_required", "preferences": normalized, "confirmed": False}


# ---------------------------------------------------------------------------
# Extended preference interpreter (v3 expansion)
# ---------------------------------------------------------------------------
# Adds support for model-compatible fields beyond the original three.
# SUPPORTED_FIELDS and GeminiPreferenceClient remain UNCHANGED.
# This function uses a separate schema and validator so that the original
# three-field path is never broken.
# ---------------------------------------------------------------------------

EXTENDED_RANGE_FIELDS = ("age", "height", "education")
EXTENDED_SET_FIELDS = ("profession", "profession_group", "religion", "ethnicity",
                       "drinks", "drugs", "smokes", "diet", "children",
                       "pets", "body_type", "body_type_group",
                       "relationship_intention", "region")
EXTENDED_HARD_EXCLUSION_FIELDS = ("region", "religion", "profession")

_EXTENDED_RESPONSE_SCHEMA = {
    "type": "object",
    "propertyOrdering": ["status", "question", "preferences"],
    "properties": {
        "status": {"type": "string", "enum": ["clarification_required", "confirmation_required"]},
        "question": {"type": "string"},
        "preferences": {
            "type": "object",
            "propertyOrdering": ["criteria", "hard_exclusions"],
            "properties": {
                "criteria": {
                    "type": "object",
                    "properties": {
                        **{
                            field: {
                                "type": "object",
                                "propertyOrdering": ["min", "max", "hard"],
                                "properties": {
                                    "min": {"type": "number"},
                                    "max": {"type": "number"},
                                    "hard": {"type": "boolean"},
                                },
                                "required": ["hard"],
                            }
                            for field in ("age", "height")
                        },
                        "education": {
                            "type": "object",
                            "propertyOrdering": ["min_rank", "hard"],
                            "properties": {
                                "min_rank": {"type": "number"},
                                "min": {"type": "number"},
                                "hard": {"type": "boolean"},
                            },
                            "required": ["hard"],
                        },
                        **{
                            field: {
                                "type": "object",
                                "propertyOrdering": ["values", "hard"],
                                "properties": {
                                    "values": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                    "hard": {"type": "boolean"},
                                },
                                "required": ["values", "hard"],
                            }
                            for field in EXTENDED_SET_FIELDS
                        },
                    },
                },
                "hard_exclusions": {
                    "type": "object",
                    "properties": {
                        field: {
                            "type": "object",
                            "propertyOrdering": ["values"],
                            "properties": {
                                "values": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                            },
                            "required": ["values"],
                        }
                        for field in EXTENDED_HARD_EXCLUSION_FIELDS
                    },
                },
            },
        },
    },
    "required": ["status"],
}

_ALL_EXTENDED_FIELDS = set(EXTENDED_RANGE_FIELDS) | set(EXTENDED_SET_FIELDS)


def _validate_extended_ai_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate extended-schema AI output — stricter whitelist for v3 fields."""
    if set(raw) - {"status", "question", "preferences"}:
        raise ValueError("Extended AI response contains unsupported top-level fields")
    if raw["status"] == "clarification_required":
        if set(raw) - {"status", "question"}:
            raise ValueError("Extended clarification response contains unsupported fields")
        return raw
    preferences = raw.get("preferences")
    if not isinstance(preferences, dict) or set(preferences) - {"criteria", "hard_exclusions"}:
        raise ValueError("Extended AI preferences must contain only criteria or hard_exclusions")

    cleaned: Dict[str, Dict[str, Any]] = {}

    # Validate criteria
    for field, spec in (preferences.get("criteria") or {}).items():
        if field not in _ALL_EXTENDED_FIELDS or not isinstance(spec, dict):
            raise ValueError(f"Extended AI response contains unsupported preference field: {field!r}")
        if not isinstance(spec.get("hard"), bool):
            raise ValueError(f"Extended AI criteria for {field!r} must declare hard as a boolean")
        if field in ("age", "height"):
            lo, hi = spec.get("min"), spec.get("max")
            if lo is None and hi is None:
                raise ValueError(f"Range criterion {field!r} requires min or max")
            # coerce to float
            cleaned.setdefault("criteria", {})[field] = {
                "min": None if lo is None else float(lo),
                "max": None if hi is None else float(hi),
                "hard": bool(spec["hard"]),
            }
        elif field == "education":
            rank = spec.get("min_rank") if spec.get("min_rank") is not None else spec.get("min")
            if rank is None:
                raise ValueError("Education criterion requires min_rank or min")
            cleaned.setdefault("criteria", {})["education"] = {
                "min_rank": float(rank),
                "hard": bool(spec["hard"]),
            }
        else:
            values = spec.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError(f"Set criterion {field!r} requires a non-empty values list")
            if any(not isinstance(v, str) or not str(v).strip() for v in values):
                raise ValueError(f"Set criterion {field!r} contains an invalid value")
            cleaned.setdefault("criteria", {})[field] = {
                "values": [str(v) for v in values],
                "hard": bool(spec["hard"]),
            }

    # Validate hard_exclusions
    for field, spec in (preferences.get("hard_exclusions") or {}).items():
        if field not in EXTENDED_HARD_EXCLUSION_FIELDS or not isinstance(spec, dict):
            raise ValueError(f"Extended AI response contains unsupported hard_exclusion field: {field!r}")
        values = spec.get("values")
        if not isinstance(values, list) or not values:
            continue  # skip empty exclusions
        if any(not isinstance(v, str) or not str(v).strip() for v in values):
            raise ValueError(f"Hard exclusion {field!r} contains an invalid value")
        cleaned.setdefault("hard_exclusions", {})[field] = {"values": [str(v) for v in values]}

    return {**raw, "preferences": cleaned}


def _local_interpret_extended(request: str) -> Dict[str, Any]:
    """Regex fallback for extended fields. Handles age ranges, lifestyle, and intent."""
    text = request.strip().lower()
    if not text:
        return {"status": "clarification_required", "question": "Please describe the preference you want to set."}

    # Age range: "between 25 and 35" / "at least 25" / "under 40" / "ages 25 to 35"
    age_range = re.search(
        r"(?:age(?:s|d)?|between)[\s:]*(\d{1,3})\s*(?:to|and|-)\s*(\d{1,3})", text
    )
    if age_range:
        lo, hi = int(age_range.group(1)), int(age_range.group(2))
        if 18 <= lo <= hi <= 100:
            return {
                "status": "confirmation_required",
                "preferences": {"criteria": {"age": {"min": float(lo), "max": float(hi), "hard": False}}},
            }

    age_min = re.search(r"(?:at least|older than|above)\s+(\d{1,3})\s*(?:years?)?", text)
    if age_min:
        lo = int(age_min.group(1))
        if 18 <= lo <= 100:
            return {
                "status": "confirmation_required",
                "preferences": {"criteria": {"age": {"min": float(lo), "max": None, "hard": False}}},
            }

    age_max = re.search(r"(?:under|younger than|below|no older than)\s+(\d{1,3})\s*(?:years?)?", text)
    if age_max:
        hi = int(age_max.group(1))
        if 18 <= hi <= 100:
            return {
                "status": "confirmation_required",
                "preferences": {"criteria": {"age": {"min": None, "max": float(hi), "hard": False}}},
            }

    # Relationship intention
    for intent_token, canon in (
        ("long.?term", "long_term"), ("serious", "serious"), ("marriage", "marriage"),
        ("casual", "casual"), ("friendship", "friendship"), ("unsure", "unsure"),
    ):
        if re.search(rf"\b{intent_token}\b", text):
            return {
                "status": "confirmation_required",
                "preferences": {"criteria": {"relationship_intention": {"values": [canon], "hard": False}}},
            }

    # Diet
    for diet_token, canon in (
        ("vegan", "vegan"), ("vegetarian", "vegetarian"), ("halal", "halal"),
        ("kosher", "kosher"), ("anything", "anything"),
    ):
        if diet_token in text:
            return {
                "status": "confirmation_required",
                "preferences": {"criteria": {"diet": {"values": [canon], "hard": False}}},
            }

    # Smoking / drinking / drugs exclusion
    if re.search(r"\b(?:non.?smok|no smok|doesn't? smok|doesn't? smoke)", text):
        return {
            "status": "confirmation_required",
            "preferences": {"criteria": {"smokes": {"values": ["no"], "hard": False}}},
        }
    if re.search(r"\b(?:non.?drink|doesn't? drink|no alcohol)", text):
        return {
            "status": "confirmation_required",
            "preferences": {"criteria": {"drinks": {"values": ["not at all", "rarely"], "hard": False}}},
        }
    if re.search(r"\b(?:no drugs|drug.?free|doesn't? use drugs)", text):
        return {
            "status": "confirmation_required",
            "preferences": {"criteria": {"drugs": {"values": ["never"], "hard": False}}},
        }

    # Children
    if re.search(r"\b(?:want[s]? kids?|want[s]? children)", text):
        return {
            "status": "confirmation_required",
            "preferences": {"criteria": {"children": {"values": ["yes"], "hard": False}}},
        }
    if re.search(r"\b(?:doesn't? want kids?|no kids?|child.?free)", text):
        return {
            "status": "confirmation_required",
            "preferences": {"criteria": {"children": {"values": ["no"], "hard": False}}},
        }

    # Fall back to the original three-field local interpreter
    return _local_interpret(request)


def interpret_extended_preference_request(
    request: str,
    ai_client: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Extended NL preference interpretation supporting 15+ model-compatible fields.

    Handles: age (range), height (range), education (rank), profession,
    profession_group, religion, ethnicity, drinks, drugs, smokes, diet,
    children, pets, body_type, body_type_group, relationship_intention, region.

    Hard exclusions remain restricted to: region, religion, profession.

    The Gemini client is used when GEMINI_API_KEY is set; otherwise falls back
    to the deterministic extended local interpreter. The result always requires
    explicit user confirmation before being persisted.
    """
    if not isinstance(request, str):
        raise ValueError("request must be text")

    client = ai_client or _configured_client()

    if client is None:
        raw = _local_interpret_extended(request)
    else:
        extended_prompt = (
            "Interpret this dating preference request for an expanded set of fields. "
            "Return JSON only with exactly one of these shapes: "
            '{"status":"clarification_required","question":"..."} or '
            '{"status":"confirmation_required","preferences":{...}}. '
            "Supported criteria fields: age (range with min/max numbers), height (range), "
            "education (range with min/max rank 1-5), profession, profession_group, religion, "
            "ethnicity, drinks, drugs, smokes, diet, children, pets, body_type, "
            "body_type_group, relationship_intention, region. "
            "Hard exclusions only for: region, religion, profession. "
            "Each criterion must include a boolean hard field. "
            "Range fields (age, height, education) use min/max numbers. "
            "Set fields use values arrays of strings. "
            "Never infer ambiguous values; ask for clarification instead. "
            "Do not include markdown or extra keys. Request: " + request
        )
        try:
            raw = client(extended_prompt)
        except GeminiProviderUnavailable:
            raw = _local_interpret_extended(request)

    if not isinstance(raw, dict) or raw.get("status") not in {"clarification_required", "confirmation_required"}:
        raise ValueError("AI response must be a structured clarification or interpretation")

    raw = _validate_extended_ai_shape(raw)

    if raw["status"] == "clarification_required":
        if not isinstance(raw.get("question"), str) or not raw["question"].strip():
            raise ValueError("AI clarification must include a question")
        return {"status": raw["status"], "question": raw["question"]}

    normalized, warnings = normalize_preferences(raw.get("preferences") or {})
    if warnings or not (normalized.get("hard_exclusions") or normalized.get("criteria")):
        raise ValueError("Extended AI response contains unsupported or invalid preferences")
    return {"status": "confirmation_required", "preferences": normalized, "confirmed": False}

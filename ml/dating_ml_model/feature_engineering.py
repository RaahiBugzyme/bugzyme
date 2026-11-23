"""Feature engineering primitives for Dating ML V2.1.

Every function is pure and deterministic. Every similarity function returns a
float in [0, 1], or ``None`` when either side is unknown. Missing data is NEVER
converted to a mismatch (0.0).
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional, Set

MISSING_TOKENS = frozenset(
    {"", "nan", "none", "null", "unknown", "not specified", "rather not say", "n/a", "na"}
)


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------
def is_missing(value: Any) -> bool:
    """True for None, NaN, pd.NA and placeholder strings such as 'unknown'."""
    if value is None:
        return True
    try:
        if value != value:  # NaN, and pd.NA (raises TypeError on bool())
            return True
    except (TypeError, ValueError):
        return True
    return isinstance(value, str) and value.strip().lower() in MISSING_TOKENS


def norm_text(value: Any) -> Optional[str]:
    """Lower-case, whitespace-collapsed text; None if missing."""
    if is_missing(value):
        return None
    text = str(value).replace("&rsquo;", "'").replace("\u2019", "'")
    text = " ".join(text.strip().lower().split())
    return None if text in MISSING_TOKENS else text


def to_float(value: Any) -> Optional[float]:
    if is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _linear_similarity(a: Optional[float], b: Optional[float], max_gap: float) -> Optional[float]:
    if a is None or b is None:
        return None
    return 1.0 - min(abs(a - b) / float(max_gap), 1.0)


def _exact(a: Optional[str], b: Optional[str]) -> Optional[float]:
    if a is None or b is None:
        return None
    return 1.0 if a == b else 0.0


# --------------------------------------------------------------------------
# Demographics: age + generation
# --------------------------------------------------------------------------
GENERATION_BANDS = (  # (label, first birth year, last birth year)
    ("gen z", 1997, 2012),
    ("zillennial", 1990, 1996),
    ("millennial", 1981, 1989),
    ("gen x", 1965, 1980),
    ("baby boomer+", -10_000, 1964),
)


def clean_age(value: Any) -> Optional[float]:
    age = to_float(value)
    return age if age is not None and 0 < age <= 120 else None


def generation_from_birth_year(birth_year: Optional[float]) -> Optional[str]:
    if birth_year is None:
        return None
    year = int(birth_year)
    for label, first, last in GENERATION_BANDS:
        if first <= year <= last:
            return label
    return None  # born after 2012: outside the defined bands


def derive_generation(profile: Dict[str, Any], reference_year: int) -> Optional[str]:
    """Precedence: supplied `derived_generation`, then `birth_year`, then age."""
    supplied = norm_text(profile.get("derived_generation"))
    if supplied is not None:
        return supplied
    birth_year = to_float(profile.get("birth_year"))
    if birth_year is None:
        age = clean_age(profile.get("age"))
        birth_year = None if age is None else reference_year - age
    return generation_from_birth_year(birth_year)


def age_similarity(a: Any, b: Any, max_gap: float = 20.0) -> Optional[float]:
    return _linear_similarity(clean_age(a), clean_age(b), max_gap)


def generation_similarity(gen_a: Optional[str], gen_b: Optional[str]) -> Optional[float]:
    return _exact(gen_a, gen_b)


# --------------------------------------------------------------------------
# Career & education
# --------------------------------------------------------------------------
_EDU_LEVELS = (
    ("high school", 1.0),
    ("two-year college", 2.0),
    ("college/university", 3.0),
    ("masters program", 4.0),
    ("law school", 4.0),
    ("med school", 4.0),
    ("ph.d program", 5.0),
)


def education_rank(value: Any) -> Optional[float]:
    """Ordinal education rank; 'working on' = -0.5, 'dropped out of' = -1."""
    text = norm_text(value)
    if text is None or "space camp" in text:
        return None
    level = next((lv for key, lv in _EDU_LEVELS if key in text), None)
    if level is None:
        return None
    if text.startswith("working on"):
        return level - 0.5
    if text.startswith("dropped out of"):
        return level - 1.0
    return level


def education_similarity(a: Any, b: Any, max_gap: float = 3.0) -> Optional[float]:
    return _linear_similarity(education_rank(a), education_rank(b), max_gap)


PROFESSION_GROUPS: Dict[str, str] = {
    "science / tech / engineering": "technology_science",
    "computer / hardware / software": "technology_science",
    "banking / financial / real estate": "business_finance",
    "sales / marketing / biz dev": "business_finance",
    "executive / management": "business_finance",
    "artistic / musical / writer": "creative_media",
    "entertainment / media": "creative_media",
    "medicine / health": "health_education",
    "education / academia": "health_education",
    "law / legal services": "law_public_service",
    "political / government": "law_public_service",
    "military": "law_public_service",
    "hospitality / travel": "service_trades",
    "construction / craftsmanship": "service_trades",
    "transportation": "service_trades",
    "clerical / administrative": "service_trades",
    "student": "student",
    "unemployed": "unemployed",
    "retired": "retired",
}


def clean_profession(value: Any) -> Optional[str]:
    text = norm_text(value)
    return None if text in (None, "other") else text  # 'other' carries no information


def profession_similarity(a: Any, b: Any) -> Optional[float]:
    """Exact match = 1.0, same broad group = 0.5, otherwise 0.0."""
    pa, pb = clean_profession(a), clean_profession(b)
    if pa is None or pb is None:
        return None
    if pa == pb:
        return 1.0
    ga, gb = PROFESSION_GROUPS.get(pa), PROFESSION_GROUPS.get(pb)
    return 0.5 if ga is not None and ga == gb else 0.0


# --------------------------------------------------------------------------
# Values & culture
# --------------------------------------------------------------------------
SECULAR = frozenset({"agnosticism", "atheism"})


def religion_base(value: Any) -> Optional[str]:
    """'catholicism and very serious about it' -> 'catholicism'."""
    text = norm_text(value)
    if text is None:
        return None
    base = re.split(r"\s+(?:and|but)\s+", text, maxsplit=1)[0]
    return None if base == "other" else base


def religion_similarity(a: Any, b: Any, secular_credit: float = 0.5) -> Optional[float]:
    ra, rb = religion_base(a), religion_base(b)
    if ra is None or rb is None:
        return None
    if ra == rb:
        return 1.0
    return float(secular_credit) if ra in SECULAR and rb in SECULAR else 0.0


def ethnicity_set(value: Any) -> Optional[Set[str]]:
    text = norm_text(value)
    if text is None:
        return None
    parts = {p.strip() for p in text.split(",") if p.strip()}
    return parts or None


def ethnicity_similarity(a: Any, b: Any) -> Optional[float]:
    """Jaccard overlap of the (multi-valued) ethnicity sets."""
    sa, sb = ethnicity_set(a), ethnicity_set(b)
    if sa is None or sb is None:
        return None
    return len(sa & sb) / len(sa | sb)


# --------------------------------------------------------------------------
# Lifestyle
# --------------------------------------------------------------------------
ORDINAL_SCALES: Dict[str, Dict[str, int]] = {
    "drinks": {"not at all": 0, "rarely": 1, "socially": 2, "often": 3, "very often": 4, "desperately": 5},
    "drugs": {"never": 0, "sometimes": 1, "often": 2},
    "smokes": {"no": 0, "trying to quit": 1, "when drinking": 2, "sometimes": 3, "yes": 4},
}


def ordinal_similarity(field: str, a: Any, b: Any) -> Optional[float]:
    scale = ORDINAL_SCALES[field]
    ta, tb = norm_text(a), norm_text(b)
    ra, rb = scale.get(ta) if ta else None, scale.get(tb) if tb else None
    return _linear_similarity(ra, rb, max(scale.values()))


_DIET_BASES = ("anything", "vegetarian", "vegan", "halal", "kosher")


def diet_base(value: Any) -> Optional[str]:
    text = norm_text(value)
    if text is None:
        return None
    for prefix in ("mostly ", "strictly "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text if text in _DIET_BASES else None


def diet_similarity(a: Any, b: Any) -> Optional[float]:
    da, db = diet_base(a), diet_base(b)
    if da is None or db is None:
        return None
    if da == db:
        return 1.0
    if {da, db} == {"vegetarian", "vegan"} or "anything" in (da, db):
        return 0.5
    return 0.0


# --------------------------------------------------------------------------
# Family (long-term relevant): children stance + pets
# --------------------------------------------------------------------------
def offspring_stance(value: Any) -> Optional[str]:
    """Stance on (more) children: 'yes' | 'maybe' | 'no' | None (not stated)."""
    text = norm_text(value)
    if text is None:
        return None
    if "doesn't want" in text:
        return "no"
    if "might want" in text:
        return "maybe"
    if "want" in text:
        return "yes"
    return None  # e.g. "has a kid" / "doesn't have kids": no stance given


def offspring_similarity(a: Any, b: Any) -> Optional[float]:
    sa, sb = offspring_stance(a), offspring_stance(b)
    if sa is None or sb is None:
        return None
    if sa == sb:
        return 1.0
    return 0.0 if {sa, sb} == {"yes", "no"} else 0.5


def pet_attitudes(value: Any) -> Dict[str, Optional[int]]:
    text = norm_text(value)
    result: Dict[str, Optional[int]] = {"dogs": None, "cats": None}
    if text is None:
        return result
    for species in result:
        if f"dislikes {species}" in text:
            result[species] = 0
        elif f"likes {species}" in text or f"has {species}" in text:
            result[species] = 1
    return result


def pets_similarity(a: Any, b: Any) -> Optional[float]:
    pa, pb = pet_attitudes(a), pet_attitudes(b)
    agree = [float(pa[s] == pb[s]) for s in pa if pa[s] is not None and pb[s] is not None]
    return sum(agree) / len(agree) if agree else None


# --------------------------------------------------------------------------
# Attraction: height (80%) + body type (20%)
# --------------------------------------------------------------------------
BODY_TYPE_GROUPS: Dict[str, str] = {
    "thin": "slim", "skinny": "slim",
    "average": "average",
    "fit": "athletic", "athletic": "athletic", "jacked": "athletic",
    "curvy": "fuller", "a little extra": "fuller", "full figured": "fuller", "overweight": "fuller",
}


def clean_height(value: Any, valid_range=(48.0, 96.0)) -> Optional[float]:
    """Height in inches; implausible values (data-entry errors) become unknown."""
    height = to_float(value)
    return height if height is not None and valid_range[0] <= height <= valid_range[1] else None


def height_similarity(a: Any, b: Any, max_gap: float = 12.0, valid_range=(48.0, 96.0)) -> Optional[float]:
    return _linear_similarity(clean_height(a, valid_range), clean_height(b, valid_range), max_gap)


def body_type_similarity(a: Any, b: Any) -> Optional[float]:
    ta, tb = norm_text(a), norm_text(b)
    if ta not in BODY_TYPE_GROUPS or tb not in BODY_TYPE_GROUPS:
        return None
    if ta == tb:
        return 1.0
    return 0.5 if BODY_TYPE_GROUPS[ta] == BODY_TYPE_GROUPS[tb] else 0.0


# --------------------------------------------------------------------------
# v2.2.0 (append-only): normalized profile attributes shared by the preference
# and behavior layers. Does not change any function above.
# --------------------------------------------------------------------------
RELATIONSHIP_INTENTIONS = ("long_term", "serious", "marriage", "casual", "friendship", "unsure")


def relationship_intention(value: Any) -> Optional[str]:
    text = norm_text(value)
    if text is None:
        return None
    text = text.replace("-", "_").replace(" ", "_")
    return text if text in RELATIONSHIP_INTENTIONS else None


def pets_liked(value: Any) -> Optional[Set[str]]:
    """Species the person likes/has (None when pets are unknown)."""
    attitudes = pet_attitudes(value)
    if all(v is None for v in attitudes.values()):
        return None
    return {species for species, v in attitudes.items() if v == 1}


def profile_attributes(profile: Dict[str, Any], reference_year: int) -> Dict[str, Any]:
    """Normalized attributes of one profile; unknown values are None (never a default)."""
    job = clean_profession(profile.get("job"))
    return {
        "age": clean_age(profile.get("age")),
        "height": clean_height(profile.get("height")),
        "education_rank": education_rank(profile.get("education")),
        "profession": job,
        "profession_group": PROFESSION_GROUPS.get(job) if job else None,
        "religion": religion_base(profile.get("religion")),
        "ethnicity": ethnicity_set(profile.get("ethnicity")),
        "drinks": norm_text(profile.get("drinks")),
        "drugs": norm_text(profile.get("drugs")),
        "smokes": norm_text(profile.get("smokes")),
        "diet": diet_base(profile.get("diet")),
        "children": offspring_stance(profile.get("offspring")),
        "pets": pets_liked(profile.get("pets")),
        "body_type": norm_text(profile.get("body_type")) if norm_text(profile.get("body_type")) in BODY_TYPE_GROUPS else None,
        "body_type_group": BODY_TYPE_GROUPS.get(norm_text(profile.get("body_type")) or ""),
        "generation": derive_generation(profile, reference_year),
        "relationship_intention": relationship_intention(profile.get("relationship_intention")),
        "region": norm_text(profile.get("region") or profile.get("state")),
    }

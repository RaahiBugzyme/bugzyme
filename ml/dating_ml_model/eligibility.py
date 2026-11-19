"""Eligibility is a hard gate, separate from compatibility scoring.

A pair is eligible only if (1) both users are adults with a known age, and
(2) attraction is mutual and directional, based on sex and sexual orientation.
Unknown sex/orientation/age => NOT eligible (it cannot be verified).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .feature_engineering import clean_age, norm_text

_SEX = {"m": "m", "male": "m", "man": "m", "f": "f", "female": "f", "woman": "f"}
_ORIENTATION = {
    "straight": "straight", "heterosexual": "straight",
    "gay": "gay", "lesbian": "gay", "homosexual": "gay",
    "bisexual": "bisexual", "bi": "bisexual",
}


def _sex(profile: Dict[str, Any]) -> Optional[str]:
    text = norm_text(profile.get("sex"))
    return _SEX.get(text) if text else None


def _orientation(profile: Dict[str, Any]) -> Optional[str]:
    text = norm_text(profile.get("orientation"))
    return _ORIENTATION.get(text) if text else None


def is_attracted(profile: Dict[str, Any], other: Dict[str, Any]) -> Optional[bool]:
    """Would `profile` be attracted to `other`'s sex? None if unknown."""
    sex, orientation, other_sex = _sex(profile), _orientation(profile), _sex(other)
    if sex is None or orientation is None or other_sex is None:
        return None
    if orientation == "bisexual":
        return True
    return (sex != other_sex) if orientation == "straight" else (sex == other_sex)


def check_eligibility(a: Dict[str, Any], b: Dict[str, Any], min_age: int = 18) -> Dict[str, Any]:
    id_a, id_b = a.get("id", a.get("user_id")), b.get("id", b.get("user_id"))
    if id_a is not None and id_a == id_b:
        return {"eligible": False, "reason": "Same user"}
    for label, profile in (("first", a), ("second", b)):
        age = clean_age(profile.get("age"))
        if age is None:
            return {"eligible": False, "reason": f"Age unknown for {label} user; adulthood cannot be verified"}
        if age < min_age:
            return {"eligible": False, "reason": f"{label.capitalize()} user is under {min_age}"}
    a_to_b, b_to_a = is_attracted(a, b), is_attracted(b, a)
    if a_to_b is None or b_to_a is None:
        return {"eligible": False, "reason": "Sex or orientation missing; mutual attraction cannot be verified"}
    if not a_to_b:
        return {"eligible": False, "reason": "First user is not attracted to the second user's sex"}
    if not b_to_a:
        return {"eligible": False, "reason": "Second user is not attracted to the first user's sex"}
    return {"eligible": True, "reason": "Mutual sex/orientation compatibility"}

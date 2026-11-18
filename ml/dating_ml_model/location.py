"""Location / distance layer (separate from core compatibility).

Rules: unknown location is UNKNOWN, never "far away". Coordinates are never invented:
they come from the profile itself or from an explicit gazetteer lookup. If a city cannot
be resolved reliably the status is "unresolved" and no score is produced.
"""
from __future__ import annotations

import csv
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .feature_engineering import norm_text, to_float

EARTH_RADIUS_KM = 6371.0088

_COUNTRY_ALIASES = {
    "in": "india", "ind": "india", "us": "united states", "usa": "united states", "u.s.": "united states",
    "u.s.a.": "united states", "united states of america": "united states", "america": "united states",
    "uk": "united kingdom", "gb": "united kingdom", "great britain": "united kingdom", "england": "united kingdom",
    "uae": "united arab emirates", "de": "germany", "fr": "france", "ca": "canada", "au": "australia", "sg": "singapore",
    "jp": "japan", "kr": "south korea", "nz": "new zealand", "nl": "netherlands", "ch": "switzerland",
    "qa": "qatar", "sa": "saudi arabia", "es": "spain", "it": "italy", "ie": "ireland", "be": "belgium",
    "th": "thailand", "my": "malaysia", "ph": "philippines", "id": "indonesia", "at": "austria", "se": "sweden",
    "no": "norway", "dk": "denmark", "fi": "finland", "pl": "poland", "il": "israel",
}

_REGION_ALIASES = {
    # US states
    "ca": "california", "ny": "new york", "il": "illinois", "ma": "massachusetts",
    "wa": "washington", "tx": "texas", "co": "colorado", "fl": "florida", "ga": "georgia",
    "pa": "pennsylvania", "dc": "district of columbia", "d.c.": "district of columbia",
    "az": "arizona", "nv": "nevada", "or": "oregon", "mn": "minnesota", "mi": "michigan",
    "md": "maryland", "va": "virginia",
    # Indian states / UTs
    "mh": "maharashtra", "dl": "delhi", "ka": "karnataka", "tn": "tamil nadu",
    "ts": "telangana", "tg": "telangana", "wb": "west bengal", "gj": "gujarat",
    "up": "uttar pradesh", "rj": "rajasthan", "mp": "madhya pradesh", "ap": "andhra pradesh",
    "kl": "kerala", "pb": "punjab", "hr": "haryana", "od": "odisha", "jh": "jharkhand",
    "br": "bihar", "cg": "chhattisgarh", "ut": "uttarakhand", "hp": "himachal pradesh",
    "jk": "jammu and kashmir", "as": "assam", "ga": "goa", "py": "puducherry",
    # Canada & Australia
    "on": "ontario", "bc": "british columbia", "nsw": "new south wales", "vic": "victoria", "qld": "queensland",
}


def norm_place(value: Any) -> Optional[str]:
    text = norm_text(value)
    if text is None:
        return None
    text = text.replace(".", "") if len(text) <= 4 else text
    return text.strip(".,;: -_")


def norm_region(value: Any) -> Optional[str]:
    text = norm_place(value)
    if text is None:
        return None
    return _REGION_ALIASES.get(text, text)


def norm_country(value: Any) -> Optional[str]:
    text = norm_text(value)
    if text is None:
        return None
    return _COUNTRY_ALIASES.get(text, _COUNTRY_ALIASES.get(text.replace(".", ""), text))


# ----------------------------------------------------------------- coordinates
def clean_coordinates(profile: Dict[str, Any], treat_zero_zero_as_missing: bool = True) -> Tuple[Optional[Tuple[float, float]], List[str]]:
    """Returns ((lat, lon) | None, warnings). Half-present or out-of-range => None + warning."""
    lat, lon = to_float(profile.get("latitude")), to_float(profile.get("longitude"))
    warnings: List[str] = []
    if lat is None and lon is None:
        return None, warnings
    if lat is None or lon is None:
        warnings.append("incomplete coordinates ignored (latitude or longitude missing)")
        return None, warnings
    if not -90.0 <= lat <= 90.0:
        warnings.append("invalid latitude ignored")
        return None, warnings
    if not -180.0 <= lon <= 180.0:
        warnings.append("invalid longitude ignored")
        return None, warnings
    if treat_zero_zero_as_missing and lat == 0.0 and lon == 0.0:
        warnings.append("coordinates (0, 0) treated as missing")
        return None, warnings
    return (lat, lon), warnings


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


# ------------------------------------------------------------------ gazetteer
class GeoResolver:
    """Interface: resolve (city, region, country) -> (lat, lon) or None. Never guess."""

    def resolve(self, city: Optional[str], region: Optional[str] = None, country: Optional[str] = None) -> Optional[Tuple[float, float]]:
        return None


class GazetteerResolver(GeoResolver):
    """Exact-name lookup in an explicit gazetteer (city centroids). No fuzzy matching, no guessing."""

    def __init__(self, rows: List[Dict[str, Any]]):
        self._entries: List[Dict[str, Any]] = []
        self._by_city: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            entry = {
                "city": norm_place(row["city"]),
                "region": norm_region(row.get("region")),
                "country": norm_country(row.get("country")),
                "raw_city": str(row["city"]).strip(),
                "raw_region": str(row.get("region") or "").strip(),
                "raw_country": str(row.get("country") or "").strip(),
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
            }
            self._entries.append(entry)
            raw_aliases = str(row.get("aliases") or "").split(";")
            names = {entry["city"]} | {norm_place(a) for a in raw_aliases if a.strip()}
            expanded_names = set(names)
            for name in names:
                if name:
                    if "-" in name:
                        expanded_names.add(name.replace("-", " "))
                    if " " in name:
                        expanded_names.add(name.replace(" ", "-"))
            for name in expanded_names:
                if name:
                    self._by_city.setdefault(name, []).append(entry)

    def __len__(self) -> int:
        return len(self._entries)

    def cities(self) -> List[str]:
        """Sorted unique list of canonical city names in this gazetteer."""
        return sorted({e["raw_city"] for e in self._entries})

    def is_ambiguous(self, city: Optional[str], region: Optional[str] = None, country: Optional[str] = None) -> bool:
        """True if the city query maps to multiple distinct locations without resolution."""
        key = norm_place(city)
        if key is None:
            return False
        candidates = self._by_city.get(key, [])
        if not candidates:
            if "-" in key:
                candidates = self._by_city.get(key.replace("-", " "), [])
            elif " " in key:
                candidates = self._by_city.get(key.replace(" ", "-"), [])
        region_n = norm_region(region)
        country_n = norm_country(country)
        if country_n is not None:
            candidates = [c for c in candidates if c["country"] == country_n]
        if region_n is not None:
            candidates = [c for c in candidates if c["region"] == region_n]
        return len(candidates) > 1

    def get_entry(self, city: Optional[str], region: Optional[str] = None, country: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Returns the unique matching entry dict if resolved, else None."""
        key = norm_place(city)
        if key is None:
            return None
        candidates = self._by_city.get(key, [])
        if not candidates:
            if "-" in key:
                candidates = self._by_city.get(key.replace("-", " "), [])
            elif " " in key:
                candidates = self._by_city.get(key.replace(" ", "-"), [])
        region_n = norm_region(region)
        country_n = norm_country(country)
        if country_n is not None:
            candidates = [c for c in candidates if c["country"] == country_n]
        if region_n is not None:
            candidates = [c for c in candidates if c["region"] == region_n]
        if len(candidates) == 1:
            return dict(candidates[0])
        return None

    @classmethod
    def from_csv(cls, path: str) -> "GazetteerResolver":
        with open(path, newline="", encoding="utf-8") as handle:
            return cls(list(csv.DictReader(handle)))

    @classmethod
    def default(cls) -> "GazetteerResolver":
        return _default_resolver()

    def resolve(self, city: Optional[str], region: Optional[str] = None, country: Optional[str] = None) -> Optional[Tuple[float, float]]:
        entry = self.get_entry(city, region, country)
        if entry is None:
            return None
        return entry["lat"], entry["lon"]


@lru_cache(maxsize=1)
def _default_resolver() -> GazetteerResolver:
    return GazetteerResolver.from_csv(str(Path(__file__).with_name("data") / "gazetteer_seed.csv"))


# ------------------------------------------------------------ location parsing
def _split_location_string(text: str) -> Dict[str, Optional[str]]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 3:
        return {"city": parts[0], "region": parts[1], "country": parts[2]}
    if len(parts) == 2:
        if norm_country(parts[1]) in set(_COUNTRY_ALIASES.values()) or norm_text(parts[1]) in _COUNTRY_ALIASES:
            return {"city": parts[0], "region": None, "country": parts[1]}
        return {"city": parts[0], "region": parts[1], "country": None}
    if len(parts) == 1:
        return {"city": parts[0], "region": None, "country": None}
    return {"city": None, "region": None, "country": None}


def describe_location(profile: Dict[str, Any], resolver: Optional[GeoResolver] = None,
                      treat_zero_zero_as_missing: bool = True) -> Dict[str, Any]:
    """Resolution hierarchy: coordinates > city(+region,+country) > region(+country) > country > unknown."""
    resolver = resolver if resolver is not None else GazetteerResolver.default()
    coords, warnings = clean_coordinates(profile, treat_zero_zero_as_missing)
    city, region = norm_place(profile.get("city")), norm_region(profile.get("state", profile.get("region")))
    country = norm_country(profile.get("country"))
    free_text = norm_text(profile.get("location"))
    if free_text and city is None and region is None and country is None:
        parsed = _split_location_string(free_text)
        city, region, country = norm_place(parsed["city"]), norm_region(parsed["region"]), norm_country(parsed["country"])
        if parsed["city"] and parsed["region"] is None and parsed["country"] is None and norm_text(parsed["city"]) in _COUNTRY_ALIASES.values():
            city, country = None, norm_country(parsed["city"])  # a lone token that is a country name

    info = {"city": city, "region": region, "country": country, "warnings": warnings,
            "latitude": None, "longitude": None, "level": "unknown", "resolution": "none", "resolved": False}
    if coords is not None:
        info.update(latitude=coords[0], longitude=coords[1], level="coordinates", resolution="coordinates", resolved=True)
    elif city is not None:
        info["level"] = "city"
        point = resolver.resolve(city, region, country)
        if point is not None:
            info.update(latitude=point[0], longitude=point[1], resolution="gazetteer_city_centroid", resolved=True)
        else:
            info["resolution"] = "unresolved"
    elif region is not None:
        info["level"] = "region"
    elif country is not None:
        info["level"] = "country"
    return info


def calculate_distance_km(user_a: Dict[str, Any], user_b: Dict[str, Any], resolver: Optional[GeoResolver] = None) -> Optional[float]:
    """Haversine distance in km, or None if either location cannot be resolved to coordinates."""
    a, b = describe_location(user_a, resolver), describe_location(user_b, resolver)
    if not (a["resolved"] and b["resolved"]):
        return None
    return round(haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"]), 4)


# --------------------------------------------------------------- score / compare
def distance_to_score(distance_km: float, curve: List[List[float]]) -> float:
    """Piecewise-linear interpolation over the configured (km, score) curve; flat beyond the last point."""
    pts = sorted((float(k), float(s)) for k, s in curve)
    if distance_km <= pts[0][0]:
        return pts[0][1]
    for (k0, s0), (k1, s1) in zip(pts, pts[1:]):
        if distance_km <= k1:
            return s0 + (s1 - s0) * (distance_km - k0) / (k1 - k0)
    return pts[-1][1]


def _positive(value: Any) -> Optional[float]:
    number = to_float(value)
    return number if number is not None and number > 0 else None


def compare_locations(user: Dict[str, Any], candidate: Dict[str, Any], config: Dict[str, Any],
                      resolver: Optional[GeoResolver] = None,
                      user_preferences: Optional[Dict[str, Any]] = None,
                      candidate_preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Location signal for `user` looking at `candidate`. Unknown location => null score, no penalty."""
    loc_cfg = config["location"]
    prefs = user_preferences or {}
    preferred = _positive(prefs.get("preferred_distance_km", user.get("preferred_distance_km")))
    preferred_source = "user" if preferred is not None else "default"
    preferred = preferred if preferred is not None else float(config["default_preferred_distance_km"])
    max_user = _positive(prefs.get("max_distance_km", user.get("max_distance_km")))
    max_cand = _positive((candidate_preferences or {}).get("max_distance_km", candidate.get("max_distance_km"))) \
        if config["preferences"].get("hard_preferences_mutual", True) else None
    if not config.get("max_distance_enabled", True):
        max_user = max_cand = None

    base = {"distance_km": None, "location_score": None, "location_confidence": 0.0, "location_available": False,
            "preferred_distance_km": preferred, "preferred_distance_source": preferred_source,
            "max_distance_km": max_user, "within_preferred_distance": None, "within_max_distance": None,
            "same_region": None, "same_country": None, "warnings": []}
    if not config.get("location_enabled", True):
        return {**base, "location_status": "disabled"}

    zz = loc_cfg.get("treat_zero_zero_as_missing", True)
    a, b = describe_location(user, resolver, zz), describe_location(candidate, resolver, zz)
    base["warnings"] = a["warnings"] + b["warnings"]
    has_a, has_b = a["level"] != "unknown", b["level"] != "unknown"

    if a["resolved"] and b["resolved"]:
        distance = haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
        scaled = distance * (float(config["default_preferred_distance_km"]) / preferred)
        confidence = min(loc_cfg["coordinate_confidence"] if a["resolution"] == "coordinates" else loc_cfg["city_centroid_confidence"],
                         loc_cfg["coordinate_confidence"] if b["resolution"] == "coordinates" else loc_cfg["city_centroid_confidence"])
        limits = [m for m in (max_user, max_cand) if m is not None]
        return {**base, "distance_km": round(distance, 2),
                "location_score": round(distance_to_score(scaled, loc_cfg["distance_curve_km_score"]), 2),
                "location_confidence": confidence, "location_available": True, "location_status": "known",
                "within_preferred_distance": distance <= preferred,
                "within_max_distance": (distance <= min(limits)) if limits else None,
                "same_region": (a["region"] == b["region"]) if a["region"] and b["region"] else None,
                "same_country": (a["country"] == b["country"]) if a["country"] and b["country"] else None}

    if not has_a and not has_b:
        status = "unknown"
    elif not has_a or not has_b:
        status = "partial_unknown"
    elif a["resolution"] == "unresolved" or b["resolution"] == "unresolved":
        status = "unresolved"
    else:
        status = "coarse"  # region/country only: no reliable distance
    same_region = (a["region"] == b["region"]) if status in ("coarse", "unresolved") and a["region"] and b["region"] else None
    same_country = (a["country"] == b["country"]) if status in ("coarse", "unresolved") and a["country"] and b["country"] else None
    return {**base, "location_status": status, "same_region": same_region, "same_country": same_country}

"""Clearly labeled synthetic test data generator for HeartMatch ML V3 standalone validation.

NOTICE: All profiles, interactions, and preferences generated in this module are strictly
synthetic test fixtures. They do NOT represent real human users, real demographic datasets,
or real-world match outcomes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

SYNTHETIC_DATA_FLAG = "SYNTHETIC_TEST_FIXTURE_DO_NOT_TREAT_AS_REAL_USER"
SYNTHETIC_NOW = datetime(2026, 10, 26, 12, 0, 0)


def create_synthetic_profile(
    user_id: str,
    age: Optional[int],
    sex: Optional[str],
    orientation: Optional[str],
    job: Optional[str] = None,
    education: Optional[str] = "graduated from college/university",
    religion: Optional[str] = "agnosticism",
    ethnicity: Optional[str] = "asian",
    city: Optional[str] = "Pune",
    state: Optional[str] = "Maharashtra",
    country: Optional[str] = "India",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    height: Optional[int] = 68,
    smokes: Optional[str] = "no",
    drinks: Optional[str] = "socially",
    diet: Optional[str] = "vegetarian",
    interests: Optional[List[str]] = None,
    relationship_intention: Optional[str] = "long_term",
    **extra: Any,
) -> Dict[str, Any]:
    """Generates a clearly labeled synthetic profile."""
    prof: Dict[str, Any] = {
        "id": str(user_id),
        "is_synthetic": True,
        "data_source": SYNTHETIC_DATA_FLAG,
        "age": age,
        "sex": sex,
        "orientation": orientation,
        "job": job,
        "education": education,
        "religion": religion,
        "ethnicity": ethnicity,
        "city": city,
        "state": state,
        "country": country,
        "height": height,
        "smokes": smokes,
        "drinks": drinks,
        "diet": diet,
        "interests": list(interests or []),
        "relationship_intention": relationship_intention,
    }
    if latitude is not None and longitude is not None:
        prof["latitude"] = latitude
        prof["longitude"] = longitude
    prof.update(extra)
    return prof


def get_synthetic_test_suite_data() -> Dict[str, Any]:
    """Builds a comprehensive suite of synthetic test profiles, preferences, personalities, and interactions."""
    # -------------------------------------------------------------------------
    # 1. Focus Synthetic Test Users
    # -------------------------------------------------------------------------
    focus_users = {
        # A. Cold Start user with zero interaction history
        "syn_user_cold_start": create_synthetic_profile(
            user_id="syn_user_cold_start",
            age=29,
            sex="f",
            orientation="straight",
            job="science / tech / engineering",
            city="Pune",
            state="Maharashtra",
            country="India",
            interests=["coding", "hiking", "badminton"],
        ),
        # B. User with Incomplete Profile Information (missing job, religion, height)
        "syn_user_incomplete": create_synthetic_profile(
            user_id="syn_user_incomplete",
            age=28,
            sex="f",
            orientation="straight",
            job=None,
            religion=None,
            height=None,
            city="Pune",
            state="Maharashtra",
            country="India",
            interests=["reading", "art"],
        ),
        # C. User with Strict Dealbreakers (Non-smokers only, strictly within 30km, age 26-34)
        "syn_user_strict": create_synthetic_profile(
            user_id="syn_user_strict",
            age=30,
            sex="f",
            orientation="straight",
            job="science / tech / engineering",
            city="Pune",
            state="Maharashtra",
            country="India",
            interests=["technology", "cycling"],
        ),
        # D. User with Active Self-Reported Personality Preferences
        "syn_user_personality": create_synthetic_profile(
            user_id="syn_user_personality",
            age=31,
            sex="m",
            orientation="straight",
            job="science / tech / engineering",
            city="Pune",
            state="Maharashtra",
            country="India",
            interests=["chess", "photography"],
        ),
        # E. Established Active User with Rich Interaction History
        "syn_user_active": create_synthetic_profile(
            user_id="syn_user_active",
            age=29,
            sex="f",
            orientation="straight",
            job="science / tech / engineering",
            city="Pune",
            state="Maharashtra",
            country="India",
            interests=["coding", "ai", "bouldering"],
        ),
    }

    # -------------------------------------------------------------------------
    # 2. Focus User Explicit Preferences & Dealbreakers
    # -------------------------------------------------------------------------
    user_preferences = {
        "syn_user_cold_start": {
            "preferred_distance_km": 50,
            "criteria": {
                "profession_group": {"values": ["technology_science"], "hard": False},
            },
        },
        "syn_user_strict": {
            "preferred_distance_km": 30,
            "max_distance_km": 30,
            "dealbreakers": {
                "smokes": ["no"],
                "age": {"min": 26, "max": 34},
            },
            "criteria": {
                "diet": {"values": ["vegetarian", "mostly_vegetarian"], "hard": False},
            },
        },
        "syn_user_personality": {
            "preferred_distance_km": 40,
        },
        "syn_user_active": {
            "preferred_distance_km": 40,
            "criteria": {
                "profession_group": {"values": ["technology_science"], "hard": False},
            },
        },
    }

    # -------------------------------------------------------------------------
    # 3. Focus User Personality & Communication Preferences
    # -------------------------------------------------------------------------
    user_personalities = {
        "syn_user_personality": {
            "personality_type": "introvert",
            "communication_frequency": "daily",
            "conversation_style": "deep_conversations",
            "social_activities": ["quiet_nights_in", "cultural_events", "creative_arts"],
        },
        "syn_user_active": {
            "personality_type": "ambivert",
            "communication_frequency": "few_times_a_week",
            "conversation_style": "deep_conversations",
            "social_activities": ["outdoor_adventures", "gaming_tech"],
        },
    }

    # -------------------------------------------------------------------------
    # 4. Diverse Candidate Pool (Eligible, Ineligible, and Edge Cases)
    # -------------------------------------------------------------------------
    candidate_pool = [
        # Candidate 01: Near Pune, Tech, Non-smoker, Highly Compatible, Introvert
        create_synthetic_profile(
            user_id="syn_cand_01_tech_near",
            age=30,
            sex="m",
            orientation="straight",
            job="science / tech / engineering",
            city="Pune",
            state="Maharashtra",
            country="India",
            smokes="no",
            diet="vegetarian",
            interests=["coding", "hiking", "badminton"],
        ),
        # Candidate 02: Mumbai (~120 km away), Business Finance, Smoker (violates strict dealbreaker)
        create_synthetic_profile(
            user_id="syn_cand_02_finance_smoker",
            age=31,
            sex="m",
            orientation="straight",
            job="banking / financial / real estate",
            city="Mumbai",
            state="Maharashtra",
            country="India",
            smokes="yes",
            diet="anything",
            interests=["stocks", "nightlife", "clubbing"],
        ),
        # Candidate 03: Pune, Creative Writer, Ambivert, Aligned styles
        create_synthetic_profile(
            user_id="syn_cand_03_writer_ambivert",
            age=29,
            sex="m",
            orientation="straight",
            job="artistic / musical / writer",
            city="Pune",
            state="Maharashtra",
            country="India",
            smokes="no",
            diet="vegetarian",
            interests=["photography", "reading", "art"],
        ),
        # Candidate 04: Bengaluru (~840 km away), Tech, Non-smoker (Far distance)
        create_synthetic_profile(
            user_id="syn_cand_04_tech_far",
            age=28,
            sex="m",
            orientation="straight",
            job="computer / hardware / software",
            city="Bengaluru",
            state="Karnataka",
            country="India",
            smokes="no",
            interests=["coding", "ai"],
        ),
        # Candidate 05: Incomplete profile (missing job, location, height)
        create_synthetic_profile(
            user_id="syn_cand_05_sparse",
            age=29,
            sex="m",
            orientation="straight",
            job=None,
            city=None,
            state=None,
            country=None,
            height=None,
            interests=["movies"],
        ),
        # Candidate 06: Underage (17 years old) -> Ineligible (Adulthood check fails)
        create_synthetic_profile(
            user_id="syn_cand_06_underage",
            age=17,
            sex="m",
            orientation="straight",
            job="student",
            city="Pune",
            state="Maharashtra",
            country="India",
            interests=["gaming"],
        ),
        # Candidate 07: Same sex (Female for straight female viewer) -> Ineligible (Orientation check fails)
        create_synthetic_profile(
            user_id="syn_cand_07_same_sex",
            age=28,
            sex="f",
            orientation="straight",
            job="medicine / health",
            city="Pune",
            state="Maharashtra",
            country="India",
            interests=["yoga", "hiking"],
        ),
        # Candidate 08: Missing age -> Ineligible (Cannot verify adulthood)
        create_synthetic_profile(
            user_id="syn_cand_08_missing_age",
            age=None,
            sex="m",
            orientation="straight",
            job="education / academia",
            city="Pune",
            state="Maharashtra",
            country="India",
        ),
        # Candidate 09: Extrovert, High social activity, frequent messaging
        create_synthetic_profile(
            user_id="syn_cand_09_extrovert",
            age=30,
            sex="m",
            orientation="straight",
            job="sales / marketing / biz dev",
            city="Pune",
            state="Maharashtra",
            country="India",
            smokes="no",
            interests=["networking", "clubbing"],
        ),
        # Candidate 10: Medicine Health, Pune, Non-smoker, Highly educated
        create_synthetic_profile(
            user_id="syn_cand_10_doctor",
            age=32,
            sex="m",
            orientation="straight",
            job="medicine / health",
            education="working on masters program",
            city="Pune",
            state="Maharashtra",
            country="India",
            smokes="no",
            diet="mostly vegetarian",
            interests=["badminton", "reading"],
        ),
        # Candidate 11: Female Tech near Pune (eligible for male viewer syn_user_personality)
        create_synthetic_profile(
            user_id="syn_cand_11_female_tech_near",
            age=29,
            sex="f",
            orientation="straight",
            job="science / tech / engineering",
            city="Pune",
            state="Maharashtra",
            country="India",
            smokes="no",
            diet="vegetarian",
            interests=["coding", "hiking", "photography"],
        ),
        # Candidate 12: Female Doctor near Pune
        create_synthetic_profile(
            user_id="syn_cand_12_female_doctor",
            age=30,
            sex="f",
            orientation="straight",
            job="medicine / health",
            city="Pune",
            state="Maharashtra",
            country="India",
            smokes="no",
            diet="mostly vegetarian",
            interests=["badminton", "reading"],
        ),
        # Historical candidates for active user's behavioral training
        create_synthetic_profile(user_id="hist_tech_01", age=29, sex="m", orientation="straight", job="science / tech / engineering", city="Pune", smokes="no"),
        create_synthetic_profile(user_id="hist_tech_02", age=30, sex="m", orientation="straight", job="computer / hardware / software", city="Pune", smokes="no"),
        create_synthetic_profile(user_id="hist_tech_03", age=28, sex="m", orientation="straight", job="science / tech / engineering", city="Pune", smokes="no"),
        create_synthetic_profile(user_id="hist_tech_04", age=31, sex="m", orientation="straight", job="science / tech / engineering", city="Pune", smokes="no"),
        create_synthetic_profile(user_id="hist_fin_01", age=33, sex="m", orientation="straight", job="banking / financial / real estate", city="Mumbai", smokes="yes"),
        create_synthetic_profile(user_id="hist_fin_02", age=34, sex="m", orientation="straight", job="banking / financial / real estate", city="Mumbai", smokes="yes"),
        create_synthetic_profile(user_id="hist_fin_03", age=35, sex="m", orientation="straight", job="sales / marketing / biz dev", city="Mumbai", smokes="yes"),
    ]

    # Candidate self-reported personalities
    candidate_personalities = {
        "syn_cand_01_tech_near": {
            "personality_type": "introvert",
            "communication_frequency": "daily",
            "conversation_style": "deep_conversations",
            "social_activities": ["quiet_nights_in", "cultural_events"],
        },
        "syn_cand_03_writer_ambivert": {
            "personality_type": "ambivert",
            "communication_frequency": "daily",
            "conversation_style": "deep_conversations",
            "social_activities": ["creative_arts", "quiet_nights_in"],
        },
        "syn_cand_09_extrovert": {
            "personality_type": "extrovert",
            "communication_frequency": "daily",
            "conversation_style": "casual_banter",
            "social_activities": ["social_gatherings", "fitness_sports"],
        },
        "syn_cand_11_female_tech_near": {
            "personality_type": "introvert",
            "communication_frequency": "daily",
            "conversation_style": "deep_conversations",
            "social_activities": ["quiet_nights_in", "cultural_events", "creative_arts"],
        },
        "syn_cand_12_female_doctor": {
            "personality_type": "extrovert",
            "communication_frequency": "few_times_a_week",
            "conversation_style": "casual_banter",
            "social_activities": ["social_gatherings", "fitness_sports"],
        },
    }

    # Candidate explicit preferences (for bilateral asymmetric evaluation)
    candidate_preferences = {
        "syn_cand_01_tech_near": {
            "preferred_distance_km": 30,
            "criteria": {
                "age": {"min": 35, "max": 42, "hard": False},  # Asymmetry: viewer is 29, so score ~50%
                "profession_group": {"values": ["technology_science"], "hard": False},
            },
        },
        "syn_cand_10_doctor": {
            "preferred_distance_km": 40,
            "criteria": {
                "age": {"min": 25, "max": 32, "hard": True},
            },
        },
    }

    # -------------------------------------------------------------------------
    # 5. Controlled Interaction Events for syn_user_active
    # -------------------------------------------------------------------------
    def ev(cand_id: Optional[str], action: str, days_ago: float, **extra: Any) -> Dict[str, Any]:
        res = {
            "user_id": "syn_user_active",
            "candidate_id": cand_id,
            "action": action,
            "timestamp": (SYNTHETIC_NOW - timedelta(days=days_ago)).isoformat() + "Z",
        }
        res.update(extra)
        return res

    active_user_events = [
        # Search criteria
        ev(None, "SEARCH", 7.0, search_criteria={"profession_group": "technology_science"}),
        ev(None, "SEARCH", 5.0, search_criteria={"profession_group": "technology_science"}),
        # Views (weak signal)
        ev("syn_cand_01_tech_near", "VIEW", 6.0),
        ev("syn_cand_02_finance_smoker", "VIEW", 5.5),
        # Intentional Likes and Saves on Tech
        ev("syn_cand_01_tech_near", "LIKE", 4.0),
        ev("syn_cand_01_tech_near", "SAVE", 3.0),
        ev("syn_cand_01_tech_near", "CONVERSATION_START", 2.0),
        ev("syn_cand_01_tech_near", "MESSAGE_SENT", 2.0, metadata={"message_length_chars": 42, "word_count": 8}),
        ev("syn_cand_01_tech_near", "RECIPROCAL_CONVERSATION", 1.0),
        # Additional historical likes on technology profiles (6 decided candidates total)
        ev("hist_tech_01", "LIKE", 4.0),
        ev("hist_tech_02", "LIKE", 3.5),
        ev("hist_tech_03", "LIKE", 3.0),
        ev("hist_tech_04", "LIKE", 2.9),
        ev("syn_cand_10_doctor", "LIKE", 2.5),
        # Explicit passes on finance/nightlife (4 decided candidates)
        ev("syn_cand_02_finance_smoker", "PASS", 3.5),
        ev("hist_fin_01", "PASS", 3.2),
        ev("hist_fin_02", "PASS", 2.8),
        ev("hist_fin_03", "PASS", 2.1),
    ]

    return {
        "focus_users": focus_users,
        "user_preferences": user_preferences,
        "user_personalities": user_personalities,
        "candidate_pool": candidate_pool,
        "candidate_personalities": candidate_personalities,
        "candidate_preferences": candidate_preferences,
        "active_user_events": active_user_events,
        "now": SYNTHETIC_NOW,
    }

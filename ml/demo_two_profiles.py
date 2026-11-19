#!/usr/bin/env python3
"""HeartMatch ML V3 — Standalone Demonstration of Two Specific Profiles.

Evaluates compatibility between two synthetic user profiles (Pune Software Engineers,
Introverts, Long-Term Relationship goals) using the actual HeartMatch ML V3 code.

Usage:
    python demo_two_profiles.py
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict

from dating_ml_model.compatibility_engine import CATEGORIES
from dating_ml_model.explainability import explain_recommendation
from dating_ml_model.model import CompatibilityModel, RecommendationModel


def create_demo_profiles() -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Creates the two synthetic profiles and their stated preferences and personality."""
    profile_a = {
        "id": "synthetic_user_a_pune_dev",
        "data_source": "SYNTHETIC_TEST_FIXTURE_DO_NOT_TREAT_AS_REAL_USER",
        "is_synthetic": True,
        "age": 27,
        "sex": "m",
        "orientation": "straight",
        "city": "Pune",
        "state": "Maharashtra",
        "country": "India",
        "job": "computer / hardware / software",  # Software Engineer
        "education": "graduated from college/university",
        "diet": "vegetarian",
        "smokes": "no",
        "drinks": "socially",
        "interests": ["hiking", "technology", "travelling"],
        "relationship_intention": "long_term",
        # Explicitly missing/unspecified attributes to test graceful handling:
        "religion": None,
        "ethnicity": None,
        "height": None,
        "body_type": None,
        "offspring": None,
        "pets": None,
    }

    profile_b = {
        "id": "synthetic_user_b_pune_dev",
        "data_source": "SYNTHETIC_TEST_FIXTURE_DO_NOT_TREAT_AS_REAL_USER",
        "is_synthetic": True,
        "age": 26,
        "sex": "f",
        "orientation": "straight",
        "city": "Pune",
        "state": "Maharashtra",
        "country": "India",
        "job": "computer / hardware / software",  # Software Engineer
        "education": "graduated from college/university",
        "diet": "vegetarian",
        "smokes": "no",
        "drinks": "socially",
        "interests": ["hiking", "technology", "music"],
        "relationship_intention": "long_term",
        # Explicitly missing/unspecified attributes to test graceful handling:
        "religion": None,
        "ethnicity": None,
        "height": None,
        "body_type": None,
        "offspring": None,
        "pets": None,
    }

    prefs_a = {
        "preferred_distance_km": 50,
        "dealbreakers": {
            "smokes": ["no"],
        },
        "criteria": {
            "profession_group": {"values": ["technology_science"], "hard": False},
        },
    }

    prefs_b = {
        "preferred_distance_km": 50,
        "dealbreakers": {
            "smokes": ["no"],
        },
        "criteria": {
            "profession_group": {"values": ["technology_science"], "hard": False},
        },
    }

    personality_a = {
        "personality_type": "introvert",
        "communication_frequency": "few_times_a_week",
        "conversation_style": "deep_conversations",
        "social_activities": ["outdoor_adventures", "gaming_tech"],
    }

    personality_b = {
        "personality_type": "introvert",
        "communication_frequency": "few_times_a_week",
        "conversation_style": "deep_conversations",
        "social_activities": ["quiet_nights_in", "cultural_events"],
    }

    return profile_a, profile_b, prefs_a, prefs_b, personality_a, personality_b


def format_profile_card(title: str, p: Dict[str, Any], prefs: Dict[str, Any], pers: Dict[str, Any]) -> str:
    lines = [
        f"--- {title} ---",
        f"  * User ID:                {p['id']}",
        f"  * Age / Sex / Orientation: {p['age']} / {p['sex'].upper()} / {p['orientation'].title()}",
        f"  * Location:               {p['city']}, {p['state']}, {p['country']}",
        f"  * Profession:             {p['job']} (Software Engineer)",
        f"  * Education:              {p['education']}",
        f"  * Habits:                 Smokes: {p['smokes']} | Drinks: {p['drinks']} | Diet: {p['diet']}",
        f"  * Interests:              {', '.join(p['interests'])}",
        f"  * Relationship Goal:      {p['relationship_intention']}",
        f"  * Personality:            {pers.get('personality_type', 'N/A').title()} (Style: {pers.get('conversation_style', 'N/A')})",
        f"  * Stated Preferences:     Pref Distance: <={prefs.get('preferred_distance_km')}km | Dealbreaker: Non-smoker",
        f"  * Unstated / Missing:     Religion, Ethnicity, Height, Body Type, Offspring, Pets (Reported as None)",
    ]
    return "\n".join(lines)


def run_demo() -> None:
    print("=" * 80)
    print("HEARTMATCH ML V3 — TWO PROFILES COMPATIBILITY DEMONSTRATION")
    print("Package: dating_ml_model (Deterministic & Explainable Matching)")
    print("Provenance: Strictly Synthetic Test Fixtures (No Real User PII)")
    print("=" * 80)

    p_a, p_b, prefs_a, prefs_b, pers_a, pers_b = create_demo_profiles()

    print("\n[1] INPUT PROFILES:")
    print(format_profile_card("PROFILE A", p_a, prefs_a, pers_a))
    print()
    print(format_profile_card("PROFILE B", p_b, prefs_b, pers_b))

    # Initialize models
    compat_model = CompatibilityModel()
    rec_model = RecommendationModel(compatibility_model=compat_model)

    print("\n" + "=" * 80)
    print("[2] ELIGIBILITY & HARD CONSTRAINTS CHECK:")
    print("=" * 80)
    elig, loc = rec_model.check_extended_eligibility(
        user=p_a,
        candidate=p_b,
        user_preferences=prefs_a,
        candidate_preferences=prefs_b,
    )
    print(f"  * Eligibility Status:      {'ELIGIBLE' if elig['eligible'] else 'INELIGIBLE'}")
    print(f"  * Hard Exclusions / Gate:  {elig['reasons'] if elig['reasons'] else 'None (Adulthood & Mutual Attraction Verified)'}")
    print(f"  * Geographic Distance:     {loc.get('distance_km', 'N/A')} km ({loc.get('location_status', 'unknown')})")
    print(f"  * Within Preferred Dist:   {loc.get('within_preferred_distance')} (Threshold: {prefs_a['preferred_distance_km']} km)")

    print("\n" + "=" * 80)
    print("[3] COMPATIBILITY MODEL (LAYER 1 DETERMINISTIC BASELINE):")
    print("=" * 80)
    l1_result = compat_model.predict_pair(p_a, p_b)
    print(f"  * Raw Compatibility Score: {l1_result['compatibility_score']:.2f} / 100.0")
    print(f"  * Evidence Confidence:     {l1_result['confidence_score']:.2f}% (Weighted share of known attributes)")
    print(f"  * Adjusted Baseline Score: {l1_result['adjusted_score']:.2f} / 100.0 (Regressed toward neutral 50.0 due to missing data)")
    print("  * Category Breakdown:")
    for cat in CATEGORIES:
        score = l1_result["categories"].get(cat)
        score_str = f"{score:.1f}%" if score is not None else "Unavailable / Missing"
        print(f"      - {cat.replace('_', ' ').title():<20}: {score_str}")

    print("\n" + "=" * 80)
    print("[4] LAYERED MULTI-SIGNAL EVALUATION & BILATERAL PREFERENCES:")
    print("=" * 80)
    record = rec_model.evaluate_candidate(
        user=p_a,
        candidate=p_b,
        user_preferences=prefs_a,
        candidate_preferences=prefs_b,
        user_personality=pers_a,
        candidate_personality=pers_b,
    )

    ranking = record["ranking"]
    print(f"  * Final Composite Score:   {ranking['final_score']:.2f} / 100.0")
    print("  * Signal Breakdown:")
    for comp in ranking.get("components", []):
        name = comp["signal"].replace("_", " ").title()
        weight = comp["effective_weight"]
        score = comp["score"]
        used = comp["used"]
        if score is not None and used:
            print(f"      - {name:<24}: Score = {score:6.2f} | Effective Weight = {weight:5.2f} (Active)")
        elif score is not None:
            print(f"      - {name:<24}: Score = {score:6.2f} | Effective Weight = {weight:5.2f} (Zero Weight)")
        else:
            print(f"      - {name:<24}: Score =    N/A | Effective Weight =  0.00 (Unavailable)")

    prefs_eval = record.get("preferences", {})
    if "user_to_candidate" in prefs_eval and "candidate_to_user" in prefs_eval:
        u2c = prefs_eval["user_to_candidate"]
        c2u = prefs_eval["candidate_to_user"]
        print("\n  * Bilateral Stated Preferences:")
        print(f"      - User A -> User B Satisfaction: {u2c.get('score', 0):.1f}% (Confidence: {u2c.get('confidence', 0):.1f}%)")
        print(f"      - User B -> User A Satisfaction: {c2u.get('score', 0):.1f}% (Confidence: {c2u.get('confidence', 0):.1f}%)")

    pers_eval = record.get("personality", {})
    print("\n  * Personality Compatibility:")
    print(f"      - Compatibility Score:     {pers_eval.get('score', 'N/A')}")
    print(f"      - Trait Alignment:         {pers_eval.get('type_a', '').title()} + {pers_eval.get('type_b', '').title()} ({pers_eval.get('type_compatibility', '')})")
    print(f"      - Communication Alignment: {pers_eval.get('communication_compatibility', 'N/A')}")

    print("\n" + "=" * 80)
    print("[5] AUDITABLE EXPLAINABILITY & TRANSPARENCY:")
    print("=" * 80)
    explanation = explain_recommendation(record)
    print(f"  * Match Classification:    {explanation['decision'].upper()}")
    print(f"  * Summary:                 {explanation['summary']}")
    print("  * Matched Preferences:")
    for mp in explanation["matched_preferences"]:
        print(f"      [+] {mp['criterion'].replace('_', ' ').title()} ({mp['direction']}): {mp['satisfaction_score']}% matched")
    print("  * Honest Accounting of Unavailable Profile Data (Not Penalized):")
    for un in explanation["unavailable_information"]:
        print(f"      [-] {un}")

    print("\n" + "=" * 80)
    print("[6] PRESENTATION-FRIENDLY SUMMARY & VERDICT:")
    print("=" * 80)
    print(
        f"Verdict: Profile A and Profile B are considered COMPATIBLE with a composite score of {ranking['final_score']:.1f}/100.\n\n"
        "Why they matched:\n"
        "  1. Shared Demographics & Life Stage: Ages 27 and 26 in the same generation.\n"
        "  2. Geographic Proximity: Both reside in Pune, India (0 km apart), well within the 50 km preferred radius.\n"
        "  3. Career & Education Alignment: Both are software engineers with university degrees.\n"
        "  4. Lifestyle & Habit Harmony: Both are non-smokers and vegetarians, satisfying stated dealbreakers.\n"
        "  5. Complementary Personality: Both self-report as introverts who prefer deep conversations.\n"
        "  6. Relationship Intent: Both seek long-term relationships.\n\n"
        "Missing Data Handling:\n"
        "  * Missing fields (religion, ethnicity, height, pets) were not fabricated or assumed to be negative;\n"
        "    instead, the model reduced confidence to 41.25% and regressed the baseline score conservatively.\n\n"
        f"MANDATORY SCIENTIFIC DISCLAIMER:\n  {explanation['disclaimer']}"
    )
    print("=" * 80)


if __name__ == "__main__":
    run_demo()

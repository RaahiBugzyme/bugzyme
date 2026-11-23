#!/usr/bin/env python3
"""HeartMatch ML V3 — Demonstration of Two Randomly Selected User Profiles.

Selects two user profiles randomly from either the anonymized benchmark dataset
(data/profiles_revised.csv) or synthetic test fixtures, evaluates their compatibility
using the actual HeartMatch ML V3 code, and produces an auditable, presentation-friendly report.

Usage:
    python demo_random_two_profiles.py                      # Default: Seed 7 (eligible pair from dataset)
    python demo_random_two_profiles.py --seed 42            # Shows eligibility gating (orientation mismatch)
    python demo_random_two_profiles.py --seed 100           # Another eligible pair from dataset
    python demo_random_two_profiles.py --source synthetic   # Random selection from synthetic test fixtures
    python demo_random_two_profiles.py --require-eligible   # Guarantees sampling an eligible pair
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from dating_ml_model.compatibility_engine import CATEGORIES
from dating_ml_model.explainability import explain_recommendation
from dating_ml_model.model import CompatibilityModel, RecommendationModel
from dating_ml_model.synthetic_data import get_synthetic_test_suite_data


def load_dataset_profiles(
    csv_path: str = "data/profiles_revised.csv",
    seed: int = 7,
    require_eligible: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Randomly selects two distinct adult profiles from the anonymized benchmark dataset."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found at {path.resolve()}")

    df = pd.read_csv(path)
    # Filter for valid adult profiles with non-null age and orientation
    valid_df = df[df["age"].notna() & (df["age"] >= 18) & df["sex"].notna() & df["orientation"].notna()]
    if len(valid_df) < 2:
        raise ValueError("Insufficient valid adult records in dataset.")

    compat_model = CompatibilityModel()
    rng = random.Random(seed)

    if require_eligible:
        # Search deterministically starting from seed until an eligible pair is found
        for attempt in range(1000):
            sample = valid_df.sample(2, random_state=rng.randint(0, 1000000))
            idx1, idx2 = sample.index[0], sample.index[1]
            p1 = {k: (None if pd.isna(v) else v) for k, v in sample.iloc[0].to_dict().items()}
            p2 = {k: (None if pd.isna(v) else v) for k, v in sample.iloc[1].to_dict().items()}
            p1["id"] = f"anon_dataset_user_{idx1}"
            p2["id"] = f"anon_dataset_user_{idx2}"
            p1["data_source"] = "ANONYMIZED_BENCHMARK_DATASET_RECORD (No PII)"
            p2["data_source"] = "ANONYMIZED_BENCHMARK_DATASET_RECORD (No PII)"
            if compat_model.check_eligibility(p1, p2)["eligible"]:
                return p1, p2, None, None
        raise RuntimeError("Could not find an eligible pair after 1000 random samples.")

    # Standard direct sample using seed
    sample = valid_df.sample(2, random_state=seed)
    idx1, idx2 = sample.index[0], sample.index[1]
    p1 = {k: (None if pd.isna(v) else v) for k, v in sample.iloc[0].to_dict().items()}
    p2 = {k: (None if pd.isna(v) else v) for k, v in sample.iloc[1].to_dict().items()}
    p1["id"] = f"anon_dataset_user_{idx1}"
    p2["id"] = f"anon_dataset_user_{idx2}"
    p1["data_source"] = "ANONYMIZED_BENCHMARK_DATASET_RECORD (No PII)"
    p2["data_source"] = "ANONYMIZED_BENCHMARK_DATASET_RECORD (No PII)"
    return p1, p2, None, None


def load_synthetic_profiles(
    seed: int = 7,
    require_eligible: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Randomly selects two profiles from the rich synthetic test suite fixtures."""
    suite = get_synthetic_test_suite_data()
    all_profiles: List[Dict[str, Any]] = list(suite["focus_users"].values()) + list(suite["candidate_pool"])
    prefs_map = suite.get("user_preferences", {})
    compat_model = CompatibilityModel()

    rng = random.Random(seed)
    indices = list(range(len(all_profiles)))

    if require_eligible:
        for _ in range(500):
            i1, i2 = rng.sample(indices, 2)
            p1, p2 = all_profiles[i1], all_profiles[i2]
            if compat_model.check_eligibility(p1, p2)["eligible"]:
                return p1, p2, prefs_map.get(str(p1.get("id"))), prefs_map.get(str(p2.get("id")))
        raise RuntimeError("Could not find eligible synthetic pair.")

    i1, i2 = rng.sample(indices, 2)
    p1, p2 = all_profiles[i1], all_profiles[i2]
    return p1, p2, prefs_map.get(str(p1.get("id"))), prefs_map.get(str(p2.get("id")))


def format_profile_details(title: str, p: Dict[str, Any], prefs: Optional[Dict[str, Any]] = None) -> str:
    """Formats a profile card highlighting available vs missing attributes."""
    known_fields = []
    missing_fields = []

    core_attrs = [
        ("Age", p.get("age")),
        ("Sex", p.get("sex")),
        ("Orientation", p.get("orientation")),
        ("Location", p.get("city") or p.get("location")),
        ("Profession", p.get("job")),
        ("Education", p.get("education")),
        ("Diet", p.get("diet")),
        ("Smokes", p.get("smokes")),
        ("Drinks", p.get("drinks")),
        ("Drugs", p.get("drugs")),
        ("Offspring", p.get("offspring")),
        ("Pets", p.get("pets")),
        ("Height", f"{p.get('height')} inches" if p.get("height") else None),
        ("Body Type", p.get("body_type")),
        ("Religion", p.get("religion")),
        ("Ethnicity", p.get("ethnicity")),
        ("Interests", ", ".join(p.get("interests", [])) if p.get("interests") else None),
        ("Relationship Goal", p.get("relationship_intention")),
    ]

    for label, val in core_attrs:
        if val is not None and str(val).strip() != "":
            known_fields.append(f"{label}: {val}")
        else:
            missing_fields.append(label)

    lines = [
        f"--- {title} [{p.get('id', 'N/A')}] ---",
        f"  * Provenance:         {p.get('data_source', 'SYNTHETIC_FIXTURE')}",
        f"  * Core Demographics:  Age {p.get('age', 'N/A')} | Sex: {str(p.get('sex')).upper()} | Orientation: {str(p.get('orientation')).title()}",
        f"  * Available Fields:   " + " | ".join(known_fields[:6]),
    ]
    if len(known_fields) > 6:
        lines.append(f"                        " + " | ".join(known_fields[6:]))

    if prefs:
        pref_str = f"Preferred Dist: <={prefs.get('preferred_distance_km')}km"
        if prefs.get("dealbreakers"):
            pref_str += f" | Dealbreakers: {prefs.get('dealbreakers')}"
        lines.append(f"  * Stated Preferences: {pref_str}")
    else:
        lines.append("  * Stated Preferences: None specified on profile")

    if missing_fields:
        lines.append(f"  * Unstated / Missing: {', '.join(missing_fields)} (Treated as unverified, NOT penalized)")
    return "\n".join(lines)


def run_random_demonstration(seed: int = 7, source: str = "dataset", require_eligible: bool = False) -> None:
    print("=" * 80)
    print("HEARTMATCH ML V3 — RANDOM TWO-PROFILE COMPATIBILITY DEMONSTRATION")
    print(f"Random Seed:       {seed} (Reproducible deterministic execution)")
    print(f"Profile Source:    {source.upper()} ({'data/profiles_revised.csv' if source == 'dataset' else 'synthetic fixtures'})")
    print(f"Require Eligible:  {require_eligible}")
    print("=" * 80)

    # 1. Load profiles
    if source.lower() == "synthetic":
        p_a, p_b, prefs_a, prefs_b = load_synthetic_profiles(seed=seed, require_eligible=require_eligible)
    else:
        p_a, p_b, prefs_a, prefs_b = load_dataset_profiles(seed=seed, require_eligible=require_eligible)

    print("\n[SECTION 1] RANDOMLY SELECTED PROFILES:")
    print(format_profile_details("PROFILE A", p_a, prefs_a))
    print()
    print(format_profile_details("PROFILE B", p_b, prefs_b))

    # 2. Initialize actual HeartMatch ML V3 models
    compat_model = CompatibilityModel()
    rec_model = RecommendationModel(compatibility_model=compat_model)

    print("\n" + "=" * 80)
    print("[SECTION 2] ELIGIBILITY & HARD CONSTRAINTS CHECK:")
    print("=" * 80)
    elig, loc = rec_model.check_extended_eligibility(
        user=p_a,
        candidate=p_b,
        user_preferences=prefs_a,
        candidate_preferences=prefs_b,
    )
    status_label = "ELIGIBLE (Proceeding to compatibility scoring)" if elig["eligible"] else "INELIGIBLE (Excluded by hard gate)"
    print(f"  * Gate Decision:           {status_label}")
    if not elig["eligible"]:
        print(f"  * Hard Exclusion Reasons:  {elig['reasons']}")
    else:
        print("  * Adulthood Check:         PASSED (Both users >= 18)")
        print("  * Mutual Attraction:       PASSED (Sex/Orientation criteria mutually compatible)")
        print(f"  * Location Proximity:      {loc.get('distance_km', 'N/A')} km (Status: {loc.get('location_status')})")

    print("\n" + "=" * 80)
    print("[SECTION 3] COMPATIBILITY MODEL (LAYER 1 BASELINE):")
    print("=" * 80)
    l1_result = compat_model.predict_pair(p_a, p_b)

    if not l1_result["eligible"]:
        print(f"  * Pair Compatibility:      None (Ineligible: {l1_result['eligibility_reason']})")
    else:
        print(f"  * Raw Compatibility Score: {l1_result['compatibility_score']:.2f} / 100.0")
        print(f"  * Evidence Confidence:     {l1_result['confidence_score']:.2f}% (Known attributes share)")
        print(f"  * Adjusted Baseline Score: {l1_result['adjusted_score']:.2f} / 100.0 (Regressed toward neutral 50.0)")
        print("  * Category Breakdown:")
        for cat in CATEGORIES:
            cat_score = l1_result["categories"].get(cat)
            cat_str = f"{cat_score:.1f}%" if cat_score is not None else "Unavailable / Missing"
            print(f"      - {cat.replace('_', ' ').title():<20}: {cat_str}")
        print("  * Attribute Level Signals:")
        for line in l1_result.get("explanation", []):
            print(f"      * {line}")

    print("\n" + "=" * 80)
    print("[SECTION 4] LAYERED MULTI-SIGNAL & BILATERAL PREFERENCES:")
    print("=" * 80)
    record = rec_model.evaluate_candidate(
        user=p_a,
        candidate=p_b,
        user_preferences=prefs_a,
        candidate_preferences=prefs_b,
    )

    ranking = record["ranking"]
    final_score = ranking.get("final_score")
    if final_score is not None:
        print(f"  * Final Composite Score:   {final_score:.2f} / 100.0")
        print("  * Signal Breakdown:")
        for comp in ranking.get("components", []):
            name = comp["signal"].replace("_", " ").title()
            weight = comp["effective_weight"]
            score = comp["score"]
            used = comp["used"]
            if score is not None and used:
                print(f"      - {name:<24}: Score = {score:6.2f} | Weight = {weight:5.2f} (Active)")
            elif score is not None:
                print(f"      - {name:<24}: Score = {score:6.2f} | Weight = {weight:5.2f} (Zero Weight)")
            else:
                print(f"      - {name:<24}: Score =    N/A | Weight =  0.00 (Unavailable/Omitted)")
    else:
        print("  * Final Composite Score:   None (Excluded by hard gate or insufficient eligibility)")

    # Directional / Bilateral preference analysis
    prefs_eval = record.get("preferences")
    if prefs_eval and isinstance(prefs_eval, dict):
        if "user_to_candidate" in prefs_eval and "candidate_to_user" in prefs_eval:
            u2c = prefs_eval["user_to_candidate"]
            c2u = prefs_eval["candidate_to_user"]
            print("\n  * Directional Preference Evaluation:")
            print(f"      - Profile A -> Profile B Satisfaction: {u2c.get('score', 0):.1f}% (Confidence: {u2c.get('confidence', 0):.1f}%)")
            print(f"      - Profile B -> Profile A Satisfaction: {c2u.get('score', 0):.1f}% (Confidence: {c2u.get('confidence', 0):.1f}%)")
        else:
            print(f"\n  * Preferences Evaluation Status: {prefs_eval.get('status')}")
    else:
        print("\n  * Preferences Evaluation: No explicit criteria specified on profiles (skipped without penalty)")

    print("\n" + "=" * 80)
    print("[SECTION 5] AUDITABLE EXPLAINABILITY & TRANSPARENCY:")
    print("=" * 80)
    explanation = explain_recommendation(record)
    print(f"  * Match Decision:          {explanation['decision'].upper()}")
    print(f"  * Decision Summary:        {explanation['summary']}")

    if explanation.get("matched_preferences"):
        print("  * Positively Matched Criteria:")
        for mp in explanation["matched_preferences"]:
            print(f"      [+] {mp['criterion'].replace('_', ' ').title()}: {mp['satisfaction_score']}% matched")

    if explanation.get("mismatched_preferences"):
        print("  * Divergent Soft Criteria:")
        for mmp in explanation["mismatched_preferences"]:
            print(f"      [-] {mmp['criterion'].replace('_', ' ').title()}: {mmp['satisfaction_score']}% satisfaction")

    if explanation.get("unavailable_information"):
        print("  * Transparent Missing Information Accounting (Not Penalized):")
        for un in explanation["unavailable_information"][:5]:
            print(f"      [?] {un}")

    print("\n" + "=" * 80)
    print("[SECTION 6] PLAIN-ENGLISH SUMMARY & SCIENTIFIC DISCLAIMER:")
    print("=" * 80)
    if elig["eligible"]:
        score_val = f"{final_score:.1f}/100" if final_score is not None else "N/A"
        print(f"Verdict: Profile A and Profile B are ELIGIBLE with a compatibility rating of {score_val}.")
        print("Key factors:")
        print(f"  - Profile A ({p_a.get('age')}{p_a.get('sex')}) and Profile B ({p_b.get('age')}{p_b.get('sex')}) satisfy mutual orientation and adulthood rules.")
        if l1_result.get("adjusted_score"):
            print(f"  - Core compatibility was evaluated across available attributes with {l1_result['confidence_score']:.1f}% data completeness.")
    else:
        print("Verdict: Profile A and Profile B are INELIGIBLE under HeartMatch ML V3 rules.")
        print(f"Reason: {'; '.join(elig['reasons'])}")
        print("The matching engine enforces hard ethical and preference boundaries before calculating compatibility scores.")

    print(f"\nMANDATORY SCIENTIFIC DISCLAIMER:\n  {explanation['disclaimer']}")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Demonstrate HeartMatch ML V3 compatibility on two randomly selected profiles.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for reproducible selection (default: 7)")
    parser.add_argument("--source", type=str, choices=["dataset", "synthetic"], default="dataset",
                        help="Profile source: 'dataset' (data/profiles_revised.csv) or 'synthetic' (default: dataset)")
    parser.add_argument("--require-eligible", action="store_true", help="Filter random selection to guarantee an eligible pair")

    args = parser.parse_args()
    run_random_demonstration(seed=args.seed, source=args.source, require_eligible=args.require_eligible)


if __name__ == "__main__":
    main()

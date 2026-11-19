"""Explainable Recommendations & Score Transparency (Phase 5).

Provides a transparent, auditable breakdown of matchmaking decisions:
- Identifies matched preferences, mismatched preferences, hard exclusions, and missing info separately.
- Explains geographic distance only when distance is known.
- Breaks down scoring components using actual weights and scores (no invented numbers).
- Guarantees explanations agree with eligibility decisions and ranking results.
- Explicitly states that compatibility scores reflect alignment/similarity, NOT relationship success probabilities.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def explain_recommendation(record: Dict[str, Any]) -> Dict[str, Any]:
    """Generates a structured, transparent explanation for a recommendation record or pair prediction.

    Ensures complete consistency with eligibility, preferences, distance, and ranking signals.
    """
    uid = record.get("user_id") or record.get("user_a")
    cid = record.get("candidate_id") or record.get("user_b")

    # 1. Eligibility & Hard Exclusion Failures
    elig = record.get("eligibility")
    if elig is None and "eligible" in record:
        reasons_list = [record["eligibility_reason"]] if record.get("eligibility_reason") else (record.get("explanation") or [])
        elig = {"eligible": bool(record["eligible"]), "reasons": reasons_list}
    elif elig is None:
        elig = {"eligible": False, "reasons": ["Ineligible"]}

    is_eligible = bool(elig.get("eligible", False))
    reasons = list(elig.get("reasons", []))
    hard_failures = list(reasons) if not is_eligible else []

    # 2. Preference Breakdown: matched, mismatched, unavailable
    matched_prefs: List[Dict[str, Any]] = []
    mismatched_prefs: List[Dict[str, Any]] = []
    unavailable_info: List[str] = []

    pref = record.get("preferences")
    if pref and isinstance(pref, dict):
        # Directional breakdowns if bilateral evaluation was run
        u_to_c = pref.get("user_to_candidate") or pref.get("a_to_b")
        c_to_u = pref.get("candidate_to_user") or pref.get("b_to_a")

        if u_to_c and isinstance(u_to_c, dict):
            for name, score in sorted((u_to_c.get("criteria") or {}).items()):
                if score is None:
                    unavailable_info.append(f"Candidate's {name.replace('_', ' ')} is unknown on profile (unverified; not penalized).")
                elif score >= 0.8:
                    matched_prefs.append({
                        "criterion": name,
                        "satisfaction_score": round(score * 100.0, 2),
                        "direction": "viewer_preference",
                        "status": "matched" if score == 1.0 else "mostly_matched",
                    })
                else:
                    mismatched_prefs.append({
                        "criterion": name,
                        "satisfaction_score": round(score * 100.0, 2),
                        "direction": "viewer_preference",
                        "status": "mismatched",
                    })
        elif pref.get("criteria"):
            for name, score in sorted(pref["criteria"].items()):
                if score is None:
                    unavailable_info.append(f"Candidate's {name.replace('_', ' ')} is unknown on profile (unverified; not penalized).")
                elif score >= 0.8:
                    matched_prefs.append({
                        "criterion": name,
                        "satisfaction_score": round(score * 100.0, 2),
                        "direction": "viewer_preference",
                        "status": "matched" if score == 1.0 else "mostly_matched",
                    })
                else:
                    mismatched_prefs.append({
                        "criterion": name,
                        "satisfaction_score": round(score * 100.0, 2),
                        "direction": "viewer_preference",
                        "status": "mismatched",
                    })

        if c_to_u and isinstance(c_to_u, dict):
            if c_to_u.get("status") == "no_preferences":
                unavailable_info.append("Candidate has not specified explicit preferences (no candidate preference penalty was applied).")
            else:
                for name, score in sorted((c_to_u.get("criteria") or {}).items()):
                    if score is None:
                        unavailable_info.append(f"Your {name.replace('_', ' ')} was not evaluated against candidate's preferences.")
                    elif score >= 0.8:
                        matched_prefs.append({
                            "criterion": name,
                            "satisfaction_score": round(score * 100.0, 2),
                            "direction": "candidate_preference",
                            "status": "matched" if score == 1.0 else "mostly_matched",
                        })
                    else:
                        mismatched_prefs.append({
                            "criterion": name,
                            "satisfaction_score": round(score * 100.0, 2),
                            "direction": "candidate_preference",
                            "status": "mismatched",
                        })

        for w in pref.get("warnings", []):
            if "unverified" in w:
                unavailable_info.append(w)
    else:
        unavailable_info.append("No explicit preference filter was specified.")

    # Personality Preferences (Phase 6)
    pers = record.get("personality")
    if pers and isinstance(pers, dict):
        if pers.get("status") == "unavailable":
            unavailable_info.append("Personality and communication preferences not provided by one or both users.")
        else:
            for name, score in sorted((pers.get("criteria") or {}).items()):
                if score is not None:
                    if score >= 0.8:
                        matched_prefs.append({
                            "criterion": f"personality_{name}",
                            "satisfaction_score": round(score * 100.0, 2),
                            "direction": "personality_alignment",
                            "status": "matched" if score >= 0.9 else "mostly_matched",
                        })
                    else:
                        mismatched_prefs.append({
                            "criterion": f"personality_{name}",
                            "satisfaction_score": round(score * 100.0, 2),
                            "direction": "personality_alignment",
                            "status": "mismatched",
                        })

    # Learned & External Interests (Phase 6 & Phase 1)
    inter = record.get("interests")
    if inter and isinstance(inter, dict):
        if inter.get("status") == "cold_start":
            unavailable_info.append("Learned interest profile has no interaction evidence yet (cold start).")
        else:
            details_map = {d["token"]: d for d in (inter.get("aligned_interest_details") or [])}
            for item in (inter.get("aligned_interests") or []):
                detail = details_map.get(item)
                prov = detail.get("provenance") if detail else None
                direction = "external_interest" if prov else "learned_interest"
                entry: Dict[str, Any] = {
                    "criterion": f"{direction}_{item}",
                    "satisfaction_score": 100.0,
                    "direction": direction,
                    "status": "matched",
                }
                if prov:
                    providers = sorted({p.get("provider", "").replace("_", " ").title() for p in prov if p.get("provider")})
                    conf = max([p.get("confidence", 0.0) for p in prov] or [0.0])
                    entry["provenance"] = prov
                    entry["providers"] = providers
                    entry["confidence"] = round(conf, 4)
                matched_prefs.append(entry)

    # 3. Location Explanation (distance explained ONLY when known)
    loc = record.get("location")
    location_explanation: Dict[str, Any] = {
        "status": "unknown",
        "distance_km": None,
        "within_preferred_distance": None,
        "within_max_distance": None,
        "explanation": "Location information is unavailable. No distance penalty was applied.",
    }
    if loc and isinstance(loc, dict):
        loc_status = loc.get("location_status", "unknown")
        dist = loc.get("distance_km")
        location_explanation["status"] = loc_status
        location_explanation["distance_km"] = dist
        location_explanation["within_preferred_distance"] = loc.get("within_preferred_distance")
        location_explanation["within_max_distance"] = loc.get("within_max_distance")

        if loc_status == "known" and dist is not None:
            pref_dist = loc.get("preferred_distance_km")
            max_dist = loc.get("max_distance_km")
            if loc.get("within_max_distance") is False:
                location_explanation["explanation"] = (
                    f"Candidate is approximately {dist:g} km away, which exceeds your maximum allowed distance of {max_dist:g} km."
                )
            elif loc.get("within_preferred_distance"):
                location_explanation["explanation"] = (
                    f"Candidate is approximately {dist:g} km away, within your preferred distance of {pref_dist:g} km."
                )
            else:
                location_explanation["explanation"] = (
                    f"Candidate is approximately {dist:g} km away, farther than preferred distance ({pref_dist:g} km), but within acceptable limits."
                )
        elif loc_status in ("unknown", "partial_unknown"):
            location_explanation["explanation"] = (
                "Location coordinates are not available for both profiles. Distance cannot be calculated, so no location penalty was applied."
            )
            unavailable_info.append("Geographic distance is unknown due to missing location coordinates.")
        elif loc_status == "unresolved":
            location_explanation["explanation"] = (
                "City location could not be resolved reliably to centroid coordinates. Distance signal was omitted without penalty."
            )
            unavailable_info.append("Geographic resolution was unresolved for city name.")
        elif loc_status == "coarse":
            location_explanation["explanation"] = (
                "Only regional or country-level location is available. Distance cannot be calculated reliably, so no distance penalty was applied."
            )
            unavailable_info.append("Geographic data is coarse (region/country only); distance calculation is unavailable.")
    else:
        # Check if location distance was recorded in hard failures (e.g., when evaluate_candidate sets location=None on ineligibility)
        dist_match = None
        for failure in hard_failures:
            m = re.search(r"Beyond a hard maximum distance \((\d+(?:\.\d+)?)\s*km away\)", failure)
            if m:
                dist_match = float(m.group(1))
                break
        if dist_match is not None:
            location_explanation["status"] = "known"
            location_explanation["distance_km"] = dist_match
            location_explanation["within_max_distance"] = False
            location_explanation["explanation"] = (
                f"Candidate is approximately {dist_match:g} km away, which exceeds your maximum allowed distance."
            )

    # 4. Behavioral & Mutual Interest Unavailable Signals
    beh = record.get("behavior")
    if beh and isinstance(beh, dict):
        b_status = beh.get("status")
        if b_status == "cold_start":
            unavailable_info.append("No interaction history yet, so behavioral personalization was omitted.")
        elif b_status == "insufficient_data":
            unavailable_info.append(f"Behavioral evidence is limited ({beh.get('evidence_count', 0)} events); personalization was not used.")

    mi = record.get("mutual_interest")
    if mi and isinstance(mi, dict):
        mi_status = mi.get("status")
        if mi_status == "insufficient_behavioral_data" or mi_status == "unavailable":
            unavailable_info.append("Interaction-based mutual interest model is not active due to insufficient behavioral logs.")

    # 5. Transparent Scoring Breakdown
    ranking = record.get("ranking") or {}
    final_score = ranking.get("final_score")
    components_raw = ranking.get("components") or []

    if final_score is None and "adjusted_score" in record:
        final_score = record.get("adjusted_score")

    # Sum of effective weights for used components
    total_effective_weight = sum(
        float(c.get("effective_weight", 0.0))
        for c in components_raw
        if c.get("used") and c.get("score") is not None
    )

    components_breakdown: List[Dict[str, Any]] = []
    if components_raw:
        for c in components_raw:
            sig_name = c.get("signal")
            sig_score = c.get("score")
            eff_w = float(c.get("effective_weight", 0.0))
            used = bool(c.get("used", False))

            point_contrib = None
            weight_share_pct = None
            if used and sig_score is not None and total_effective_weight > 0:
                point_contrib = round((eff_w * float(sig_score)) / total_effective_weight, 4)
                weight_share_pct = round(100.0 * eff_w / total_effective_weight, 2)

            components_breakdown.append({
                "signal": sig_name,
                "score": sig_score,
                "base_weight": c.get("base_weight"),
                "effective_weight": eff_w,
                "used": used,
                "point_contribution": point_contrib,
                "weight_share_pct": weight_share_pct,
                "status": "contributing" if used else "omitted_or_zero_weight",
            })
    elif record.get("categories"):
        # Compatibility-only breakdown (from predict_pair)
        for cat_name, cat_score in sorted((record.get("categories") or {}).items()):
            components_breakdown.append({
                "signal": cat_name,
                "score": cat_score,
                "base_weight": None,
                "effective_weight": None,
                "used": cat_score is not None,
                "point_contribution": None,
                "weight_share_pct": None,
                "status": "contributing" if cat_score is not None else "unavailable_or_unanswered",
            })

    # 6. Overall Decision & Summary
    if not is_eligible:
        decision = "ineligible"
        summary = f"Candidate is not eligible: {'; '.join(hard_failures)}."
    elif final_score is not None and final_score >= 80.0:
        decision = "strongly_recommended"
        summary = f"Strong overall match ({final_score:.1f}/100) driven by high profile alignment and mutual criteria satisfaction."
    elif final_score is not None and final_score >= 60.0:
        decision = "recommended"
        summary = f"Good overall match ({final_score:.1f}/100) with favorable compatibility across available attributes."
    else:
        decision = "partially_aligned"
        score_str = f"{final_score:.1f}/100" if final_score is not None else "N/A"
        summary = f"Moderate match ({score_str}) with differences in some soft preferences or limited evidence."

    return {
        "user_id": uid,
        "candidate_id": cid,
        "eligible": is_eligible,
        "decision": decision,
        "summary": summary,
        "hard_exclusion_failures": hard_failures,
        "matched_preferences": matched_prefs,
        "mismatched_preferences": mismatched_prefs,
        "unavailable_information": sorted(set(unavailable_info)),
        "location_explanation": location_explanation,
        "scoring_breakdown": {
            "final_score": final_score,
            "components": components_breakdown,
            "weights_validated": bool(ranking.get("weights_are_validated", False)),
            "score_interpretation": (
                "Scores reflect profile attribute similarity and stated preference alignment. "
                "They are not an empirical probability of relationship success."
            ),
        },
        "personality": pers or {"status": "unavailable"},
        "disclaimer": (
            "Scores reflect profile attribute similarity and stated preference alignment. "
            "They are not an empirical probability of relationship success."
        ),
        "text_explanations": record.get("explanation") or [],
    }

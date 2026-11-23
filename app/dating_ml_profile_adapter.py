#!/usr/bin/env python3


def user_to_datingml_profile(user):
    """Convert a User model instance to a DatingML V3 profile dict.

    Safely handles all optional/missing fields. Only includes fields
    that have actual values; None/Null fields are omitted.

    The DatingML V3 profile structure includes:
    - age (optional)
    - location (optional)
    - preferences (optional)
    - relationship_intention (optional)
    - interests (optional)
    - personality traits (optional)
    """
    from app.models import DatingProfile  # lazy import

    profile = {}

    # Start with User-level fields
    if user.bio:
        profile["bio"] = user.bio

    if user.activity_status_enabled:
        profile["activity_status_enabled"] = user.activity_status_enabled

    if user.ai_memory_enabled:
        profile["ai_memory_enabled"] = user.ai_memory_enabled

    if user.full_name:
        profile["full_name"] = user.full_name

    profile["username"] = user.username

    if user.last_seen:
        profile["last_seen"] = user.last_seen

    # Now override/update with DatingProfile fields if they exist
    dp = getattr(user, "dating_profile", None)
    if dp:
        # Physical attributes
        if dp.height is not None:
            profile["height"] = dp.height
        if dp.body_type:
            profile["body_type"] = dp.body_type

        # Location
        if dp.city:
            profile["city"] = dp.city
        if dp.state:
            profile["state"] = dp.state
        if dp.country:
            profile["country"] = dp.country

        # Preferences
        if dp.orientation:
            profile["orientation"] = dp.orientation
        if dp.target_gender_preference:
            profile["target_gender_preference"] = dp.target_gender_preference
        if dp.match_era_preference:
            profile["match_era_preference"] = dp.match_era_preference
        if dp.sex:
            profile["sex"] = dp.sex

        # Lifestyle
        if dp.drinks:
            profile["drinks"] = dp.drinks
        if dp.drugs:
            profile["drugs"] = dp.drugs
        if dp.smokes:
            profile["smokes"] = dp.smokes
        if dp.diet:
            profile["diet"] = dp.diet

        # Family
        if dp.offspring:
            profile["offspring"] = dp.offspring
        if dp.pets:
            profile["pets"] = dp.pets

        # Values & culture
        if dp.religion:
            profile["religion"] = dp.religion
        if dp.ethnicity:
            profile["ethnicity"] = dp.ethnicity

        # Education & career
        if dp.education:
            profile["education"] = dp.education
        if dp.job:
            profile["job"] = dp.job

        # Verification
        if dp.is_face_verified:
            profile["is_face_verified"] = dp.is_face_verified
        if dp.is_id_verified:
            profile["is_id_verified"] = dp.is_id_verified
        if dp.verification_status:
            profile["verification_status"] = dp.verification_status
        if dp.profile_completion_pct is not None:
            profile["profile_completion_pct"] = dp.profile_completion_pct
        if dp.is_profile_public is not None:
            profile["is_profile_public"] = dp.is_profile_public

    return profile

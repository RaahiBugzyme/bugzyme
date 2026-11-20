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
    profile = {}

    # Age (from full_name or other indicators - but we do not fabricate age)
    # The DatingML model expects age, but we do not have it in the User model
    # So we simply omit it rather than inventing a value

    # Location - user has no location field in the model
    # Omit rather than invent

    # Preferences - user has bio and activity_status_enabled
    if user.bio:
        profile["bio"] = user.bio

    # Relationship intention - not explicitly in User model
    # Omit rather than invent

    # Interests - not explicitly in User model
    # Omit rather than invent

    # Personality traits - not explicitly in User model
    # Omit rather than invent

    # activity_status_enabled is available
    if user.activity_status_enabled:
        profile["activity_status_enabled"] = user.activity_status_enabled

    # ai_memory_enabled is available
    if user.ai_memory_enabled:
        profile["ai_memory_enabled"] = user.ai_memory_enabled

    # full_name is available
    if user.full_name:
        profile["full_name"] = user.full_name

    # username is always available (nullable=False)
    profile["username"] = user.username

    # last_seen is optional
    if user.last_seen:
        profile["last_seen"] = user.last_seen

    return profile
PYEND
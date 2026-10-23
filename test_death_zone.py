
import pytest

from app.ai.death_zone import (
    analyze_death_zone,
    is_death_zone,
)


def make_messages(contents, sender_a="1", sender_b="2"):
    """Create alternating messages for two participants."""
    return [
        {
            "sender_id": sender_a if i % 2 == 0 else sender_b,
            "content": content,
        }
        for i, content in enumerate(contents)
    ]


def test_insufficient_messages():
    messages = make_messages([
        "Hey",
        "Hello",
        "How are you?",
        "Fine",
    ])

    result = analyze_death_zone(messages)

    assert result["status"] == "insufficient_data"
    assert result["death_zone_score"] is None
    assert is_death_zone(result) is False


def test_healthy_conversation():
    messages = make_messages([
        "Hey, how was your day today?",
        "It was good, I finished my work early. What about yours?",
        "Mine was nice too! Did you watch that new movie?",
        "Not yet, but I have heard so many good things about it.",
        "You should definitely watch it this weekend!",
        "Sure, maybe we can discuss it after I watch it.",
        "That sounds great. What kind of movies do you usually enjoy?",
        "I love comedy and thriller movies, especially with good stories.",
        "Have you watched any interesting series recently?",
        "Yes, I started a new series yesterday and it is really engaging.",
        "Oh nice! Tell me the name so I can add it to my list.",
        "It is a mystery series. I think you would really enjoy it.",
        "Thanks for the recommendation! I will check it out.",
        "Let me know what you think after watching the first episode.",
        "Definitely! I will share my review with you.",
        "Looking forward to hearing it. Have a great evening!",
    ])

    result = analyze_death_zone(messages)

    assert result["status"] == "healthy"
    assert is_death_zone(result) is False


def test_stagnant_conversation():
    messages = make_messages([
        "Hey, how was your weekend?",
        "It was good, went out with some friends. What about you?",
        "Mine was nice too. Did you do anything interesting?",
        "I watched a movie and tried a new restaurant nearby.",
        "Oh nice! What movie did you watch?",
        "I watched a comedy movie. It was actually pretty funny.",
        "Sounds fun. Would you recommend it?",
        "Yeah, definitely worth watching if you like comedy.",
        "Hmm",
        "Okay",
        "Yeah",
        "Fine",
        "Lol",
        "Hmm",
        "Okay",
        "Sure",
    ])

    # Compare the latest 8 short messages against the earlier conversation.
    result = analyze_death_zone(messages, recent_window=8)

    assert result["status"] in {
    "stagnant",
    "declining",
    "possible_disengagement",
    }
    assert is_death_zone(result) is True


def test_declining_conversation():
    messages = make_messages([
        "Hey, how was your weekend?",
        "It was great, I went hiking with my friends. How about you?",
        "That sounds fun! Which place did you visit?",
        "We visited a beautiful mountain trail. Have you tried hiking?",
        "Not recently, but I would love to go. Was the trail difficult?",
        "It was a little challenging, but the views were totally worth it.",
        "You should take me there sometime! I love mountain views.",
        "Sure, I can share the location with you.",
        "What other places do you enjoy visiting?",
        "I love peaceful places, especially forests and mountains.",
        "Nice, we seem to have similar interests!",
        "Yeah, I think so too.",
        "Okay",
        "Hmm",
        "Fine",
        "Yeah",
        "Okay",
        "Lol",
        "Hmm",
        "Sure",
        "Fine",
        "Okay",
        "Yeah",
        "Hmm",
    ])

    result = analyze_death_zone(messages, recent_window=8)

    assert result["status"] in {
        "declining",
        "possible_disengagement",
    }
    assert result["engagement_change"] <= -15
    assert is_death_zone(result) is True


def test_deleted_messages_are_ignored():
    messages = make_messages([
        "Hey there!",
        "How are you doing today?",
        "I am doing well, thanks for asking.",
        "What are you planning for this weekend?",
        "Maybe I will go out with friends.",
        "That sounds nice! Any special plans?",
        "Not yet, still figuring it out.",
        "You could try a new cafe nearby.",
        "Thanks, that is a good idea!",
    ])

    messages.append({
        "sender_id": "1",
        "content": "This message was deleted.",
        "is_deleted": True,
    })

    result = analyze_death_zone(messages)

    assert result["message_count"] == 9


def test_invalid_recent_window():
    messages = make_messages([
        "Hello there!",
        "How are you doing?",
    ])

    with pytest.raises(ValueError):
        analyze_death_zone(messages, recent_window=1)


def test_invalid_input_type():
    with pytest.raises(TypeError):
        analyze_death_zone("not a list")


def test_threshold_validation():
    result = {
        "status": "stagnant",
        "death_zone_score": 80,
    }

    with pytest.raises(ValueError):
        is_death_zone(result, threshold=101)

    with pytest.raises(ValueError):
        is_death_zone(result, threshold=-1)

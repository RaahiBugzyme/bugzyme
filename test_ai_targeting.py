from app.ai.targeting import analyze_participant_effort


def _thread(effort_sender):
    texts = [
        "What was the best part of your weekend?",
        "Yeah",
        "I finally tried that little bookstore near the park today.",
        "Okay",
        "They had a lovely travel section and a tiny coffee corner too.",
        "Fine",
        "Do you usually pick travel books or something completely different?",
        "Hmm",
        "I found a funny collection of short stories that looked really good.",
        "Sure",
        "I might go back next week and see what else they have.",
        "Yep",
    ]
    return [
        {"sender_id": effort_sender if index % 2 == 0 else (2 if effort_sender == 1 else 1), "content": text}
        for index, text in enumerate(texts)
    ]


def test_high_effort_user_is_targeted_even_when_other_user_sent_last():
    result = analyze_participant_effort(_thread(1))
    assert result["eligible"] is True
    assert result["target_user_id"] == 1
    assert result["scores"]["1"] > result["scores"]["2"]


def test_targeting_reverses_when_other_user_is_carrying_conversation():
    result = analyze_participant_effort(_thread(2))
    assert result["eligible"] is True
    assert result["target_user_id"] == 2


def test_balanced_and_insufficient_conversations_do_not_target_anyone():
    balanced = []
    for index in range(12):
        balanced.append({
            "sender_id": 1 if index % 2 == 0 else 2,
            "content": "I had a nice day and tried a new recipe. What about you?",
        })
    assert analyze_participant_effort(balanced)["eligible"] is False
    assert analyze_participant_effort(balanced)["target_user_id"] is None
    assert analyze_participant_effort(balanced[:6])["reason"] == "insufficient_evidence"
